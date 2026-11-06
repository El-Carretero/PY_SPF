"""Bounded local progress logs and stack traces; never drive the instrument."""
from __future__ import annotations
from collections import deque
from datetime import datetime, timezone
import faulthandler
import functools
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import time
import uuid


class SessionDiagnostics:
    """Observe the main loop, with best-effort disk IO on a worker thread.

    A full queue drops new log records instead of delaying equipment control.
    Sequence gaps and heartbeat logger counters make that loss visible. File
    errors are retried on later worker passes. Stack traces are evidence of the
    current stack (including modal dialogs), rather than a hang verdict.
    """
    SCHEMA_VERSION = 2

    def __init__(self, controller, path=None, *, queue_capacity=4096,
                 max_file_bytes=16 * 1024 * 1024, retained_files=4,
                 flush_interval=.25, heartbeat_interval=1.,
                 max_flush_entries=128, max_flush_seconds=.02):
        self.enabled = path is not None
        if not self.enabled:
            return
        self.controller = controller
        self.path = Path(path)
        self.started = self.last_tick = time.monotonic()
        self._last_arm = self.started
        self.loops = 0
        self.phase = 'controller.start'
        self._closed = False
        self._queue = queue.Queue(maxsize=max(1, int(queue_capacity)))
        self._pending = deque()
        self._rotation_recovery = []
        self._done = threading.Event()
        self._health_lock = threading.Lock()
        self._hooks = []
        self._max_file_bytes = max(256, int(max_file_bytes))
        self._retained_files = max(1, int(retained_files))
        self._flush_interval = max(.01, float(flush_interval))
        self._heartbeat_interval = max(.01, float(heartbeat_interval))
        self._max_flush_entries = max(1, int(max_flush_entries))
        self._max_flush_seconds = max(.001, float(max_flush_seconds))
        self._sequence = 0
        self._worker_progress = self.started
        self._last_event_write = None
        self._last_heartbeat_write = None
        self._errors = {}
        self._health = {'accepted_events': 0, 'written_events': 0,
                        'dropped_events': 0, 'queue_high_watermark': 0,
                        'event_write_failures': 0, 'heartbeat_write_failures': 0,
                        'rotations': 0, 'worker_write_failures': 0}
        self._stacks = None
        from . import __version__
        hashes = {}
        for name in ('native.py', 'native_ticker.py', 'controller.py', 'protocol.py'):
            try:
                hashes[name] = hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            except OSError:
                hashes[name] = None
        self._identity = {'schema_version': self.SCHEMA_VERSION,
                          'session_id': uuid.uuid4().hex, 'session_directory': self.path.name, 'pid': os.getpid(),
                          'package_version': __version__, 'original_ni_gui_version': '1.6.0',
                          'source_sha256': hashes}
        self._main_snapshot = {}
        self._sample_main_thread()
        # Failure to create diagnostics must not prevent the controller starting.
        self._open_stacks()
        self._log = controller.log

        def log(kind, payload):
            self._enqueue(kind, payload)
            return self._log(kind, payload)

        controller.log = log
        for name in ('process_events', 'read', 'set_value', 'set_attribute',
                     'read_attribute', 'show_panel', '_control_event', 'close'):
            original = getattr(controller.view, name, None)
            if original is None:
                continue

            @functools.wraps(original)
            def tracked(*args, _name=name, _original=original, **kwargs):
                previous = self.phase
                self.phase = _name + repr(args[:3])[:100]
                try:
                    return _original(*args, **kwargs)
                finally:
                    self.phase = previous
            self._hooks.append((name, original))
            setattr(controller.view, name, tracked)
        self._thread = threading.Thread(target=self._observe, daemon=True,
                                        name='spitfire-local-diagnostics')
        self._thread.start()
        self._arm_watchdog()

    @staticmethod
    def _utc():
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

    def _set_error(self, area, error):
        with self._health_lock:
            self._errors[area] = f'{type(error).__name__}: {error}'[:500]
            key = area + '_write_failures'
            if key in self._health:
                self._health[key] += 1

    def _clear_error(self, area):
        with self._health_lock:
            self._errors.pop(area, None)

    def _open_stacks(self):
        if self._stacks is not None:
            return
        try:
            self.path.mkdir(parents=True, exist_ok=True)
            self._stacks = (self.path / 'stacks.txt').open('a', encoding='utf-8')
            self._clear_error('stacks')
        except OSError as error:
            self._set_error('stacks', error)

    def _arm_watchdog(self):
        if self._stacks is not None:
            try:
                faulthandler.dump_traceback_later(10, repeat=True, file=self._stacks)
            except (OSError, RuntimeError, ValueError) as error:
                self._set_error('stacks', error)

    def _enqueue(self, kind, payload):
        # Retain the old readable payload while giving new queue events fields
        # that a reader does not have to parse out of Python's dict repr.
        readable = str(payload)[:8192]
        while len(json.dumps(readable, ensure_ascii=False).encode('utf-8', errors='backslashreplace')) > 8192:
            readable = readable[:len(readable) // 2]
        entry = {'schema_version': self.SCHEMA_VERSION,
                 'session_id': self._identity['session_id'], 'utc': self._utc(),
                 'monotonic': time.monotonic(), 'kind': str(kind)[:100],
                 'payload': readable}
        if isinstance(payload, dict):
            try:
                encoded = json.dumps(payload, ensure_ascii=False, default=str, allow_nan=False)
                fields = json.loads(encoded) if len(encoded.encode('utf-8', errors='backslashreplace')) <= 16384 else {'truncated': True}
            except (TypeError, ValueError, OverflowError):
                fields = {'unserializable': True}
            entry['fields'] = fields
            for key in ('event', 'tag', 'request_id', 'queued_monotonic', 'origin', 'batch_id'):
                if key in fields:
                    entry[key] = fields[key]
        with self._health_lock:
            self._sequence += 1
            entry['seq'] = self._sequence
            try:
                self._queue.put_nowait(entry)
            except queue.Full:
                self._health['dropped_events'] += 1
            else:
                self._health['accepted_events'] += 1
                self._health['queue_high_watermark'] = max(
                    self._health['queue_high_watermark'], self._queue.qsize())

    def tick(self):
        if not self.enabled or self._closed:
            return
        self.loops += 1
        self.last_tick = time.monotonic()
        self.phase = 'main_loop'
        if self.last_tick - self._last_arm >= 1:
            self._sample_main_thread()
            # Only this main-thread method arms faulthandler. The writer never
            # calls GUI or controller methods, including communication sampling.
            self._arm_watchdog()
            self._last_arm = self.last_tick

    def _sample_main_thread(self):
        try:
            state = self.controller.state
            communication = getattr(self.controller, 'communication_diagnostics', None)
            snapshot = {'sampled_utc': self._utc(), 'sampled_monotonic': time.monotonic(),
                        'connected': bool(state.get('connected')), 'gui_ready': bool(state.get('gui_ready')),
                        'last_query_id': state.get('last_query_id'),
                        'communication': communication() if communication else {},
                        'read_only': bool(getattr(self.controller, 'read_only', False)),
                        'running': bool(self.controller.running),
                        'native_reads': dict(getattr(self.controller.view, '_read_diagnostics', {})),
                        'native_ticker': dict(getattr(self.controller.view, '_ticker_diagnostics', {}))}
            self._main_snapshot = snapshot
            self._clear_error('sampling')
        except Exception as error:
            self._set_error('sampling', error)

    def _restore_rotation(self):
        """Restore a failed transaction before creating or appending any file."""
        for record in self._rotation_recovery:
            if record['location'] != record['original']:
                record['location'].replace(record['original'])
                record['location'] = record['original']
        self._rotation_recovery = []

    def _rotate(self):
        # Stage current FIRST. A Windows sharing violation must not delete or
        # repeatedly shift archives while current cannot be renamed. Stage all
        # other files before discarding anything, so archive failures can also
        # roll back without losing retained records.
        records = []
        for index in range(self._retained_files):
            source = self.path / ('events.jsonl' if index == 0 else f'events.{index}.jsonl')
            if source.exists():
                records.append({'index': index, 'original': source, 'location': source})
        self._rotation_recovery = records
        try:
            for record in records:
                temporary = self.path / f".events-rotation-{self._identity['session_id']}-{record['index']}.tmp"
                record['location'].replace(temporary)
                record['location'] = temporary
            for record in records:
                if record['index'] < self._retained_files - 1:
                    destination = self.path / f"events.{record['index'] + 1}.jsonl"
                    record['location'].replace(destination)
                    record['location'] = destination
            # At most one oldest file is removed, after all renames succeeded.
            for record in records:
                if record['index'] == self._retained_files - 1:
                    record['location'].unlink()
            self._rotation_recovery = []
        except OSError:
            # If rollback itself is locked, preserve its state and retry it on
            # the next flush; do not accumulate temporary files or overwrite it.
            self._restore_rotation()
            raise
        with self._health_lock:
            self._health['rotations'] += 1

    def _flush(self):
        """One bounded writer pass; failed entries stay queued for retry."""
        deadline = time.monotonic() + self._max_flush_seconds
        processed = 0
        stream = None
        try:
            if self._rotation_recovery:
                self._restore_rotation()
            while processed < self._max_flush_entries and time.monotonic() < deadline:
                if not self._pending:
                    try:
                        self._pending.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
                entry = self._pending[0]
                data = (json.dumps(entry, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8', errors='backslashreplace')
                if stream is None:
                    self.path.mkdir(parents=True, exist_ok=True)
                    stream = (self.path / 'events.jsonl').open('a+b', buffering=0)
                    stream.seek(0, 2)
                size = stream.tell()
                if size and size + len(data) > self._max_file_bytes:
                    stream.close()
                    stream = None
                    self._rotate()
                    stream = (self.path / 'events.jsonl').open('a+b', buffering=0)
                    size = 0
                # A previous interrupted OS write may have left a partial line.
                # Separate it before retrying; seq lets readers suppress repeats.
                if size:
                    stream.seek(-1, 2)
                    terminated = stream.read(1) == b'\n'
                    stream.seek(0, 2)
                    if not terminated:
                        stream.write(b'\n')
                if stream.write(data) != len(data):
                    raise OSError('Incomplete diagnostic event write')
                self._pending.popleft()
                processed += 1
                self._last_event_write = time.monotonic()
                with self._health_lock:
                    self._health['written_events'] += 1
            self._clear_error('event')
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            self._set_error('event', error)
        finally:
            if stream is not None:
                try:
                    stream.close()
                except OSError as error:
                    self._set_error('event', error)
        return processed

    def _logger_snapshot(self, now):
        with self._health_lock:
            return {**self._health, 'queue_depth': self._queue.qsize() + len(self._pending),
                    'queue_capacity': self._queue.maxsize, 'last_event_seq': self._sequence,
                    'errors': dict(self._errors), 'healthy': not self._errors,
                    'max_file_bytes': self._max_file_bytes, 'retained_files': self._retained_files,
                    'last_event_write_age_seconds': None if self._last_event_write is None else max(0., now - self._last_event_write),
                    'last_heartbeat_write_age_seconds': None if self._last_heartbeat_write is None else max(0., now - self._last_heartbeat_write)}

    def _heartbeat(self):
        now = time.monotonic()
        snapshot = self._main_snapshot
        record = {**self._identity, **snapshot,
                  'utc': self._utc(), 'monotonic': now, 'elapsed_seconds': now - self.started,
                  'loops': self.loops, 'main_loop_progress_age_seconds': max(0., now - self.last_tick),
                  'main_snapshot_age_seconds': max(0., now - snapshot.get('sampled_monotonic', self.started)),
                  'writer_progress_age_seconds': max(0., now - self._worker_progress),
                  'last_gui_operation': self.phase, 'closed': self._closed,
                  'logger': self._logger_snapshot(now)}
        # A successful replacement resolves a previous heartbeat write error;
        # do not publish that historical error as a current failure. Its total
        # remains visible in heartbeat_write_failures.
        record['logger']['errors'].pop('heartbeat', None)
        record['logger']['healthy'] = not record['logger']['errors']
        temporary = self.path / 'heartbeat.tmp'
        try:
            self.path.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(record, indent=2, allow_nan=False), encoding='utf-8')
            temporary.replace(self.path / 'heartbeat.json')
            self._last_heartbeat_write = now
            self._clear_error('heartbeat')
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            self._set_error('heartbeat', error)

    def _observe(self):
        last_heartbeat = self.started - self._heartbeat_interval
        while not self._done.wait(self._flush_interval):
            self._worker_progress = time.monotonic()
            try:
                self._flush()
                self._open_stacks()
                self._clear_error('worker')
            except Exception as error:
                self._set_error('worker', error)
            if time.monotonic() - last_heartbeat >= self._heartbeat_interval:
                self._heartbeat()
                last_heartbeat = time.monotonic()
        # Shutdown is also bounded if the disk is unavailable or producers were
        # faster than the writer. Remaining count is preserved in final heartbeat.
        deadline = time.monotonic() + .5
        while time.monotonic() < deadline:
            if not self._flush():
                break
        self._worker_progress = time.monotonic()
        self._heartbeat()
        if self._closed and self._stacks is not None:
            self._stacks.close()

    def close(self):
        if not self.enabled or self._closed:
            return
        self._closed = True
        faulthandler.cancel_dump_traceback_later()
        self.controller.log = self._log
        for name, original in self._hooks:
            setattr(self.controller.view, name, original)
        self._done.set()
        self._thread.join(timeout=1)
        # The daemon may still be in an OS filesystem call. Never close a handle
        # it owns or wait without a bound on the controller's shutdown path.
        if not self._thread.is_alive() and self._stacks is not None:
            self._stacks.close()

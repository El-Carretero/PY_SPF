"""Read one session's saved diagnostics, without importing device or GUI code.

The worker opens files briefly, so Windows rotation is not obstructed by an
idle monitor. snapshot() only copies cached state; it never touches the disk.
"""
from __future__ import annotations
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time


def _reject_constant(value):
    raise ValueError('non-finite JSON number: ' + value)


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _seconds(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return max(0., number) if math.isfinite(number) else None
    except (OverflowError, ValueError):
        return None


def _validate_shape(value):
    """Bound nesting/work before objects enter the GUI-facing cache."""
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 16 or count > 8192:
            raise ValueError('diagnostic JSON nesting/node limit exceeded')
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _utc_seconds(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


class CommunicationMonitor:
    """Bounded incremental reader for an exact, explicitly supplied directory.

    ``start`` is explicit. ``close`` waits at most ``timeout`` seconds; an OS
    filesystem call that stalls cannot hold up the GUI's shutdown. Missing,
    invalid and stale logs do not imply a device failure.
    """
    def __init__(self, session_path, *, max_events=1000, poll_interval=.25,
                 stale_after=3., response_stale_after=10., max_read_bytes=256 * 1024,
                 max_line_bytes=64 * 1024, clock=time.monotonic, wall_clock=time.time):
        self.path = Path(session_path)
        self.max_events = max(1, int(max_events))
        self.poll_interval = max(.01, float(poll_interval))
        self.stale_after = max(.1, float(stale_after))
        self.response_stale_after = max(.1, float(response_stale_after))
        self.max_read_bytes = max(128, int(max_read_bytes))
        self.max_line_bytes = max(128, int(max_line_bytes))
        self._clock, self._wall_clock = clock, wall_clock
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._events = deque(maxlen=self.max_events)
        self._seen_sequences = set()
        self._seen_order = deque()
        self._heartbeat = {}
        self._heartbeat_key = None
        self._heartbeat_timestamp = None
        self._event_identity = None
        self._offset = 0
        self._buffer = b''
        self._discard_line = False
        self._anchor = b''
        self._initialized = False
        self._last_poll = None
        self._last_event_timestamp = None
        self._errors = {}
        self._counters = {'events_read': 0, 'malformed_lines': 0,
                          'malformed_heartbeats': 0, 'read_failures': 0,
                          'rotations': 0, 'truncations': 0, 'duplicate_events': 0,
                          'skipped_initial_bytes': 0, 'lost_rotation_tails': 0,
                          'discarded_partial_lines': 0, 'bytes_read': 0}
        self._cached = self._cache_record()

    def start(self):
        if self._done.is_set():
            return self
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True,
                                                 name='spitfire-log-monitor')
                self._thread.start()
        return self

    def close(self, timeout=1.):
        self._done.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0., float(timeout)))

    @staticmethod
    def _identity(stat):
        return stat.st_dev, stat.st_ino

    def _error(self, area, error):
        self._errors[area] = f'{type(error).__name__}: {error}'[:500]
        self._counters['read_failures'] += 1

    def _read_heartbeat(self):
        path = self.path / 'heartbeat.json'
        try:
            stat = path.stat()
            key = (self._identity(stat), stat.st_mtime_ns, stat.st_size)
            if key == self._heartbeat_key:
                return
            # Remember invalid versions too, so a corrupt unchanging file counts
            # once rather than as a new error every refresh.
            self._heartbeat_key = key
            if stat.st_size > 256 * 1024:
                raise ValueError('heartbeat exceeds 256 KiB limit')
            with path.open('rb') as stream:
                record = json.loads(stream.read(256 * 1024 + 1).decode('utf-8'), parse_constant=_reject_constant)
            if not isinstance(record, dict):
                raise ValueError('heartbeat is not a JSON object')
            _validate_shape(record)
            self._heartbeat = record
            self._heartbeat_timestamp = _utc_seconds(record.get('utc'))
            if self._heartbeat_timestamp is None:
                self._heartbeat_timestamp = stat.st_mtime
            self._errors.pop('heartbeat', None)
        except FileNotFoundError:
            # Starting/opening a panel before the first saved heartbeat is normal.
            self._errors.pop('heartbeat', None)
        except (ValueError, UnicodeError, RecursionError) as error:
            self._counters['malformed_heartbeats'] += 1
            self._error('heartbeat', error)
        except OSError as error:
            self._heartbeat_key = None  # A transient sharing violation is retried.
            self._error('heartbeat', error)

    def _reset_event_file(self, identity, *, initial=False, size=0):
        if self._buffer or self._discard_line:
            self._counters['discarded_partial_lines'] += 1
        self._event_identity = identity
        self._offset = 0
        self._buffer = b''
        self._discard_line = False
        self._anchor = b''
        if initial and size > self.max_read_bytes:
            self._offset = size - self.max_read_bytes
            self._discard_line = True  # Beginning of the selected tail is partial.
            self._counters['skipped_initial_bytes'] += self._offset

    def _old_event_path(self):
        # Only files in the supplied session. Never search adjacent sessions or
        # choose the newest session, which could belong to a self-test process.
        for index in range(1, 33):
            candidate = self.path / f'events.{index}.jsonl'
            try:
                if self._identity(candidate.stat()) == self._event_identity:
                    return candidate
            except FileNotFoundError:
                continue
        return None

    def _consume(self, data):
        self._buffer += data
        lines = self._buffer.split(b'\n')
        self._buffer = lines.pop()
        for line in lines:
            if self._discard_line:
                self._discard_line = False
                continue
            if not line.strip():
                continue
            try:
                if len(line) > self.max_line_bytes:
                    raise ValueError('event line exceeds reader limit')
                record = json.loads(line.decode('utf-8'), parse_constant=_reject_constant)
                if not isinstance(record, dict) or 'kind' not in record or 'payload' not in record:
                    raise ValueError('event is missing kind or payload')
                _validate_shape(record)
            except (ValueError, UnicodeError, RecursionError):
                self._counters['malformed_lines'] += 1
                continue
            sequence = record.get('seq')
            if isinstance(sequence, int):
                key = (str(record.get('session_id', '')), sequence)
                if key in self._seen_sequences:
                    self._counters['duplicate_events'] += 1
                    continue
                self._seen_sequences.add(key)
                self._seen_order.append(key)
                while len(self._seen_order) > self.max_events * 2:
                    self._seen_sequences.discard(self._seen_order.popleft())
            # Bounds are also enforced for logs written by older/other versions.
            record['kind'] = str(record['kind'])[:100]
            record['payload'] = str(record['payload'])[:8192]
            self._events.append(record)
            self._counters['events_read'] += 1
            timestamp = _utc_seconds(record.get('utc'))
            if timestamp is not None:
                self._last_event_timestamp = timestamp
        if len(self._buffer) > self.max_line_bytes:
            if not self._discard_line:
                self._counters['malformed_lines'] += 1
            self._discard_line = True
            self._buffer = b''

    def _read_chunk(self, path, budget):
        """Return whether the selected file's current end was reached."""
        with path.open('rb') as stream:
            # Detect truncation/replacement even when a truncate+rewrite grew
            # past our old offset between polls and retained the same inode.
            if self._anchor and self._offset >= len(self._anchor):
                stream.seek(self._offset - len(self._anchor))
                if stream.read(len(self._anchor)) != self._anchor:
                    self._counters['truncations'] += 1
                    self._reset_event_file(self._event_identity)
            stream.seek(self._offset)
            data = stream.read(budget)
            self._offset += len(data)
            self._counters['bytes_read'] += len(data)
            self._consume(data)
            # Only a small fixed-size anchor, not a second pass through the file.
            stream.seek(max(0, self._offset - 32))
            self._anchor = stream.read(min(32, self._offset))
            return self._offset >= path.stat().st_size

    def _read_events(self):
        current = self.path / 'events.jsonl'
        try:
            stat = current.stat()
            identity = self._identity(stat)
            if not self._initialized:
                self._reset_event_file(identity, initial=True, size=stat.st_size)
                self._initialized = True
            if identity != self._event_identity:
                old = self._old_event_path()
                if old is not None and not self._read_chunk(old, self.max_read_bytes):
                    return
                # Find the remembered file again in case it moved to a higher
                # archive number during the read. Advance only ONE archive at
                # a time; two rotations between polls must not skip the middle.
                old = self._old_event_path() if old is not None else None
                if old is None:
                    self._counters['lost_rotation_tails'] += 1
                    next_index = 32
                else:
                    next_index = int(old.name.split('.')[1]) - 1
                next_identity = identity
                for index in range(next_index, 0, -1):
                    candidate = self.path / f'events.{index}.jsonl'
                    try:
                        next_identity = self._identity(candidate.stat())
                        break
                    except FileNotFoundError:
                        continue
                self._counters['rotations'] += 1
                self._reset_event_file(next_identity)
                return  # A second file is read on the next bounded worker pass.
            if stat.st_size < self._offset:
                self._counters['truncations'] += 1
                self._reset_event_file(identity)
            self._read_chunk(current, self.max_read_bytes)
            self._errors.pop('events', None)
        except FileNotFoundError:
            # There can be a brief gap between rotation and creation of current.
            self._errors.pop('events', None)
        except OSError as error:
            self._error('events', error)

    def _cache_record(self):
        return {'heartbeat': deepcopy(self._heartbeat), 'events': list(self._events),
                'reader_counters': dict(self._counters), 'errors': dict(self._errors),
                '_heartbeat_timestamp': self._heartbeat_timestamp,
                '_event_timestamp': self._last_event_timestamp,
                '_last_poll': self._last_poll}

    def _poll_once(self):
        """Worker-only IO, separate for deterministic fault-injection tests."""
        self._read_heartbeat()
        self._read_events()
        self._last_poll = self._clock()
        cached = self._cache_record()
        with self._lock:
            self._cached = cached

    def _run(self):
        while not self._done.is_set():
            try:
                self._poll_once()
            except Exception as error:
                # Reader bugs or unusual files cannot take down controller tick.
                self._error('reader', error)
                with self._lock:
                    self._cached = self._cache_record()
            self._done.wait(self.poll_interval)

    def snapshot(self):
        """Return cached rows and explicit freshness/device/logging statuses."""
        with self._lock:
            result = deepcopy(self._cached)
        wall_now = self._wall_clock()
        heartbeat_at = result.pop('_heartbeat_timestamp')
        event_at = result.pop('_event_timestamp')
        last_poll = result.pop('_last_poll')
        heartbeat_age = None if heartbeat_at is None else max(0., wall_now - heartbeat_at)
        heartbeat = result['heartbeat']
        communication = _mapping(heartbeat.get('communication'))
        logger = _mapping(heartbeat.get('logger'))
        sample_at = _utc_seconds(heartbeat.get('sampled_utc'))
        sample_age = None if sample_at is None else max(0., wall_now - sample_at)
        last_reply_age = _seconds(communication.get('last_match_age_seconds'))
        last_status_age = _seconds(communication.get('last_status_age_seconds'))
        # Communication ages were sampled on the main thread, not at the later
        # heartbeat disk write. Add time since that actual sample.
        if last_reply_age is not None:
            last_reply_age += sample_age or 0.
        else:
            last_reply_age = None
        if last_status_age is not None:
            last_status_age += sample_age or 0.
        else:
            last_status_age = None
        if result['errors']:
            log_status = 'read_error'
        elif not heartbeat:
            log_status = 'waiting'
        elif heartbeat.get('closed'):
            log_status = 'closed'
        elif heartbeat_age is not None and heartbeat_age > self.stale_after:
            log_status = 'stale'
        elif logger.get('errors') or logger.get('dropped_events', 0):
            log_status = 'degraded'
        else:
            log_status = 'live'
        if log_status in ('waiting', 'stale', 'read_error') or (sample_age is not None and sample_age > self.stale_after):
            device_status = 'unknown'
        elif heartbeat.get('closed') or not heartbeat.get('running', True):
            device_status = 'stopped'
        elif not heartbeat.get('connected'):
            device_status = 'disconnected'
        elif last_reply_age is None:
            device_status = 'waiting_for_reply'
        elif last_reply_age > self.response_stale_after:
            device_status = 'no_recent_reply'
        elif not heartbeat.get('gui_ready'):
            device_status = 'initializing'
        else:
            device_status = 'ready'
        result.update({'session_path': str(self.path), 'status': log_status,
                       'log_status': log_status, 'device_status': device_status,
                       'heartbeat_age_seconds': heartbeat_age,
                       'main_sample_age_seconds': sample_age,
                       'last_reply_age_seconds': last_reply_age,
                       'last_status_age_seconds': last_status_age,
                       'last_event_age_seconds': None if event_at is None else max(0., wall_now - event_at),
                       'reader_progress_age_seconds': None if last_poll is None else max(0., self._clock() - last_poll),
                       'counters': {'reader': result.pop('reader_counters'),
                                    'controller': _mapping(communication.get('controller')),
                                    'transport': _mapping(communication.get('transport')),
                                    'logger': logger}})
        return result


# A short alias is convenient for embedders; both names have identical behavior.
LogMonitor = CommunicationMonitor

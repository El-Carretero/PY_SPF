"""Optional local progress logs and stack traces; never drive the instrument."""
from __future__ import annotations
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


class SessionDiagnostics:
    """Observe the main loop without calling GUI or transport APIs off-thread.

    Call tick after a complete GUI/controller iteration and close after GUI
    teardown. A ten-second gap produces stack traces, including during a modal
    dialog or teardown; it is evidence of the current stack, not a hang verdict.
    """
    def __init__(self, controller, path=None):
        self.enabled = path is not None
        if not self.enabled:
            return
        self.controller = controller
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.started = self.last_tick = time.monotonic()
        self._last_arm = self.started
        self.loops = 0
        self.phase = 'controller.start'
        self._closed = False
        self._queue = queue.SimpleQueue()
        self._done = threading.Event()
        self._hooks = []
        from . import __version__
        self._identity = {'pid': os.getpid(), 'package_version': __version__, 'original_ni_gui_version': '1.6.0',
                          'source_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                            for name in ('native.py', 'native_ticker.py', 'controller.py', 'protocol.py')}}
        self._main_snapshot = {}
        self._sample_main_thread()
        self._events = (self.path / 'events.jsonl').open('a', encoding='utf-8')
        self._stacks = (self.path / 'stacks.txt').open('a', encoding='utf-8')
        self._log = controller.log

        def log(kind, payload):
            self._queue.put({'utc': self._utc(), 'monotonic': time.monotonic(),
                             'kind': kind, 'payload': str(payload)})
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
        faulthandler.dump_traceback_later(10, repeat=True, file=self._stacks)

    @staticmethod
    def _utc():
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

    def tick(self):
        if not self.enabled:
            return
        self.loops += 1
        self.last_tick = time.monotonic()
        self.phase = 'main_loop'
        # Restarting faulthandler creates a watchdog thread. Once a second is
        # enough; doing it for every 5 ms GUI iteration adds unnecessary work.
        if self.last_tick - self._last_arm >= 1:
            self._sample_main_thread()
            faulthandler.dump_traceback_later(10, repeat=True, file=self._stacks)
            self._last_arm = self.last_tick

    def _sample_main_thread(self):
        state = self.controller.state
        communication = getattr(self.controller, 'communication_diagnostics', None)
        self._main_snapshot = {
            'sampled_utc': self._utc(),
            'connected': bool(state.get('connected')), 'gui_ready': bool(state.get('gui_ready')),
            'last_query_id': state.get('last_query_id'),
            'communication': communication() if communication else {},
            'native_reads': dict(getattr(self.controller.view, '_read_diagnostics', {})),
            'native_ticker': dict(getattr(self.controller.view, '_ticker_diagnostics', {})),
        }

    def _flush(self):
        while True:
            try:
                entry = self._queue.get_nowait()
            except queue.Empty:
                break
            self._events.write(json.dumps(entry, ensure_ascii=False) + '\n')
        self._events.flush()

    def _heartbeat(self):
        now = time.monotonic()
        record = {**self._identity, **self._main_snapshot,
                  'utc': self._utc(), 'elapsed_seconds': now - self.started,
                  'loops': self.loops, 'main_loop_progress_age_seconds': now - self.last_tick,
                  'last_gui_operation': self.phase,
                  'read_only': bool(getattr(self.controller, 'read_only', False)),
                  'running': bool(self.controller.running), 'closed': self._closed}
        temporary = self.path / 'heartbeat.tmp'
        temporary.write_text(json.dumps(record, indent=2), encoding='utf-8')
        try:
            temporary.replace(self.path / 'heartbeat.json')
        except OSError:
            pass  # A Windows reader can briefly lock the destination.

    def _observe(self):
        while not self._done.wait(1):
            self._flush()
            self._heartbeat()
        self._flush()
        self._heartbeat()

    def close(self):
        if not self.enabled or self._closed:
            return
        self._closed = True
        faulthandler.cancel_dump_traceback_later()
        self.controller.log = self._log
        for name, original in self._hooks:
            setattr(self.controller.view, name, original)
        self._done.set()
        self._thread.join(timeout=3)
        if not self._thread.is_alive():
            self._events.close()
        self._stacks.close()

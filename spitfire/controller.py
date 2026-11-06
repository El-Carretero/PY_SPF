"""Application controller shared by the native CVI and portable Qt views."""
from __future__ import annotations
from collections import Counter, deque
from pathlib import Path
import math
import re
import select
import time

from .callbacks import SHOW_PANELS, HIDE_PANELS, dispatch, access_level_actions, fault_update_actions
from .decoders import ResponseDecoder, parse_internal_trigger_reply
from .limits import validate_internal_trigger_hz
from .protocol import QUERIES, PacketBuffer, UDPTransport
from .scheduling import (BWD_RESET_TAGS, FAULT_QUERY_TAGS, FAULT_RESET_TAGS,
                         Scheduler, StartupAttempts)
from .settings import AccessKeySequence, read_max_level
from .simulator import SimulatedTransport


def _native_seconds():
    """The original deadlines use time(NULL), with whole-second resolution."""
    return float(int(time.time()))


class Controller:
    def __init__(self, view, *, demo=False, host="10.19.70.13", port=1024,
                 local_port=1024, config=None, data_dir=None, tcp_port=1001,
                 tcp_host="127.0.0.1", clock=time.monotonic, read_only=False,
                 min_request_interval=None):
        self.view = view
        self.clock = clock
        self._ack_clock = clock
        self.demo = demo
        self.read_only = bool(read_only)
        self.min_request_interval = (0.0 if demo else 0.25) if min_request_interval is None else float(min_request_interval)
        if not math.isfinite(self.min_request_interval) or self.min_request_interval < 0:
            raise ValueError("min_request_interval must be finite and nonnegative")
        self.diagnostics = Counter()
        self._closed_transport_diagnostics = Counter()
        self._last_matched_at = None
        self._last_status_at = None
        self._next_send_at = 0.0
        self._inflight_deadline = None
        self._inflight_retries = 0
        self.query_timeout = 0.7
        self.max_query_retries = 2
        self.host, self.port, self.local_port = host, port, local_port
        self.config = config
        self.data_dir = Path(data_dir or Path.cwd())
        self.tcp_port, self.tcp_host = tcp_port, tcp_host
        self.values = {}
        self.attributes = {}
        self.decoder = ResponseDecoder(read=self.read)
        self.state = self.decoder.state
        self.state.update(gAccessLevel=0, evnt_cmt=0, curtain_not_open=1, gui_ready=False)
        self.state.update(internal_trigger_requested_hz=None, internal_trigger_actual_hz=None,
                          internal_trigger_pending=False, internal_trigger_confirmed=False,
                          internal_trigger_result='not_requested')
        self._internal_trigger_readback_request = None
        try:
            self._internal_trigger_fallback = self.view.read(5, 28)
        except (KeyError, AttributeError, TypeError):
            self._internal_trigger_fallback = None
        presentation = getattr(view, "connection_presentation", None)
        self._connection_presentation = presentation() if presentation else None
        self._desired_device_dimming = dict(self._connection_presentation["controls"]) if self._connection_presentation else {}
        self._desired_alarm_attributes = dict(self._connection_presentation["alarm"]) if self._connection_presentation else {}
        self._connection_message = "Waiting for instrument"
        self.scheduler = Scheduler(clock=clock, read_only=self.read_only,
                                   on_event=lambda payload: self.log("QUEUE", payload))
        self.keys = AccessKeySequence()
        self.transport = None
        self.startup = None
        self.running = True
        self.tcp = None
        self.events = deque(maxlen=2000)
        self.last_health = 0.0
        self.last_log = clock()
        self._button_started = None
        self._pending_tcp_events = deque()
        self._opening_deadline = None
        self._next_open_attempt = 0.0
        self._opening_error = None
        self._default_optout_ack_deadline = None
        self._default_optout_ack_timed_out = False
        self._startup_retry_deadline = None
        self._status_requested = False
        self._tick_active = False
        self._last_tick_at = self.clock()
        self._pause_recovery_since = None
        self._pause_probe_sent = False
        self._pause_status_received = False
        self._receive_queue_drained = False

    def communication_diagnostics(self):
        transport = self._closed_transport_diagnostics.copy()
        transport.update(getattr(self.transport, "diagnostics", {}))
        now = self.clock()
        pending = self.scheduler.last_sent if self.scheduler.balance else None
        waiting = [request for queue in (self.scheduler.inside, self.scheduler.outside)
                   for request in queue]
        oldest = min((request.queued_monotonic for request in waiting
                      if request.queued_monotonic is not None), default=None)
        return {"controller": dict(self.diagnostics),
                "transport": dict(transport),
                "pending_tag": self.scheduler.last_sent.tag if self.scheduler.balance and self.scheduler.last_sent else None,
                "pending_request_id": pending.request_id if pending else None,
                "pending_origin": pending.origin if pending else None,
                "pending_batch_id": pending.batch_id if pending else None,
                "pending_wait_seconds": (None if pending is None or pending.queued_monotonic is None
                                         else max(0, now-pending.queued_monotonic)),
                "queue_inside": len(self.scheduler.inside),
                "queue_outside": len(self.scheduler.outside),
                "queue_total": len(waiting),
                "oldest_queued_age_seconds": None if oldest is None else max(0, now-oldest),
                "suppressed_reset_batches": self.scheduler.suppressed_reset_batches,
                "suppressed_fault_batches": self.scheduler.suppressed_fault_batches,
                "suppressed_bwd_reset_batches": self.scheduler.suppressed_bwd_reset_batches,
                "read_only": self.read_only, "min_request_interval": self.min_request_interval,
                "last_match_monotonic": self._last_matched_at,
                "last_match_age_seconds": None if self._last_matched_at is None else max(0, now-self._last_matched_at),
                "last_status_monotonic": self._last_status_at,
                "last_status_age_seconds": None if self._last_status_at is None else max(0, now-self._last_status_at)}

    def read(self, panel, control):
        try:
            value = self.view.read(panel, control)
        except (KeyError, AttributeError, TypeError):
            value = self.values.get((panel, control), 0)
        self.values[panel, control] = value
        return value

    def set_value(self, panel, control, value):
        if panel == 6 and control in (7, 9):
            # Product override: EXT rates share the confirmed TDG frequency
            # input. Keep the recovered XP decoder/callback behavior isolated
            # here so EMP PRF replies and local callbacks cannot replace it.
            actual = self.state['internal_trigger_actual_hz']
            value = 0.0 if actual is None else actual
            if control == 7 and actual is not None:
                divisor = float(self.read(5, 43)) or 1.0
                value = actual / divisor
        self.values[panel, control] = value
        self.decoder.values[panel, control] = value
        self.view.set_value(panel, control, value)
        if (panel, control) == (5, 43):
            self._refresh_external_rates()
        if self._connection_presentation and (panel, control) == (6, 54):
            self._connection_message = str(value)
            self._view_optional("set_connection_status", self.state["gui_ready"], str(value))

    def _refresh_external_rates(self):
        """Show a user-set reference after valid 1053, never measured BNC Hz."""
        unavailable = int(self.state['internal_trigger_actual_hz'] is None)
        for control in (7, 9):
            self.set_value(6, control, 0.0)
            # The ordinary offline presentation still takes precedence. Its
            # desired dimming also keeps an unavailable source disabled when
            # STATUS becomes ready before any valid frequency readback.
            self.set_attribute(6, control, 500, unavailable)

    def set_attribute(self, panel, control, attribute, value):
        if self._connection_presentation:
            if attribute == 500 and (panel, control) in self._desired_device_dimming:
                self._desired_device_dimming[panel, control] = value
                if not self.state["gui_ready"]:
                    value = 1
            if (panel, control) == (6, 50) and attribute in self._desired_alarm_attributes:
                self._desired_alarm_attributes[attribute] = value
                if not self.state["gui_ready"]:
                    value = {500: 0, 641: "NOT CONNECTED", 880: 0xFFFF00}[attribute]
            if panel == 6 and control in (49, 54) and attribute == 530:
                value = 0
        self.attributes[panel, control, attribute] = value
        self.view.set_attribute(panel, control, attribute, value)

    def _set_gui_ready(self, ready):
        self.state["gui_ready"] = bool(ready)
        if not self._connection_presentation:
            return
        for (panel, control), desired in list(self._desired_device_dimming.items()):
            self.set_attribute(panel, control, 500, desired)
        for attribute, desired in list(self._desired_alarm_attributes.items()):
            self.set_attribute(6, 50, attribute, desired)
        self._view_optional("set_connection_status", bool(ready), self._connection_message)

    def log(self, kind, payload):
        self.events.append((self.clock(), kind, payload))
        if hasattr(self.view, "log"):
            self.view.log(f"{kind}: {payload}")

    def _restore_internal_trigger_display(self):
        actual = self.state['internal_trigger_actual_hz']
        previous = self._internal_trigger_fallback if actual is None else actual
        if previous is not None:
            self.set_value(5, 28, previous)

    def _internal_trigger_unconfirmed(self, result, message):
        self.state['internal_trigger_pending'] = False
        self.state['internal_trigger_confirmed'] = False
        self.state['internal_trigger_result'] = result
        self._internal_trigger_readback_request = None
        self._restore_internal_trigger_display()
        self.diagnostics['internal_trigger_unconfirmed'] += 1
        self.log('frequency', message)

    def _internal_trigger_readback(self, actual, *, confirms_request):
        self.state['internal_trigger_actual_hz'] = actual
        self._internal_trigger_fallback = actual
        self._refresh_external_rates()
        if not confirms_request:
            if (not self.state['internal_trigger_pending']
                    and self.state['internal_trigger_confirmed']
                    and actual != self.state['internal_trigger_requested_hz']):
                self.state['internal_trigger_confirmed'] = False
                self.state['internal_trigger_result'] = 'readback_changed'
                self.log('frequency', f'Internal trigger readback changed to {actual:g} Hz; '
                         'previous request is no longer confirmed')
            return
        requested = self.state['internal_trigger_requested_hz']
        confirmed = actual == requested
        self.state['internal_trigger_pending'] = False
        self.state['internal_trigger_confirmed'] = confirmed
        self.state['internal_trigger_result'] = 'confirmed' if confirmed else 'mismatch'
        self._internal_trigger_readback_request = None
        self.log('frequency', f'Internal trigger requested {requested:g} Hz; '
                 f'readback {actual:g} Hz; {"confirmed" if confirmed else "NOT confirmed"}')

    def start(self):
        self.apply(access_level_actions(0))
        self.apply(dispatch("close_curtain"))
        # TCP queries include static version fields and controls which may not
        # receive a device update. Capture actual GUI defaults on the GUI thread.
        import json
        spec_path = Path(__file__).with_name("resources") / "gui_spec.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text())
            for panel in spec["panels"]:
                for control in panel["controls"]:
                    cid = control.get("runtime_id", control["local_index"] + 1)
                    self.read(panel["id"], cid)
        read_attr = getattr(self.view, "read_attribute", None)
        if read_attr:
            for cid in (5, 50):
                self.attributes[6, cid, 500] = read_attr(6, cid, 500)
        if self.tcp_port is not None:
            from .tcp import TCPBridge
            self.tcp = TCPBridge(
                lambda p, c: self.values.get((p, c), 0),
                lambda p, c, a: self.attributes.get((p, c, a), 0),
                state=self.state,
                on_event=lambda k, v: self._pending_tcp_events.append((k, v)),
            )
            try:
                self.tcp.start(self.tcp_host, self.tcp_port)
            except OSError as exc:
                self.log("TCP error", str(exc))
        self.connect()

    def connect(self):
        if self.state['internal_trigger_pending']:
            self._internal_trigger_unconfirmed('reconnected', 'Frequency request unconfirmed before reconnect')
        self.state['internal_trigger_actual_hz'] = None
        self.state['internal_trigger_confirmed'] = False
        self.diagnostics['connect_attempts'] += 1
        if self.diagnostics['connect_attempts'] > 1:
            self.diagnostics['reconnects'] += 1
        if self.transport:
            self._closed_transport_diagnostics.update(getattr(self.transport, "diagnostics", {}))
            self.transport.close()
        self.scheduler.clear(reason="reconnect")
        self._default_optout_ack_deadline = None
        self._default_optout_ack_timed_out = False
        self._startup_retry_deadline = None
        self._status_requested = False
        self._pause_recovery_since = None
        self._pause_probe_sent = False
        self._pause_status_received = False
        self._receive_queue_drained = False
        self._last_status_at = None
        self._inflight_deadline = None
        self._inflight_retries = 0
        self._next_send_at = 0.0
        self.scheduler.hold = True
        self.state["connected"] = False
        self.state["curtain_not_open"] = 1
        self.state["evnt_cmt"] = 0
        self._button_started = None
        self._set_gui_ready(False)
        self._refresh_external_rates()
        self.set_value(6, 30, 0)
        self.apply(dispatch("close_curtain"))
        self.set_value(6, 54, "Loading simulator data, please wait" if self.demo else
                       f"Connecting to {self.host}:{self.port}...")
        self.transport = None
        self.startup = None
        self._opening_deadline = self.clock() + 3.0
        self._next_open_attempt = 0.0
        self._opening_error = None
        self._attempt_open()

    def _attempt_open(self):
        self._next_open_attempt = self.clock() + 0.25
        self.diagnostics['open_attempts'] += 1
        transport = SimulatedTransport() if self.demo else UDPTransport(
            self.host, self.port, self.local_port, timeout=0.0)
        try:
            transport.open()
        except OSError as exc:
            transport.close()
            self.diagnostics['open_errors'] += 1
            self._opening_error = str(exc)
            return False
        self.transport = transport
        self._opening_deadline = None
        self.startup = StartupAttempts()
        self._send_startup(self.startup.begin(self.clock()))
        return True

    def _send_startup(self, request):
        self.diagnostics['startup_attempts'] += 1
        try:
            self._send(request)
        except OSError as exc:
            self.diagnostics['send_errors'] += 1
            self.log("UDP error", f"Startup query send failed: {exc}")

    def _send(self, request, *, retry=False):
        # This is the final authority, including decoder/startup/poll requests.
        # Partial legacy query 1026 and injected multi-line parameters are not
        # exact catalog questions and are intentionally unavailable read-only.
        if self.read_only and (type(request.tag) is not int or request.tag not in QUERIES
                               or not QUERIES[request.tag].endswith('?')
                               or request.parameter
                               or request.message != f'[{request.tag}]{QUERIES[request.tag]}'):
            self.diagnostics['blocked_writes'] += 1
            self.log("read only", f"Blocked {request.tag}")
            if self.scheduler.last_sent is request:
                self.scheduler.finish_current("canceled")
                self._inflight_deadline = None
            return False
        # Set deadlines for every attempt, including a failed sendto. Otherwise
        # an expired retry can be attempted again on every GUI tick.
        now = self.clock()
        self._next_send_at = now + self.min_request_interval
        if self.scheduler.last_sent is request and self.scheduler.balance:
            if not retry:
                self._inflight_retries = 0
            self._inflight_deadline = now + (self.query_timeout if request.tag < 2000 else 1.0)
        packet = PacketBuffer()
        for part in packet.append(request.message):
            self.transport.send_packet(part)
            self.diagnostics['tx_packets'] += 1
        data = packet.flush()
        if data is not None:
            self.transport.send_packet(data)
            self.diagnostics['tx_packets'] += 1
        self.log("TX", request.message)
        self.scheduler.record_sent(request, retry=retry, sent_at=now)
        if request.tag == 1085:
            self._status_requested = True
        if request is self.scheduler.default_optout_write:
            # A missing configuration-write receipt must not strand startup.
            # The original EMPOPTOUT? readback still determines the state.
            self._default_optout_ack_deadline = self._ack_clock() + 1.0
        return True

    def _drain_receive(self):
        # A duplicate may arrive while balance is zero. Drain it before choosing
        # a new request so it cannot become the next request's apparent reply.
        # Bound work per UI tick so malformed traffic cannot freeze the GUI.
        for _ in range(64):
            sock = self.transport.socket
            if sock is not None and not select.select([sock], [], [], 0)[0]:
                return True
            replies = self.transport.receive()
            for reply in replies:
                self._receive(reply.decorated)
            if sock is None and not replies:
                return True
        # Hitting the work limit is not evidence that the old queue is empty.
        # Real sockets can be checked without consuming another datagram; an
        # in-memory transport must return an empty receive on a later tick.
        return sock is not None and not bool(select.select([sock], [], [], 0)[0])

    def _expire_request(self, now):
        if (not self.scheduler.balance or self._inflight_deadline is None
                or now < self._inflight_deadline or now < self._next_send_at):
            return
        request = self.scheduler.last_sent
        safe_query = request.tag in QUERIES and QUERIES[request.tag].endswith('?') and not request.parameter
        if safe_query and self._inflight_retries < self.max_query_retries:
            self._inflight_retries += 1
            self.diagnostics['query_retries'] += 1
            self.log("retry", f"query {request.tag}, attempt {self._inflight_retries + 1}")
            self._send(request, retry=True)
            return
        self.scheduler.finish_current("timeout")
        self._inflight_deadline = None
        key = 'query_timeouts' if request.tag < 2000 else 'write_ack_timeouts'
        self.diagnostics[key] += 1
        self.log("timeout", f"{request.tag}; {'skipped query' if request.tag < 2000 else 'write NOT replayed'}")
        if request is self._internal_trigger_readback_request:
            self._internal_trigger_unconfirmed('readback_timeout', 'Internal trigger frequency readback timed out; setting NOT confirmed')

    def cancel_pending_run(self, reason="RUN cancelled"):
        armed = bool(self.state.get('evnt_cmt') or self._button_started is not None)
        self.state['evnt_cmt'] = 0
        self._button_started = None
        removed = self._remove_queued_writes(lambda request: request.tag == 2027)
        if armed:
            self.diagnostics['cancelled_run_holds'] += 1
        if removed:
            self.diagnostics['cancelled_run_requests'] += removed
        if armed or removed:
            self.log('connection', reason)

    def _remove_queued_writes(self, predicate):
        return self.scheduler.remove_queued(predicate)

    def cancel_pending_actuation(self, reason="Pending writes cancelled"):
        self.cancel_pending_run(reason)
        if self.state['internal_trigger_pending']:
            self._internal_trigger_unconfirmed('cancelled', 'Frequency request unconfirmed: ' + reason)
        removed = self._remove_queued_writes(lambda request: request.tag >= 2000 and not self._shutdown_request(request))
        if removed:
            self.diagnostics['cancelled_write_requests'] += removed
            self.log('connection', reason)

    @staticmethod
    def _shutdown_request(request):
        return request.tag in (2006, 2013, 2016, 2023, 2028) and request.parameter == ''

    def notify_ui_pause(self, reason='GUI pause'):
        self.diagnostics['gui_pause_events'] += 1
        self.cancel_pending_run(reason)
        if self._last_status_at is None:
            # Before the first STATUS, preserve automatic Opt-out initialization.
            # A UI pause is not elapsed time spent waiting in the network loop.
            self.scheduler.last_received = self.clock()
            return
        self.cancel_pending_actuation(reason)
        if self.startup and self.startup.complete and not self.scheduler.hold:
            self._pause_recovery_since = self.clock()
            self._pause_probe_sent = False
            self._pause_status_received = False

    def tick(self):
        # Native menu loops may dispatch a UI-thread timer while a CVI call is
        # active. Never allow that callback to enter a second scheduler tick.
        if self._tick_active:
            self.diagnostics['reentrant_ticks_skipped'] += 1
            return
        self._tick_active = True
        try:
            now = self.clock()
            gap = now-self._last_tick_at
            self._last_tick_at = now
            if gap > 2 and getattr(self.view, 'native_timers', False):
                self.notify_ui_pause('GUI pause: cancelled pending actuation')
            return self._tick_once()
        finally:
            self._tick_active = False

    def _recover_after_pause(self, now):
        if self._pause_recovery_since is None:
            return False
        if self._pause_status_received:
            self._pause_recovery_since = None
            self._pause_probe_sent = False
            self._pause_status_received = False
            self.log('connection', 'GUI pause recovered with a fresh STATUS; no startup replay')
            return False
        if not self._pause_probe_sent:
            if self.state['gui_ready'] or self.state['curtain_not_open'] != 1:
                self.state['curtain_not_open'] = 1
                self._set_gui_ready(False)
                self.apply(dispatch('close_curtain'))
            if not self._receive_queue_drained:
                self.diagnostics['pause_quarantine_wait_ticks'] += 1
                if self.diagnostics['pause_quarantine_wait_ticks'] == 1:
                    self.log('connection', 'GUI pause: draining buffered replies before STATUS probe')
                # Existing deliberate shutdowns do not need a fresh status.
                # Remove before attempting the send: even an uncertain sendto
                # failure must never cause an actuator command to be replayed.
                if now >= self._next_send_at:
                    shutdown = None
                    for queue in (self.scheduler.inside, self.scheduler.outside):
                        shutdown = next((request for request in queue if self._shutdown_request(request)), None)
                        if shutdown is not None:
                            queue.remove(shutdown)
                            break
                    if shutdown is not None:
                        try:
                            if self._send(shutdown):
                                self.diagnostics['quarantine_shutdowns_sent'] += 1
                        except OSError as exc:
                            self.diagnostics['send_errors'] += 1
                            self.log('UDP error', f'Shutdown not replayed: {exc}')
                return True
            shutdowns = [request for queue in (self.scheduler.inside, self.scheduler.outside)
                         for request in queue if self._shutdown_request(request)]
            self.scheduler.clear(reason="gui_pause")
            self._inflight_deadline = None
            self._default_optout_ack_deadline = None
            self._status_requested = False
            self.log('connection', 'GUI resumed: probing STATUS before any reconnect')
            for request in shutdowns:
                self.scheduler.push(request.tag, origin="preserved_shutdown")
            self.scheduler.push(1085, origin="pause_recovery")
            self._pause_probe_sent = True
        try:
            self._expire_request(now)
        except OSError as exc:
            self.diagnostics['send_errors'] += 1
            self.log('UDP error', str(exc))
        if not self.scheduler.balance:
            if not self.scheduler.inside and not self.scheduler.outside:
                self.log('connection', 'STATUS recovery probe failed; automatically reconnecting')
                self.connect()
            elif now >= self._next_send_at:
                request = self.scheduler.next_request(auto_poll=False)
                try:
                    self._send(request)
                except OSError as exc:
                    self.diagnostics['send_errors'] += 1
                    self.log('UDP error', str(exc))
        return True

    def _tick_once(self):
        if not self.running:
            return
        while self._pending_tcp_events:
            kind, payload = self._pending_tcp_events.popleft()
            self.log(kind, payload)
            self._tcp_event(kind, payload)
        if self._opening_deadline is not None:
            if self.clock() < self._opening_deadline:
                if self.clock() >= self._next_open_attempt:
                    self._attempt_open()
            else:
                self._opening_deadline = None
                self.set_value(6, 54, "Com error - cannot open!")
                self.apply(dispatch("close_curtain"))
                self.log("UDP error", self._opening_error or "could not open UDP")
                self._startup_retry_deadline = self.clock() + 2.0
            return
        if self._startup_retry_deadline is not None:
            if self.clock() >= self._startup_retry_deadline:
                self.connect()
            return
        if self.transport:
            self._receive_queue_drained = False
            try:
                self._receive_queue_drained = self._drain_receive()
            except (OSError, ValueError) as exc:
                self.log("UDP error", str(exc))
        if self.startup and not self.startup.complete:
            if self.startup.should_advance(self.clock()) and self.clock() >= self._next_send_at:
                success = self.startup.finish_attempt()
                if not self.startup.complete:
                    self._send_startup(self.startup.begin(self.clock()))
                else:
                    if success:
                        self.scheduler.hold = False
                        self.scheduler.queue_initial()
                        self.scheduler.last_received = self.clock()
                    else:
                        self.scheduler.hold = True
                        self.state["connected"] = False
                        self._startup_retry_deadline = self.clock() + 2.0
                        message = (f"No reply from {self.host}:{self.port}.\n"
                                   "Check connection or use run_demo.bat.")
                        self.set_value(6, 54, message)
                        self.log("connection", message.replace("\n", " "))
            return
        now = self.clock()
        if self.transport and not self.scheduler.hold:
            if self._recover_after_pause(now):
                return
            if (self._default_optout_ack_deadline is not None
                    and self._ack_clock() >= self._default_optout_ack_deadline):
                self._default_optout_ack_deadline = None
                if (self.scheduler.balance
                        and self.scheduler.last_sent is self.scheduler.default_optout_write):
                    self.scheduler.finish_current("timeout")
                    self._inflight_deadline = None
                    self._default_optout_ack_timed_out = True
                    self.diagnostics['write_ack_timeouts'] += 1
                    self.log("connection", "No Opt-out write ACK; checking EMPOPTOUT? readback")
            action = self.scheduler.connection_action()
            if action:
                last = self.scheduler.last_sent
                self.log("connection", f"{action}; last TX={last.tag if last else None}; "
                         f"last RX={self.state.get('last_query_id')}; "
                         f"pending={len(self.scheduler.inside) + len(self.scheduler.outside)}")
                self.state["connected"] = False
                self.state["curtain_not_open"] = 1
                self.state["evnt_cmt"] = 0
                self._button_started = None
                self._status_requested = False
                self._set_gui_ready(False)
                self.apply(dispatch("close_curtain"))
                if action == "reconnect":
                    self.set_value(6, 30, 0)
                    self.log('connection', 'Automatically reconnecting; no modal acknowledgement required')
                self.connect()
                return
            if self.state['gui_ready'] and self._last_status_at is not None and now-self._last_status_at > 30:
                self.diagnostics['status_stale_events'] += 1
                self.state['curtain_not_open'] = 1
                self.cancel_pending_actuation('STALE STATUS: cancelled pending actuation')
                self._set_gui_ready(False)
                self.apply(dispatch('close_curtain'))
                self.log('connection', 'No fresh STATUS for 30 seconds; device controls disabled')
            try:
                self._expire_request(now)
            except OSError as exc:
                self.diagnostics['send_errors'] += 1
                self.log("UDP error", str(exc))
            self.set_value(6, 30, int(bool(self.state.get("connected"))))
            if not self.scheduler.inside and not self.scheduler.outside:
                self.last_health = now
                self._apply_updates(self.decoder.check_health(self.scheduler.access_level))
                self._decoder_effects()
            request = self.scheduler.next_request() if now >= self._next_send_at else None
            if request is not None:
                try:
                    self._send(request)
                except OSError as exc:
                    self._inflight_deadline = now + (self.query_timeout if request.tag < 2000 else 1.0)
                    self.diagnostics['send_errors'] += 1
                    self.log("UDP error", str(exc))
        if self.state.get("evnt_cmt") and not self.scheduler.hold:
            if self._button_started is None:
                self._button_started = now
            self._held_turn_on(now)
        else:
            self._button_started = None
        if not getattr(self.view, "native_timers", False) and now - self.last_log >= 1.0:
            self.last_log = now
            self.handle_callback("tmr_Data_Logger", 0, 15, 6, 64)

    def _receive(self, line):
        self.log("RX", line)
        match = re.search(r"<(\d+)>", line)
        if not match:
            self.diagnostics['malformed_replies'] += 1
            return
        tag = int(match[1])
        payload = line[match.end():]
        confirms_frequency = (tag == 1053 and self.state['internal_trigger_pending']
                              and self.scheduler.last_sent is self._internal_trigger_readback_request)
        if self._pause_recovery_since is not None and not self._pause_probe_sent:
            # Arrival at our event loop after a pause is not proof that the
            # device answered *after* the pause. Drain pre-pause buffered replies
            # before issuing the explicit recovery probe on the same socket.
            self.diagnostics['ignored_replies'] += 1
            self.log('ignored reply', f'Buffered tag {tag} before post-pause STATUS probe')
            return
        if tag == 1085 and (not self._status_requested or not self.startup or not self.startup.complete):
            self.log("connection", "Ignored STATUS before the current initialization requested it")
            self.diagnostics['ignored_replies'] += 1
            return
        if tag == 1085 and payload.strip():
            if (not re.fullmatch(r'\s*\+?\d+(?:\.0+)?\s*', payload)
                    or not 0 <= int(payload.split('.', 1)[0]) <= 0xffffffff):
                self.diagnostics['malformed_replies'] += 1
                return
        if (tag == 2036 and self._default_optout_ack_timed_out
                and (self.scheduler.last_sent is None or self.scheduler.last_sent.tag != 2036
                     or not self.scheduler.balance)):
            # A delayed write receipt must not release the readback's balance.
            self.log("connection", "Ignored late Opt-out write ACK")
            self.diagnostics['ignored_replies'] += 1
            return
        if tag == 1000 and self.startup and not self.startup.complete:
            if self.startup.received or not line[match.end():].strip():
                self.diagnostics['ignored_replies'] += 1
                return
            self.startup.mark_received()
            self.scheduler.last_received = self.clock()
        elif not self.scheduler.acknowledge(tag):
            self.diagnostics['ignored_replies'] += 1
            self.log("ignored reply", f"tag {tag}; pending {self.scheduler.last_sent.tag if self.scheduler.balance and self.scheduler.last_sent else None}")
            return
        self._inflight_deadline = None
        if tag == 2036 and self.scheduler.last_sent is self.scheduler.default_optout_write:
            self._default_optout_ack_deadline = None
        self.diagnostics['matched_replies'] += 1
        self._last_matched_at = self.clock()
        frequency_readback = None
        if tag == 1053:
            try:
                frequency_readback = validate_internal_trigger_hz(parse_internal_trigger_reply(payload))
            except ValueError as exc:
                self.diagnostics['malformed_replies'] += 1
                if not payload.strip():
                    self.diagnostics['empty_replies'] += 1
                if confirms_frequency:
                    self._internal_trigger_unconfirmed('invalid_readback', f'{exc}; setting NOT confirmed')
                else:
                    self.log('frequency', str(exc))
                return
        if not payload.strip():
            self.diagnostics['empty_replies'] += 1
            # Never let the original empty-payload fallback reuse another tag's
            # value (notably the real board's empty HEDOPTOUT response).
            return
        if tag == 1085:
            self._last_status_at = self.clock()
            if self._pause_recovery_since is not None and self._pause_probe_sent:
                self._pause_status_received = True
        updates = self.decoder.decode_line(line)
        if self.read_only and tag == 1085:
            # Original STATUS assumes RES12 is about to turn PC1/2 off. In
            # read-only mode RES12 is suppressed, so keep actual DEL? indicators.
            updates = [u for u in updates if u.attribute is not None or (u.panel_id, u.control_id) not in ((6, 23), (6, 21))]
        self._apply_updates(updates)
        if frequency_readback is not None:
            self._internal_trigger_readback(frequency_readback, confirms_request=confirms_frequency)
        self._decoder_effects()
        if self.state.pop("call_for_reset_c1n2", 0):
            self.scheduler.reset_channels_pending = not self.read_only

    def _tcp_event(self, kind, payload):
        """Original SERVER.UIR connection indicators and receive console."""
        if kind == "listening":
            import socket
            hostname = socket.gethostname()
            try:
                address = socket.gethostbyname(hostname)
            except OSError:
                address = "127.0.0.1"
            self.set_value("server", 6, 1)
            self.set_value("server", 5, 0)
            self.set_value("server", 10, hostname)
            self.set_value("server", 11, address)
            self.set_attribute("server", 3, 500, 1)
        elif kind == "connected":
            import socket
            address = str(payload[0])
            self.set_value("server", 5, 1)
            self.set_value("server", 9, address)
            self.set_value("server", 8, socket.getfqdn(address))
            self.set_value("server", 4, f"-- New connection from {address} --\n")
            self.set_attribute("server", 3, 500, 0)
        elif kind == "refused":
            self.set_value("server", 4, f"-- Refusing conection request from {payload[0]} --\n")
        elif kind == "disconnected":
            self.set_value("server", 5, 0)
            self.set_value("server", 9, "")
            self.set_value("server", 8, "")
            self.set_value("server", 4, "-- Client disconnected --\n")
            self.set_attribute("server", 3, 500, 1)
        elif kind == "received":
            self.set_value("server", 4, str(payload))
        elif kind == "stopped":
            self.set_value("server", 6, 0)

    def _apply_updates(self, updates):
        for update in updates:
            if update.attribute is None:
                self.set_value(update.panel_id, update.control_id, update.value)
            else:
                self.set_attribute(update.panel_id, update.control_id, update.attribute, update.value)

    def _decoder_effects(self):
        for tag, parameter in self.decoder.next_queries:
            if self.read_only and tag >= 2000:
                self.diagnostics['blocked_writes'] += 1
                self.log("read only", f"Blocked automatic {tag}")
            else:
                self.scheduler.push(tag, parameter, origin="decoder")
        for kind, value in self.decoder.effects:
            if kind == "initial_updates":
                self.scheduler.queue_subsystem_initial(value)
            elif kind == "open_curtain":
                self._set_gui_ready(True)
                self.apply(dispatch("open_curtain"))
            elif kind == "connected":
                # Native control 48 is CMBATDEBUG, a readback preference.
                # Connectivity refresh updates its timestamp, never that control.
                self.state["connected"] = bool(value)
            elif kind == "hide_ecu":
                self.apply(dispatch("hide_ecu_controls" if value else "show_ecu_controls"), automatic=True)
            elif kind == "hide_emp":
                self.apply(dispatch("hide_emp_controls" if value else "show_emp_controls"))
            elif kind == "menu_disabled":
                item, disabled = value
                self._view_optional("set_menu_attribute", 6, item, 500, int(disabled))
            elif kind == "fault_update":
                self.apply(fault_update_actions(), automatic=True, origin="health")
            else:
                self.state[kind] = value
        self.decoder.next_queries = []
        self.decoder.effects = []

    def handle_callback(self, name, value=0, event=1, panel=6, control=0):
        frequency_commit = name.lstrip('_') == 'trig_reprate' and event == 1
        readonly_local = (set(SHOW_PANELS) | set(HIDE_PANELS) | {
            'QuitProgram', 'Shutdown', 'exit_from_menu', 'display_faults',
            'cmtRETUSERMODE', 'SetAccessLevel', 'ClearScreenCB', 'MainCallBack',
            'MainPanelCB', 'tmr_Data_Logger', 'set_max_current',
            'Ch1_Coarse_Check_Callback', 'Ch2_Coarse_Check_Callback',
            'SYNC_Coarse_Check_Callback', 'Ch3_Coarse_Check_Callback',
            'Ch4_Coarse_Check_Callback',
        })
        if self.read_only and name.lstrip('_') not in readonly_local:
            if frequency_commit:
                self._restore_internal_trigger_display()
            self.diagnostics['blocked_callbacks'] += 1
            self.log("read only", f"Blocked callback {name}")
            return
        if frequency_commit:
            if self.state['internal_trigger_pending']:
                self._restore_internal_trigger_display()
                self.log('frequency', 'Frequency edit ignored while its readback is pending')
                return
            if (self.state['internal_trigger_actual_hz'] is None
                    or (self._connection_presentation and not self.state['gui_ready'])):
                self._restore_internal_trigger_display()
                self.log('frequency', 'Frequency edit blocked until a valid device frequency readback is available')
                return
        if self._connection_presentation and not self.state["gui_ready"] and name == "tmr_Data_Logger":
            return  # An offline display must not be logged as instrument data.
        if self._connection_presentation and not self.state["gui_ready"] and name.lstrip('_') == 'cllbck':
            self.log("connection", "RUN ignored while waiting for instrument status")
            return  # A queued press must not become an armed RUN after STATUS.
        self.values[panel, control] = value
        if event in (3, 5):
            self.state["left_mouse_down" if event == 3 else "right_mouse_down"] = True
        try:
            actions = dispatch(name, value, read=self.read, event=event,
                               panel=panel, control=control, state=self.state)
            if frequency_commit:
                requested = next(a for a in actions if a.kind == 'command' and a.target == 2032)
                self.state['internal_trigger_requested_hz'] = float(requested.value)
                self.state['internal_trigger_pending'] = True
                self.state['internal_trigger_confirmed'] = False
                self.state['internal_trigger_result'] = 'pending'
                self._restore_internal_trigger_display()
            self.apply(actions, origin=name.lstrip('_'))
            if frequency_commit:
                self._internal_trigger_readback_request = next(
                    request for request in reversed(self.scheduler.inside) if request.tag == 1053)
        except (KeyError, ValueError) as exc:
            if frequency_commit:
                self._restore_internal_trigger_display()
            self.log("callback", str(exc))

    def key_pressed(self, text):
        if text == "\x1b":
            if self.read_only:
                self.log("read only", "Blocked ESC device OFF")
                self.diagnostics['blocked_callbacks'] += 1
                return
            self.apply(dispatch("esc_turnoff", event=1))
        for character in text:
            level = self.keys.feed(character, read_max_level(self.config))
            if level is not None:
                self.apply(access_level_actions(level))

    def mouse_released(self):
        self.state["left_mouse_down"] = False
        self.state["right_mouse_down"] = False
        if self.state.pop("motor_mouse_button", None) is not None:
            self.apply(dispatch("tmr_Mouse_Callback1", event=15, state=self.state))

    def _held_turn_on(self, now):
        if self.read_only or (self._connection_presentation and not self.state["gui_ready"]):
            self.state["evnt_cmt"] = 0
            self._button_started = None
            return
        # Worker 0x406953 compares time(NULL): strictly more than 3 whole
        # seconds, then sends ON, reflects TEC-enable and clears the hold flag.
        if self._button_started is not None and int(now) - int(self._button_started) > 3:
            self.scheduler.push(2027, "", origin="held_run")
            self.set_value(2, 8, 1)
            self.state["evnt_cmt"] = 0
            self._button_started = None

    def apply(self, actions, *, automatic=False, origin=None):
        actions = list(actions)
        origin = origin or ("automatic" if automatic else "action")
        # Recognize whole recovered operations, never individual repeated tags.
        # In particular the intentional second fault-query pass is preserved.
        signature = tuple((action.kind, action.target, action.value or "")
                          for action in actions if action.kind in ("command", "query"))
        batch_kind = None
        for candidate, tags in (("fault_reset", FAULT_RESET_TAGS),
                                ("fault_update", FAULT_QUERY_TAGS),
                                ("bwd_reset", BWD_RESET_TAGS)):
            expected = tuple(("command" if tag >= 2000 else "query", tag, "") for tag in tags)
            if signature == expected:
                batch_kind = candidate
                break
        batch_entries = []
        for action in actions:
            kind, target, value = action.kind, action.target, action.value
            if kind in ("command", "query"):
                if self.read_only and target >= 2000:
                    self.diagnostics['blocked_writes'] += 1
                    self.log("read only", f"Blocked action {target}")
                    continue
                if self._connection_presentation and not self.state["gui_ready"] and not automatic:
                    self.log("connection", f"Control request {target} blocked while waiting for instrument status")
                    continue
                if batch_kind:
                    batch_entries.append((target, value or ""))
                else:
                    self.scheduler.push(target, value or "", origin=origin)
            elif kind == "set":
                self.set_value(*target, value)
            elif kind == "attribute":
                self.set_attribute(*target, value)
            elif kind == "panel_attribute":
                self.view.set_panel_attribute(*target, value)
            elif kind == "panel":
                self.view.show_panel(target, bool(value))
            elif kind == "state":
                self.state[target] = value
                if target == "gAccessLevel":
                    self.scheduler.access_level = int(value)
                elif target == "turn_on_started" and value == "now":
                    self._button_started = self.clock()
            elif kind == "menu_attribute":
                if self._connection_presentation and target == (6, 0, 500):
                    value = 0  # Allow offline navigation; hardware controls remain dimmed.
                self._view_optional("set_menu_attribute", *target, value)
            elif kind == "server_panel":
                self._view_optional("show_server", bool(value))
            elif kind == "append_file":
                self.data_dir.mkdir(parents=True, exist_ok=True)
                with (self.data_dir / Path(target).name).open("a", encoding="ascii") as stream:
                    stream.write(value)
            elif kind == "server_write":
                if self.tcp is not None:
                    self.tcp.send_text(str(value).removesuffix("\n"))
            elif kind == "reset_textbox":
                self.set_value(*target, value or "")
            elif kind == "key_pressed":
                self.key_pressed(str(value))
            elif kind == "reconnect":
                self.connect()
            elif kind == "quit":
                self.running = False
                self._view_optional("request_close")
        if batch_entries:
            if len(batch_entries) == len(signature):
                self.scheduler.queue_batch(batch_kind, batch_entries, origin=origin)
            else:
                # Read-only/offline filtering must not invent a partial Reset
                # batch or let a partial operation suppress a later full one.
                for tag, parameter in batch_entries:
                    self.scheduler.push(tag, parameter, origin=origin)

    def _view_optional(self, name, *args):
        method = getattr(self.view, name, None)
        if method:
            return method(*args)

    def _warn_retry(self, text):
        self.log("Warning", text)
        self._view_optional("show_warning", "Warning", text, self.connect)

    def stop(self):
        if self.state['internal_trigger_pending']:
            self._internal_trigger_unconfirmed('stopped', 'Frequency request unconfirmed when application stopped')
        self.running = False
        self.state["gui_ready"] = False
        self.state["evnt_cmt"] = 0
        self._button_started = None
        self.scheduler.clear(reason="stopped")
        if self.transport:
            self.transport.close()
        if self.tcp:
            self.tcp.stop()

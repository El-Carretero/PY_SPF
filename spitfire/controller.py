"""Application controller shared by the native CVI and portable Qt views."""
from __future__ import annotations
from collections import deque
from pathlib import Path
import re
import select
import time

from .callbacks import dispatch, access_level_actions
from .external_state import ExternalResponseDecoder
from .external_policy import validate_request, is_stop_request, RESET_COMMAND_IDS
from .protocol import PacketBuffer, UDPTransport
from .scheduling import Scheduler, StartupAttempts, Request
from .settings import AccessKeySequence, read_max_level
from .simulator import SimulatedTransport
from .diagnostics import CommunicationLog, notify_observer


class Controller:
    def __init__(self, view, *, demo=False, host="10.19.70.13", port=1024,
                 local_port=1024, config=None, data_dir=None, tcp_port=1001,
                 tcp_host="127.0.0.1", clock=time.monotonic, request_timeout=2.0,
                 diagnostic_config=None):
        self.view = view
        self.clock = clock
        self.demo = demo
        self.host, self.port, self.local_port = host, port, local_port
        self.config = config
        self.data_dir = Path(data_dir or Path.cwd())
        self.tcp_port, self.tcp_host = tcp_port, tcp_host
        self.values = {}
        self.attributes = {}
        if not 0 < request_timeout < 60:
            raise ValueError("Request timeout must be between 0 and 60 seconds")
        self.request_timeout = request_timeout
        self.decoder = ExternalResponseDecoder(read=self.read, clock=clock,
                                               stale_after=max(5.0, request_timeout * 3))
        self.state = self.decoder.state
        self.state.update(gAccessLevel=0, evnt_cmt=0, curtain_not_open=1)
        self.scheduler = Scheduler(clock=clock)
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
        self._opening_error = None
        self._last_hold_tick = None
        self._reply_counts = {}
        self._pc_run = None
        self._pc_running = False
        self._pc_stop = None
        self._stop_required = False
        self._stop_after_connect = False
        self.run_status = "PC output unconfirmed"
        self.state['pc_output_status'] = self.run_status
        self.diagnostics = None
        self._diagnostic_error = None
        self._diagnostic_request_seq = 0
        self._diagnostic_connection = 0
        self._diagnostic_request = {}
        self._diagnostic_reset_seq = 0
        self._diagnostic_resets = {}
        self._diagnostic_snapshot = None
        if diagnostic_config is not None:
            try:
                self.diagnostics = CommunicationLog(diagnostic_config,
                    mode='simulator' if demo else 'udp')
                self._diagnose('controller_config', host=host, port=port,
                               local_port=local_port, request_timeout=request_timeout)
            except Exception as exc:
                self._diagnostic_error = str(exc)
                self.log('diagnostic error', str(exc))

    @property
    def diagnostic_status(self):
        if self.diagnostics is None:
            return dict(enabled=False, error=self._diagnostic_error)
        return dict(enabled=True, **self.diagnostics.status)

    def _diagnose(self, event, **fields):
        if self.diagnostics is not None:
            notify_observer(self.diagnostics.emit, event,
                            connection_id=self._diagnostic_connection, **fields)

    def _transport_event(self, event, **fields):
        # Active request is context only: UDP IDs do not identify transactions.
        self._diagnose(event, mode='simulator' if self.demo else 'udp',
                       active_request_seq=self._diagnostic_request.get('request_seq'), **fields)

    def _observe_state(self):
        if self.diagnostics is None:
            return
        reads, now = self.decoder.readbacks, self.clock()
        snapshot = dict(connected=bool(self.state.get('connected')),
                        fault_reason=reads.fault_reason(now),
                        readbacks={str(tag): dict(value=reads.value(tag), fresh=reads.is_fresh(tag, now))
                                   for tag in (1015, 1019, 1028, 1039, 1066, 1068, 1088, 1089)})
        if snapshot != self._diagnostic_snapshot:
            self._diagnostic_snapshot = snapshot
            self._diagnose('state', **snapshot)

    def _prune_diagnostic_resets(self, reason='removed_from_queue'):
        if not self._diagnostic_resets:
            return
        pending = {id(r) for q in (self.scheduler.inside, self.scheduler.outside, self.scheduler.urgent) for r in q}
        for key in list(self._diagnostic_resets):
            if key not in pending:
                self._diagnose('reset_step_cancelled', reason=reason,
                               **self._diagnostic_resets.pop(key)[1])

    def read(self, panel, control):
        try:
            value = self.view.read(panel, control)
        except (KeyError, AttributeError, TypeError):
            value = self.values.get((panel, control), 0)
        self.values[panel, control] = value
        return value

    def set_value(self, panel, control, value):
        self.values[panel, control] = value
        self.decoder.values[panel, control] = value
        self.view.set_value(panel, control, value)

    def set_attribute(self, panel, control, attribute, value):
        self.attributes[panel, control, attribute] = value
        self.view.set_attribute(panel, control, attribute, value)

    def log(self, kind, payload):
        self.events.append((self.clock(), kind, payload))
        self._diagnose('controller_event', kind=kind, message=str(payload))
        if hasattr(self.view, "log"):
            self.view.log(f"{kind}: {payload}")

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
                external=True,
                external_readbacks=lambda: dict(self.state.get('external_readbacks', {})),
            )
            try:
                self.tcp.start(self.tcp_host, self.tcp_port)
            except OSError as exc:
                self.log("TCP error", str(exc))
        self.connect()

    def connect(self):
        self._diagnose('connection', phase='reconnect_requested' if self.transport else 'connect_requested')
        self._stop_after_connect = bool(self._stop_after_connect or self._stop_required or self._pc_run or self._pc_running or self._pc_stop)
        self.cancel_run_hold()
        self._pc_run = None
        self._pc_running = False
        self._pc_stop = None
        self.decoder.readbacks.clear()
        self._set_run_status("PC output unknown after reconnect")
        if self.transport:
            self.transport.close()
        self.scheduler.clear()
        self._prune_diagnostic_resets('connection_replaced')
        if self._diagnostic_request:
            self._diagnose('request_interrupted', reason='connection_replaced', **self._diagnostic_request)
        self._diagnostic_request = {}
        self._diagnostic_connection += 1
        self.scheduler.last_received = self.clock()
        self.scheduler.hold = True
        self.state["connected"] = False
        self._observe_state()
        self.set_value(6, 54, "Loading data, please wait")
        self.transport = None
        self.startup = None
        self._opening_deadline = self.clock() + 3.0
        self._opening_error = None
        self._attempt_open()

    def _attempt_open(self):
        transport = SimulatedTransport() if self.demo else UDPTransport(
            self.host, self.port, self.local_port, timeout=0.0)
        if self.diagnostics is not None:
            transport.observer = self._transport_event
        try:
            transport.open()
        except OSError as exc:
            transport.close()
            self._opening_error = str(exc)
            self._diagnose('connection', phase='open_failed', error=str(exc))
            return False
        self.transport = transport
        if self._stop_after_connect:
            # An interrupted RUN/STOP keeps its OFF obligation across socket
            # replacement. Cleanup does not wait for the identity handshake.
            self._stop_after_connect = False
            self._opening_deadline = None
            self.startup = StartupAttempts(complete=True)
            self.scheduler.hold = False
            self.scheduler.queue_initial()
            self.request_pc_stop()
            return True
        self.startup = StartupAttempts()
        try:
            self._send(self.startup.begin(self.clock()))
        except OSError as exc:
            self._diagnose('request_send_failed', reason=str(exc), **self._diagnostic_request)
            transport.close()
            self.transport = None
            self.startup = None
            self._opening_error = str(exc)
            return False
        self._opening_deadline = None
        return True

    def _send(self, request):
        # Recheck policy and live conditions at the last point before transport.
        if self.diagnostics is not None:
            self._diagnostic_request_seq += 1
            self._diagnostic_request = dict(request_seq=self._diagnostic_request_seq,
                request_id=request.tag, command=request.message,
                **self._diagnostic_resets.pop(id(request), (None, {}))[1])
            self._diagnose('request_attempt', **self._diagnostic_request)
        self._validate_write(request.tag, request.parameter, sequence_step=True)
        self.transport.discard_pending()
        packet = PacketBuffer()
        for part in packet.append(request.message):
            self.transport.send_packet(part)
        data = packet.flush()
        if data is not None:
            self.transport.send_packet(data)
        self.log("TX", request.message)
        self._diagnose('request_sent', **self._diagnostic_request)
        if request.tag == 2019:
            channel, setting = request.parameter.strip().upper().split()
            channel = int(channel)
            query = 1044 + channel
            if setting == 'ON' and self._pc_run is not None and channel == self._pc_run['channel']:
                self._pc_run.update(sent_at=self.clock(), baseline=self._reply_counts.get(query, 0))
            if setting == 'OFF' and self._pc_stop is not None and channel in (1, 2):
                self._pc_stop['sent'][channel] = self._reply_counts.get(query, 0)

    def tick(self):
        if not self.running:
            return
        self._prune_diagnostic_resets()
        now = self.clock()
        if self.state.get('evnt_cmt') and self._last_hold_tick is not None and now - self._last_hold_tick > 0.5:
            self.cancel_run_hold()
        if self.state.get('evnt_cmt'):
            self._last_hold_tick = now
        while self._pending_tcp_events:
            kind, payload = self._pending_tcp_events.popleft()
            self.log(kind, payload)
            self._tcp_event(kind, payload)
        if self._opening_deadline is not None:
            if self.clock() < self._opening_deadline:
                self._attempt_open()
            else:
                self._opening_deadline = None
                self.set_value(6, 54, "Com error - cannot open!")
                self.apply(dispatch("close_curtain"))
                self.log("UDP error", self._opening_error or "could not open UDP")
            return
        waiting_startup = self.startup is not None and not self.startup.complete
        if self.transport and (waiting_startup or self.scheduler.balance > 0):
            try:
                sock = self.transport.socket
                ready = sock is None or bool(select.select([sock], [], [], 0)[0])
                if ready:
                    for reply in self.transport.receive():
                        self._receive(reply.decorated)
            except (OSError, ValueError) as exc:
                self.log("UDP error", str(exc))
        if self.startup and not self.startup.complete:
            if self.startup.should_advance(self.clock()):
                self._diagnose('startup_result', attempt=self.startup.attempts,
                               outcome='reply' if self.startup.received else 'timeout',
                               **self._diagnostic_request)
                self._diagnostic_request = {}
                success = self.startup.finish_attempt()
                if not self.startup.complete:
                    try:
                        self._send(self.startup.begin(self.clock()))
                    except OSError as exc:
                        self._diagnose('request_send_failed', reason=str(exc), **self._diagnostic_request)
                        self.log('UDP error', str(exc))
                else:
                    self.scheduler.hold = False
                    if success:
                        self.scheduler.queue_initial()
                        self.scheduler.last_received = self.clock()
                    else:
                        self.set_value(6, 54, "No controller reply; retrying read-only")
            return
        now = self.clock()
        if (self.scheduler.balance and self.scheduler.last_sent_at is not None
                and now - self.scheduler.last_sent_at >= self.request_timeout):
            failed = self.scheduler.abandon_inflight()
            self._request_failed(failed, "response timeout")
        self._advance_pc_operation(now)
        self._refresh_external_state(now)
        if self.transport and not self.scheduler.hold:
            action = self.scheduler.connection_action()
            if action:
                self.log("connection", action)
                self.state["connected"] = False
                if action == "reconnect":
                    self.set_value(6, 30, 0)
                    if not self.state.get("pardon_first_time_user", 1):
                        self.set_value(6, 54, "Failed to connect to remote system!")
                        self.scheduler.hold = True
                        self._warn_retry("Remote system not responding, click OK to retry")
                        return
                self.connect()
                return
            self.set_value(6, 30, int(self.decoder.readbacks.link_fresh(now)))
            if not self.scheduler.inside and not self.scheduler.outside and not self.scheduler.urgent:
                self.last_health = now
                self._apply_updates(self.decoder.check_health(self.scheduler.access_level))
                self._decoder_effects()
            request = self.scheduler.next_request()
            if request is not None:
                try:
                    self._send(request)
                except (OSError, PermissionError, ValueError) as exc:
                    self.scheduler.abandon_inflight()
                    self._request_failed(request, str(exc))
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
            self._diagnose('response', line=line, disposition='missing_id')
            return
        tag = int(match[1])
        payload = line[match.end():]
        if tag == 1000 and self.startup and not self.startup.complete:
            self._diagnose('response', line=line, response=payload,
                           disposition='startup_accepted' if payload.strip() else 'startup_empty',
                           **self._diagnostic_request)
            if payload.strip():
                self.startup.mark_received()
                self.scheduler.acknowledge(tag)
            return
        request = self.scheduler.last_sent
        if not self.scheduler.balance or request is None or request.tag != tag:
            self._diagnose('response', line=line, request_id=tag, response=payload, disposition='unmatched',
                           active_request_seq=self._diagnostic_request.get('request_seq'))
            self.log('ignored response', str(tag))
            return
        self.scheduler.acknowledge(tag)
        if tag >= 2000:
            rejected = bool(re.search(r'\b(?:ERROR|ERR|NACK|FAIL|INVALID|UNKNOWN)\b', payload, re.I))
            self._diagnose('response', line=line, response=payload,
                           disposition='rejected' if rejected else 'ack', **self._diagnostic_request)
            if 'reset_id' in self._diagnostic_request and not rejected:
                self._diagnose('reset_step_result', outcome='ack',
                               **self._diagnostic_request)
            if re.search(r'\b(?:ERROR|ERR|NACK|FAIL|INVALID|UNKNOWN)\b', payload, re.I):
                self._request_failed(request, 'device rejected command: ' + payload)
            else:
                self._queue_readbacks(request)
            self._diagnostic_request = {}
            return
        self._apply_updates(self.decoder.decode_line(line))
        self._diagnose('response', line=line, response=payload,
                       disposition='valid_readback' if self.decoder.last_valid else 'invalid_readback',
                       **self._diagnostic_request)
        if self.decoder.last_valid:
            self._reply_counts[tag] = self._reply_counts.get(tag, 0) + 1
        else:
            self._request_failed(request, 'invalid or empty readback')
        self._decoder_effects()
        self._observe_state()
        self._diagnostic_request = {}

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
            self.scheduler.push(tag, parameter)
        for kind, value in self.decoder.effects:
            if kind == "initial_updates":
                self.scheduler.queue_subsystem_initial(value)
            elif kind == "open_curtain":
                self.apply(dispatch("open_curtain"))
            elif kind == "connected":
                # Native control 48 is CMBATDEBUG, a readback preference.
                # Connectivity refresh updates its timestamp, never that control.
                self.state["connected"] = bool(value)
                if value and self.state.get('curtain_not_open'):
                    self.apply(dispatch('open_curtain'))
                    self.state['curtain_not_open'] = 0
            elif kind == "hide_ecu":
                self.apply(dispatch("hide_ecu_controls" if value else "show_ecu_controls"))
            elif kind == "hide_emp":
                self.apply(dispatch("hide_emp_controls" if value else "show_emp_controls"))
            elif kind == "menu_disabled":
                item, disabled = value
                self._view_optional("set_menu_attribute", 6, item, 500, int(disabled))
            elif kind == "fault_update":
                for tag in (1089, 1088, 1066, 1057):
                    self.scheduler.push(tag)
            else:
                self.state[kind] = value
        self.decoder.next_queries = []
        self.decoder.effects = []

    def handle_callback(self, name, value=0, event=1, panel=6, control=0):
        name = name.lstrip('_')
        self.values[panel, control] = value
        if event in (3, 5):
            self.state["left_mouse_down" if event == 3 else "right_mouse_down"] = True
        try:
            if name == 'cancel_run_hold':
                self.cancel_run_hold()
                return
            if name == 'cllbck':
                if event == 3:
                    self._button_started = self.clock()
                    self._last_hold_tick = self.clock()
                    self.state['evnt_cmt'] = 1
                elif event == 1:
                    self.cancel_run_hold()
                return
            if name == 'parse_command5':
                if event == 3:
                    self.request_pc_stop()
                return
            if name == 'esc_turnoff':
                self.request_pc_stop()
                return
            if name in ('apply_external_optout', 'empoweroptoutcall'):
                if event == 1:
                    if name == 'empoweroptoutcall' and int(value) != 1:
                        raise PermissionError('External pump opt-out cannot be disabled')
                    self._enqueue(2036, ' 1')
                return
            if name == 'external_hv_off':
                self.request_pc_stop()
                self.scheduler.push_urgent(2016)
                return
            if name == 'cllbckcmd_reset':
                if event == 1:
                    self._diagnostic_reset_seq += 1
                    reset_id = f'reset-{self._diagnostic_reset_seq}'
                    self._diagnose('reset_requested', reset_id=reset_id,
                                   command_ids=list(RESET_COMMAND_IDS))
                    self.cancel_run_hold()
                    if self._pc_run or self._pc_running or self._pc_stop:
                        self._diagnose('reset_blocked', reset_id=reset_id, reason='PC operation active')
                        raise PermissionError('Complete PC STOP before resetting faults')
                    for step, tag in enumerate(RESET_COMMAND_IDS, 1):
                        try:
                            request = self._enqueue(tag)
                        except (ValueError, PermissionError) as exc:
                            self._diagnose('reset_blocked', reset_id=reset_id, step=step, reason=str(exc))
                            raise
                        if self.diagnostics is not None:
                            metadata = dict(reset_id=reset_id, reset_step=step)
                            # Retain the object until sent/pruned so Python id
                            # reuse cannot attribute another request to Reset.
                            self._diagnostic_resets[id(request)] = (request, metadata)
                            self._diagnose('reset_step_queued', request_id=tag, **metadata)
                return
            if name == 'tmr_Data_Logger':
                if event == 15 and self.read(1, 3):
                    self._log_external_readbacks()
                return
            actions = dispatch(name, value, read=self.read, event=event,
                               panel=panel, control=control, state=self.state)
            self.apply(actions)
        except (KeyError, ValueError, PermissionError) as exc:
            self.log("callback", str(exc))
            self._view_optional('set_external_status', str(exc))

    def key_pressed(self, text):
        if text == "\x1b":
            self.request_pc_stop()
        for character in text:
            level = self.keys.feed(character, read_max_level(self.config))
            if level is not None:
                self.apply(access_level_actions(level))

    def mouse_released(self):
        self.cancel_run_hold()
        self.state["left_mouse_down"] = False
        self.state["right_mouse_down"] = False
        if self.state.pop("motor_mouse_button", None) is not None:
            self.apply(dispatch("tmr_Mouse_Callback1", event=15, state=self.state))

    def _held_turn_on(self, now):
        if self._button_started is not None and now - self._button_started >= 3.0:
            self.cancel_run_hold()
            try:
                self.request_pc_run()
            except (PermissionError, ValueError) as exc:
                self._set_run_status(str(exc))

    def cancel_run_hold(self):
        self.state['evnt_cmt'] = 0
        self._button_started = None
        self._last_hold_tick = None

    def _validate_write(self, tag, parameter='', *, sequence_step=False):
        validate_request(tag, parameter)
        if tag < 2000 or is_stop_request(tag, parameter):
            return
        if self._pc_stop is not None or self._stop_required:
            raise PermissionError('Wait for PC STOP readback confirmation')
        if self._pc_run is not None:
            expected = f"{self._pc_run['channel']} ON"
            if tag != 2019 or ' '.join(parameter.strip().upper().split()) != expected:
                raise PermissionError('Wait for PC RUN confirmation before other writes')
        if tag in (2036, 2030, 2031, 2020, 2032, 2046):
            reason = self.decoder.readbacks.hv_off_reason(self.clock())
            if reason:
                raise PermissionError(reason)
        if tag == 2017 or tag == 2048:
            reason = self.decoder.readbacks.enable_block_reason(self.clock())
            if reason:
                raise PermissionError(reason)
        if tag == 2019 and parameter.strip().upper().endswith(' ON'):
            channel = int(parameter.strip().split()[0])
            if channel in (1, 2) and (not sequence_step or self._pc_run is None or self._pc_run['channel'] != channel):
                raise PermissionError('Use PC RUN for the PC1/PC2 sequence')
            reason = self.decoder.readbacks.gate_reason(self.clock(), require_off=False)
            if reason:
                raise PermissionError(reason)
            channel_state = self.decoder.readbacks.value(1044 + channel)
            if (not self.decoder.readbacks.is_fresh(1044 + channel, self.clock())
                    or not getattr(channel_state, 'bwd', False) or not getattr(channel_state, 'enabled', False)):
                raise PermissionError(f'PC{channel} BWD and enable gating must be freshly confirmed')
            if channel == 2 and any(self.decoder.readbacks.channel_on(ch, self.clock()) is not False for ch in (1, 2)):
                raise PermissionError('Both PC channels must still be OFF before PC2 ON')
            if channel == 1 and self.decoder.readbacks.channel_on(2, self.clock()) is not True:
                raise PermissionError('PC2 must still be confirmed ON before PC1 ON')

    def _enqueue(self, tag, parameter=''):
        self._validate_write(tag, parameter)
        if is_stop_request(tag, parameter):
            if self._pc_run or self._pc_running:
                self.request_pc_stop()
            return self.scheduler.push_urgent(tag, parameter)
        return self.scheduler.push(tag, parameter)

    def _set_run_status(self, text):
        self.run_status = text
        self.state['pc_output_status'] = text
        self._diagnose('pc_operation', status=text)
        self._view_optional('set_external_status', text)

    def request_pc_run(self):
        if self._stop_required:
            raise PermissionError('PC STOP must be confirmed before RUN')
        if self._pc_run or self._pc_running or self._pc_stop:
            raise PermissionError('Finish the current PC operation before RUN')
        if not self.state.get('connected'):
            raise PermissionError('Controller is not connected')
        if any(r.tag >= 2000 for q in (self.scheduler.inside, self.scheduler.outside, self.scheduler.urgent) for r in q):
            raise PermissionError('Wait for pending writes before RUN')
        if self.scheduler.balance and self.scheduler.last_sent.tag >= 2000:
            raise PermissionError('Wait for the current write before RUN')
        reason = self.decoder.readbacks.run_block_reason(self.clock())
        if reason:
            raise PermissionError(reason)
        self._pc_run = dict(channel=2, sent_at=None, baseline=0)
        self.scheduler.push(2019, ' 2 ON')
        self._set_run_status('PC RUN pending: waiting for PC2 ON readback')

    def request_pc_stop(self):
        self.cancel_run_hold()
        self._pc_run = None
        self._pc_running = False
        self._stop_required = True
        if self.startup is not None and not self.startup.complete:
            # STOP must not wait through three identity timeouts.
            self.startup.complete = True
            self.scheduler.hold = False
            self.scheduler.queue_initial()
        elif self.transport is None:
            self._stop_after_connect = True
        if self._pc_stop is None:
            self._pc_stop = dict(sent={}, deadline=self.clock() + self.request_timeout * 8)
            self.scheduler.queue_stop()
        self._set_run_status('PC STOP pending: PC1 and PC2 OFF requested')

    def _abort_run(self, reason):
        self.request_pc_stop()
        self._set_run_status('PC RUN aborted; stopping both channels: ' + reason)

    def _advance_pc_operation(self, now):
        operation = self._pc_run
        if operation:
            reason = self.decoder.readbacks.gate_reason(now, require_off=False)
            if reason:
                self._abort_run(reason)
            elif operation['sent_at'] is not None:
                query = 1044 + operation['channel']
                if self._reply_counts.get(query, 0) > operation['baseline']:
                    if self.decoder.readbacks.channel_on(operation['channel'], now) is not True:
                        self._abort_run('PC ON readback does not match')
                    elif operation['channel'] == 2:
                        self._pc_run = dict(channel=1, sent_at=None, baseline=0)
                        self.scheduler.push(2019, ' 1 ON')
                        self._set_run_status('PC2 ON confirmed; waiting for PC1 ON readback')
                    else:
                        self._pc_run = None
                        self._pc_running = True
                        self._set_run_status('PC RUN confirmed (optical output is not measured)')
                elif now - operation['sent_at'] >= self.request_timeout * 3:
                    self._abort_run('PC ON readback deadline expired')
        if self._pc_running:
            reason = self.decoder.readbacks.gate_reason(now, require_off=False)
            if reason or any(self.decoder.readbacks.channel_on(ch, now) is not True for ch in (1, 2)):
                self._abort_run(reason or 'PC readback no longer confirms ON')
        stop = self._pc_stop
        if stop:
            confirmed = all(ch in stop['sent'] and self._reply_counts.get(1044 + ch, 0) > stop['sent'][ch]
                            and self.decoder.readbacks.channel_on(ch, now) is False for ch in (1, 2))
            if confirmed:
                self._pc_stop = None
                self._stop_required = False
                self._set_run_status('PC STOP confirmed: PC1 and PC2 OFF')
            elif now >= stop['deadline']:
                self._pc_stop = None
                self._set_run_status('PC STOP unverified: missing or mismatched OFF readback')

    def _queue_readbacks(self, request):
        tag = request.tag
        mapping = {2016:(1021,), 2017:(1021,), 2022:(1028,), 2023:(1028,),
                   2036:(1068,), 2030:(1050,), 2031:(1051,), 2020:(1025,),
                   2032:(1053,), 2046:(1065,), 2025:(1040,), 2026:(1041,),
                   2021:(1032,), 2014:(1060,), 2029:(1044,), 2053:(1087,),
                   2024:(1033,), 2035:(1069,), 2048:(1080,)}
        ids = mapping.get(tag, ())
        if tag == 2019:
            ids = (1044 + int(request.parameter.strip().split()[0]),)
        elif tag in RESET_COMMAND_IDS:
            ids = (1066, 1088, 1089, 1021, 1045, 1046)
        # Place readbacks before ordinary queued work; urgent OFF still wins.
        for query in reversed(ids):
            readback = Request(query)
            self.scheduler.inside.appendleft(readback)
            if self.diagnostics is not None and 'reset_id' in self._diagnostic_request:
                metadata = {
                    key: self._diagnostic_request[key] for key in ('reset_id', 'reset_step')}
                metadata['readback_for_request_seq'] = self._diagnostic_request['request_seq']
                self._diagnostic_resets[id(readback)] = (readback, metadata)
        self._diagnose('readbacks_queued', query_ids=list(ids), **self._diagnostic_request)

    def _request_failed(self, request, reason):
        if request is None:
            return
        self._diagnose('request_failed', reason=reason,
                       outcome='timeout' if reason == 'response timeout' else 'failed',
                       **self._diagnostic_request)
        if 'reset_id' in self._diagnostic_request and request.tag in RESET_COMMAND_IDS:
            self._diagnose('reset_step_result', outcome='failed', reason=reason,
                           **self._diagnostic_request)
        self.log('request failed', f'{request.tag}: {reason}')
        if request.tag < 2000:
            self.decoder.readbacks.invalidate(request.tag)
        else:
            self._queue_readbacks(request)
        self._diagnostic_request = {}
        if self._pc_run:
            self._abort_run(reason)
        # A failed first OFF must not cancel the other queued OFF.

    def _refresh_external_state(self, now):
        reads = self.decoder.readbacks
        self.state['connected'] = reads.link_fresh(now)
        self.state['external_readbacks'] = {tag: value for tag, value in reads.values.items() if reads.is_fresh(tag, now)}
        # Fault UI/TCP reflect independent subsystem health, never EMP status.
        self._apply_updates(self.decoder.check_health(self.scheduler.access_level))
        self._decoder_effects()
        self._observe_state()
        if not self._pc_run and not self._pc_stop and not self._pc_running:
            if self.run_status in ('PC output unconfirmed', 'PC output unknown after reconnect') or self.run_status.startswith('PC readback:'):
                channels = [reads.channel_on(ch, now) for ch in (1, 2)]
                labels = ['unknown' if value is None else 'ON' if value else 'OFF' for value in channels]
                self.run_status = f'PC readback: PC1 {labels[0]}, PC2 {labels[1]}'
                self.state['pc_output_status'] = self.run_status
            reason = reads.run_block_reason(now)
            if self._stop_required:
                reason = 'PC STOP is unverified; request STOP again and wait for both OFF readbacks'
            self._view_optional('set_external_status', self.run_status + (' | ' + reason if reason else ' | Ready for PC RUN'))

    def _log_external_readbacks(self):
        import csv
        from datetime import datetime, timezone
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / 'external_datalog.csv'
        new = not path.exists()
        snapshot = self.state.get('external_readbacks', {})
        with path.open('a', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            if new:
                writer.writerow(('utc_time', 'hv_enabled', 'hv1_kV', 'hv2_kV', 'crystal_C', 'humidity_percent', 'pc_status'))
            writer.writerow((datetime.now(timezone.utc).isoformat(), *(snapshot.get(tag, '') for tag in (1021,1042,1043,1030,1031)), self.run_status))

    def apply(self, actions):
        actions = list(actions)
        try:
            for action in actions:
                if action.kind in ('command', 'query'):
                    self._validate_write(action.target, action.value or '')
        except (ValueError, PermissionError) as exc:
            self.log('blocked action', str(exc))
            return
        for action in actions:
            kind, target, value = action.kind, action.target, action.value
            if kind in ("command", "query"):
                self._enqueue(target, value or "")
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

    def _view_optional(self, name, *args):
        method = getattr(self.view, name, None)
        if method:
            return method(*args)

    def _warn_retry(self, text):
        self.log("Warning", text)
        self._view_optional("show_warning", "Warning", text, self.connect)

    def stop(self):
        if not self.running and self.diagnostics is not None and self.diagnostics.status['closed']:
            return
        self.running = False
        if self.transport:
            self.transport.close()
        if self.tcp:
            self.tcp.stop()
        self._diagnose('connection', phase='stopped')
        for _, metadata in self._diagnostic_resets.values():
            self._diagnose('reset_step_cancelled', reason='controller_stopped', **metadata)
        self._diagnostic_resets.clear()
        if self._diagnostic_request:
            self._diagnose('request_interrupted', reason='controller_stopped', **self._diagnostic_request)
            self._diagnostic_request = {}
        if self.diagnostics is not None:
            self.diagnostics.close()

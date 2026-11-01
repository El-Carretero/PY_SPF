"""Application controller shared by the native CVI and portable Qt views."""
from __future__ import annotations
from collections import deque
from pathlib import Path
import re
import select
import time

from .callbacks import dispatch, access_level_actions, fault_update_actions
from .decoders import ResponseDecoder
from .protocol import PacketBuffer, UDPTransport
from .scheduling import Scheduler, StartupAttempts
from .settings import AccessKeySequence, read_max_level
from .simulator import SimulatedTransport


def _native_seconds():
    """The original deadlines use time(NULL), with whole-second resolution."""
    return float(int(time.time()))


class Controller:
    def __init__(self, view, *, demo=False, host="10.19.70.13", port=1024,
                 local_port=1024, config=None, data_dir=None, tcp_port=1001,
                 tcp_host="127.0.0.1", clock=_native_seconds):
        self.view = view
        self.clock = clock
        # Preserve original whole-second scheduling, but measure the added
        # optional-ACK grace with a full monotonic second in real execution.
        # An injected test clock controls both deadlines deterministically.
        self._ack_clock = time.monotonic if clock is _native_seconds else clock
        self.demo = demo
        self.host, self.port, self.local_port = host, port, local_port
        self.config = config
        self.data_dir = Path(data_dir or Path.cwd())
        self.tcp_port, self.tcp_host = tcp_port, tcp_host
        self.values = {}
        self.attributes = {}
        self.decoder = ResponseDecoder(read=self.read)
        self.state = self.decoder.state
        self.state.update(gAccessLevel=0, evnt_cmt=0, curtain_not_open=1, gui_ready=False)
        presentation = getattr(view, "connection_presentation", None)
        self._connection_presentation = presentation() if presentation else None
        self._desired_device_dimming = dict(self._connection_presentation["controls"]) if self._connection_presentation else {}
        self._desired_alarm_attributes = dict(self._connection_presentation["alarm"]) if self._connection_presentation else {}
        self._connection_message = "Waiting for instrument"
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
        self._default_optout_ack_deadline = None
        self._default_optout_ack_timed_out = False
        self._startup_retry_deadline = None
        self._status_requested = False

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
        if self._connection_presentation and (panel, control) == (6, 54):
            self._connection_message = str(value)
            self._view_optional("set_connection_status", self.state["gui_ready"], str(value))

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
        if self.transport:
            self.transport.close()
        self.scheduler.clear()
        self._default_optout_ack_deadline = None
        self._default_optout_ack_timed_out = False
        self._startup_retry_deadline = None
        self._status_requested = False
        self.scheduler.hold = True
        self.state["connected"] = False
        self.state["curtain_not_open"] = 1
        self.state["evnt_cmt"] = 0
        self._button_started = None
        self._set_gui_ready(False)
        self.set_value(6, 30, 0)
        self.apply(dispatch("close_curtain"))
        self.set_value(6, 54, "Loading simulator data, please wait" if self.demo else
                       f"Connecting to {self.host}:{self.port}...")
        self.transport = None
        self.startup = None
        self._opening_deadline = self.clock() + 3.0
        self._opening_error = None
        self._attempt_open()

    def _attempt_open(self):
        transport = SimulatedTransport() if self.demo else UDPTransport(
            self.host, self.port, self.local_port, timeout=0.0)
        try:
            transport.open()
        except OSError as exc:
            transport.close()
            self._opening_error = str(exc)
            return False
        self.transport = transport
        self._opening_deadline = None
        self.startup = StartupAttempts()
        self._send(self.startup.begin(self.clock()))
        return True

    def _send(self, request):
        packet = PacketBuffer()
        for part in packet.append(request.message):
            self.transport.send_packet(part)
        data = packet.flush()
        if data is not None:
            self.transport.send_packet(data)
        self.log("TX", request.message)
        if request.tag == 1085:
            self._status_requested = True
        if request is self.scheduler.default_optout_write:
            # A missing configuration-write receipt must not strand startup.
            # The original EMPOPTOUT? readback still determines the state.
            self._default_optout_ack_deadline = self._ack_clock() + 1.0

    def tick(self):
        if not self.running:
            return
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
        if self._startup_retry_deadline is not None:
            if self.clock() >= self._startup_retry_deadline:
                self.connect()
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
                success = self.startup.finish_attempt()
                if not self.startup.complete:
                    self._send(self.startup.begin(self.clock()))
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
            if (self._default_optout_ack_deadline is not None
                    and self._ack_clock() >= self._default_optout_ack_deadline):
                self._default_optout_ack_deadline = None
                if (self.scheduler.balance
                        and self.scheduler.last_sent is self.scheduler.default_optout_write):
                    self.scheduler.balance = 0
                    self._default_optout_ack_timed_out = True
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
                    if not self.state.get("pardon_first_time_user", 1):
                        self.set_value(6, 54, "Failed to connect to remote system!")
                        self.scheduler.hold = True
                        self._warn_retry("Remote system not responding, click OK to retry")
                        return
                self.connect()
                return
            self.set_value(6, 30, int(bool(self.state.get("connected"))))
            if not self.scheduler.inside and not self.scheduler.outside:
                self.last_health = now
                self._apply_updates(self.decoder.check_health(self.scheduler.access_level))
                self._decoder_effects()
            request = self.scheduler.next_request()
            if request is not None:
                try:
                    self._send(request)
                except OSError as exc:
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
            return
        tag = int(match[1])
        if tag == 1085 and (not self._status_requested or not self.startup or not self.startup.complete):
            self.log("connection", "Ignored STATUS before the current initialization requested it")
            return
        if (tag == 2036 and self._default_optout_ack_timed_out
                and (self.scheduler.last_sent is None or self.scheduler.last_sent.tag != 2036
                     or not self.scheduler.balance)):
            # A delayed write receipt must not release the readback's balance.
            self.log("connection", "Ignored late Opt-out write ACK")
            return
        if tag == 2036 and self.scheduler.last_sent is self.scheduler.default_optout_write:
            self._default_optout_ack_deadline = None
        if tag == 1000 and self.startup and not self.startup.complete:
            self.startup.mark_received()
        self.scheduler.acknowledge(tag)
        self._apply_updates(self.decoder.decode_line(line))
        self._decoder_effects()
        if self.state.pop("call_for_reset_c1n2", 0):
            self.scheduler.reset_channels_pending = True

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
                self.apply(fault_update_actions(), automatic=True)
            else:
                self.state[kind] = value
        self.decoder.next_queries = []
        self.decoder.effects = []

    def handle_callback(self, name, value=0, event=1, panel=6, control=0):
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
            self.apply(actions)
        except (KeyError, ValueError) as exc:
            self.log("callback", str(exc))

    def key_pressed(self, text):
        if text == "\x1b":
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
        if self._connection_presentation and not self.state["gui_ready"]:
            self.state["evnt_cmt"] = 0
            self._button_started = None
            return
        # Worker 0x406953 compares time(NULL): strictly more than 3 whole
        # seconds, then sends ON, reflects TEC-enable and clears the hold flag.
        if self._button_started is not None and int(now) - int(self._button_started) > 3:
            self.scheduler.push(2027, "")
            self.set_value(2, 8, 1)
            self.state["evnt_cmt"] = 0
            self._button_started = None

    def apply(self, actions, *, automatic=False):
        for action in actions:
            kind, target, value = action.kind, action.target, action.value
            if kind in ("command", "query"):
                if self._connection_presentation and not self.state["gui_ready"] and not automatic:
                    self.log("connection", f"Control request {target} blocked while waiting for instrument status")
                    continue
                self.scheduler.push(target, value or "")
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

    def _view_optional(self, name, *args):
        method = getattr(self.view, name, None)
        if method:
            return method(*args)

    def _warn_retry(self, text):
        self.log("Warning", text)
        self._view_optional("show_warning", "Warning", text, self.connect)

    def stop(self):
        self.running = False
        self.state["gui_ready"] = False
        self.state["evnt_cmt"] = 0
        self._button_started = None
        if self.transport:
            self.transport.close()
        if self.tcp:
            self.tcp.stop()

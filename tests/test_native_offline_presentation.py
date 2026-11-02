"""Native view contract: visible navigation without unready device commands."""
import pytest

from spitfire.__main__ import MemoryView
from spitfire.callbacks import command, query
from spitfire.controller import Controller
from spitfire.protocol import PACKET_PREFIX
from spitfire.simulator import SimulatedTransport


class OfflineNativeView(MemoryView):
    def __init__(self):
        super().__init__()
        self.connection_statuses = []
        self.device_controls = {
            (6, 10): 0, (6, 11): 0, (6, 23): 0, (6, 3): 0,
            (6, 60): 0, (6, 51): 0, (6, 52): 0,
            (2, 7): 0, (2, 9): 0, (9, 8): 0,
            (5, 35): 1,  # A control already dimmed by normal application policy.
        }

    def connection_presentation(self):
        return {"controls": dict(self.device_controls),
                "alarm": {500: 0, 641: "FAULT (click here)", 880: 0xffcc33}}

    def set_connection_status(self, ready, message):
        self.connection_statuses.append((bool(ready), str(message)))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr("socket.socket", lambda *a, **kw: pytest.fail("Offline UI tests must not open sockets"))
    now = [0.0]
    controller = Controller(OfflineNativeView(), demo=True, tcp_port=None, clock=lambda: now[0])
    yield controller, now
    controller.stop()


def settle(controller):
    for _ in range(220):
        controller.tick()


def sent_lines(controller):
    return [line for packet in controller.transport.sent_packets
            for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines()]


def assert_offline_presentation(controller):
    assert controller.state["gui_ready"] is False
    assert controller.state["curtain_not_open"] == 1
    assert controller.view.attributes[6, 49, 530] == 0
    assert controller.view.attributes[6, 54, 530] == 0
    assert controller.view.menu_attributes[6, 0, 500] == 0
    for panel, control in controller.view.device_controls:
        assert controller.view.attributes[panel, control, 500] == 1
    assert "NOT CONNECTED" in controller.view.attributes[6, 50, 641].upper()
    assert controller.view.connection_statuses[-1][0] is False


def test_silent_board_keeps_blue_navigation_and_blocks_auto_poll_before_identity(app, monkeypatch):
    class SilentBoard(SimulatedTransport):
        def receive(self):
            return []

    controller, now = app
    monkeypatch.setattr("spitfire.controller.SimulatedTransport", SilentBoard)
    controller.start()
    assert_offline_presentation(controller)
    for deadline in (3.0, 6.0, 9.0):
        now[0] = deadline
        controller.tick()
    assert controller.state["connected"] is False
    assert controller.scheduler.hold is True
    assert_offline_presentation(controller)
    assert sent_lines(controller) == ["[1000]*idn?"] * 3
    now[0] = 9.5
    controller.tick()
    assert sent_lines(controller) == ["[1000]*idn?"] * 3


@pytest.mark.parametrize("name,value,event,panel,control", [
    ("parse_command5", 0, 3, 6, 11),
    ("swChannelEnableCallback_btn1", 1, 1, 6, 23),
    ("SetHVCallback1", 1500, 1, 5, 35),
    ("ecu_set_temp", 21, 1, 2, 7),
    ("com_motor_speed", 30, 1, 6, 3),
    ("empoweroptoutcall", 1, 1, 2, 9),
    ("strnsendcllback", "TDG:HV:ON", 1, 6, 60),
])
def test_offline_device_callbacks_cannot_queue_requests(app, name, value, event, panel, control):
    controller, now = app
    controller.start()
    controller.view.values[panel, control] = value
    if name == "strnsendcllback":
        controller.view.values[6, 59] = value
    controller.handle_callback(name, value, event, panel, control)
    assert not controller.scheduler.inside
    assert not controller.scheduler.outside
    assert sent_lines(controller) == ["[1000]*idn?"]
    assert not any(kind == "callback" for _, kind, value in controller.events)


def test_offline_escape_mouse_release_and_held_run_cannot_bypass_guard(app):
    controller, now = app
    controller.start()
    controller.apply([command(2017), query(1021)])
    controller.key_pressed("\x1b")
    controller.state["motor_mouse_button"] = 1
    controller.mouse_released()
    controller.handle_callback("cllbck", event=3, panel=6, control=10)
    controller._button_started = 0.0
    controller._held_turn_on(10.0)
    assert controller.state["evnt_cmt"] == 0
    assert controller._button_started is None
    assert not controller.scheduler.inside
    assert not controller.scheduler.outside
    assert sent_lines(controller) == ["[1000]*idn?"]


def test_offline_help_panel_navigation_and_exit_remain_available(app):
    controller, now = app
    controller.start()
    for name, panel in (("show_help", 4), ("show_info", 5), ("show_ccu", 2)):
        controller.handle_callback(name)
        assert controller.view.panels[panel]
    controller.key_pressed("regensvc")
    assert controller.state["gAccessLevel"] == 1
    for panel, control in controller.view.device_controls:
        assert controller.view.attributes[panel, control, 500] == 1
    controller.handle_callback("exit_from_menu")
    assert controller.running is False
    assert not controller.scheduler.inside


def test_original_startup_survives_guard_and_restores_latest_device_policy(app):
    controller, now = app
    controller.start()
    controller.set_attribute(2, 7, 500, 1)
    controller.set_attribute(6, 50, 641, "ALL SYS OK")
    assert "NOT CONNECTED" in controller.view.attributes[6, 50, 641].upper()
    settle(controller)
    assert controller.state["gui_ready"] is True
    assert controller.state["connected"] is True
    assert controller.view.connection_statuses[-1][0] is True
    lines = sent_lines(controller)
    for original_request in ("[2036]EMPOPTOUT 1", "[1068]EMPOPTOUT?",
                             "[2047]EMP:LBOBREAK 1", "[1085]STATUS?"):
        assert original_request in lines
    assert controller.view.attributes[6, 10, 500] == 0
    assert controller.view.attributes[5, 35, 500] == 1
    assert controller.view.attributes[2, 7, 500] == 1
    controller.view.values[2, 7] = 21
    controller.handle_callback("ecu_set_temp", 21, panel=2, control=7)
    assert any(request.tag == 2021 for request in controller.scheduler.inside)


def test_unsolicited_status_cannot_enable_controls_before_requested_status(app):
    controller, now = app
    controller.start()
    controller._receive("(9,1)<1085>0")
    assert controller.state["gui_ready"] is False
    assert controller.state["curtain_not_open"] == 1
    for _ in range(200):
        controller.tick()
        if controller.scheduler.last_sent and controller.scheduler.last_sent.tag == 1085:
            break
    else:
        pytest.fail("Original startup never reached its STATUS request")
    assert controller.state["gui_ready"] is False
    controller._receive("(10,1)<1085>0")
    assert controller.state["gui_ready"] is True


def test_reconnect_discards_old_ready_status_and_pending_run(app):
    controller, now = app
    controller.start()
    settle(controller)
    assert controller.state["gui_ready"] is True
    controller.state["evnt_cmt"] = 1
    controller._button_started = 0.0
    controller.connect()
    assert controller.state["connected"] is False
    assert_offline_presentation(controller)
    assert controller.state["evnt_cmt"] == 0
    assert controller._button_started is None
    controller._receive("(20,1)<1085>0")
    assert controller.state["gui_ready"] is False
    controller.handle_callback("parse_command5", event=3, panel=6, control=11)
    assert not controller.scheduler.inside
    settle(controller)
    assert controller.state["gui_ready"] is True
    assert "[2027]ON" not in sent_lines(controller)


def test_native_data_logger_does_not_record_offline_or_reconnecting_values(app, tmp_path):
    controller, now = app
    controller.data_dir = tmp_path / "measurements"
    log = controller.data_dir / "datalog.csv"
    controller.view.values[1, 3] = 1
    controller.start()
    controller.view.values[9, 2] = 12.34
    controller.view.values[8, 15] = 56.78
    controller.handle_callback("tmr_Data_Logger", event=15, panel=6, control=64)
    assert not controller.data_dir.exists()
    now[0] = 1.0
    controller.tick()
    controller.handle_callback("tmr_Data_Logger", event=15, panel=6, control=64)
    assert controller.state["gui_ready"] is False
    assert not log.exists()
    settle(controller)
    assert controller.state["gui_ready"] is True
    controller.view.values[9, 2] = 2.5
    controller.view.values[8, 15] = 42.0
    controller.handle_callback("tmr_Data_Logger", event=15, panel=6, control=64)
    assert log.read_text() == "2.50, 42.00\n"
    recorded = log.read_bytes()
    controller.connect()
    controller.handle_callback("tmr_Data_Logger", event=15, panel=6, control=64)
    assert controller.state["gui_ready"] is False
    assert log.read_bytes() == recorded


def test_pending_offline_run_press_cannot_arm_when_status_arrives_before_next_tick(app):
    controller, now = app
    controller.start()
    for _ in range(200):
        controller.tick()
        if controller.scheduler.last_sent and controller.scheduler.last_sent.tag == 1085:
            break
    else:
        pytest.fail("Startup never reached STATUS")
    assert not controller.state["gui_ready"]
    # A queued mouse event can be delivered immediately before the readback.
    controller.handle_callback("cllbck", event=3, panel=6, control=10)
    assert controller.state["evnt_cmt"] == 0
    assert controller._button_started is None
    now[0] = 4.0
    controller._receive("(30,1)<1085>0")
    assert controller.state["gui_ready"]
    controller._held_turn_on(now[0])
    settle(controller)
    assert "[2027]ON" not in sent_lines(controller)


def test_long_connection_loss_disables_controls_before_retry_warning(app, monkeypatch, tmp_path):
    controller, now = app
    controller.start()
    settle(controller)
    assert controller.state["gui_ready"]
    controller.data_dir = tmp_path / "offline-measurements"
    controller.view.values[1, 3] = 1
    controller.state["evnt_cmt"] = 1
    controller._button_started = 0.0
    monkeypatch.setattr(controller.view, "show_warning",
                        lambda *args: pytest.fail("Reconnect must not wait for modal acknowledgement"), raising=False)
    old_transport = controller.transport
    monkeypatch.setattr(controller.transport, "receive", lambda: [])
    now[0] = 31.0  # A stalled event loop can skip the normal >10s reopen branch.
    controller.tick()
    assert controller.transport is not old_transport
    assert sent_lines(controller) == ["[1000]*idn?"]
    assert controller.scheduler.hold
    assert not controller.state["connected"]
    assert_offline_presentation(controller)
    assert controller.state["evnt_cmt"] == 0
    assert controller._button_started is None
    controller._receive("(30,1)<1085>0")  # A delayed old STATUS is not fresh.
    assert not controller.state["gui_ready"]
    controller.handle_callback("cllbck", event=3, panel=6, control=10)
    controller.handle_callback("tmr_Data_Logger", event=15, panel=6, control=64)
    assert not controller.data_dir.exists()
    controller._held_turn_on(35.0)
    assert sent_lines(controller) == ["[1000]*idn?"]
    assert_offline_presentation(controller)
    assert not controller._status_requested
    settle(controller)
    assert controller.state["gui_ready"]
    assert "[2027]ON" not in sent_lines(controller)

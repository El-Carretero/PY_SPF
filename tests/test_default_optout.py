"""post2 uses the original board setting, with no External-mode policy."""
import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.protocol import PACKET_PREFIX
from spitfire.simulator import SimulatedTransport


def sent_lines(controller):
    return [line for packet in controller.transport.sent_packets
            for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines()]


def settle(controller):
    for _ in range(180):
        controller.tick()


@pytest.mark.parametrize("hv", ["0", "1", None])
def test_connection_applies_optout_without_hv_off_prerequisite(monkeypatch, hv):
    transport = SimulatedTransport()
    if hv is None:
        del transport.values["TDG:HV:ON?"]
    else:
        transport.values["TDG:HV:ON?"] = hv
    monkeypatch.setattr("spitfire.controller.SimulatedTransport", lambda: transport)
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: 0.0)
    try:
        app.start()
        # A default is a request, not a fabricated board readback.
        assert app.state["emp_optout"] == 0
        settle(app)
        lines = sent_lines(app)
        assert lines[:6] == ["[1000]*idn?"] * 3 + [
            "[1069]HEDOPTOUT?", "[2036]EMPOPTOUT 1", "[1068]EMPOPTOUT?"]
        assert app.state["emp_optout"] == 1
        assert app.view.read(2, 9) == 1
        assert lines.count("[2036]EMPOPTOUT 1") == 1
        # Preserve original initialization/polling, including Empower traffic.
        assert "[2047]EMP:LBOBREAK 1" in lines
        assert "[1013]EMP:STB?" in lines
        assert "[1007]EMP:READ:DIODE:CURR?" in lines
    finally:
        app.stop()


def test_reconnect_reapplies_default_and_manual_original_toggle_still_works():
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: 0.0)
    try:
        app.start()
        settle(app)
        # Original callback accepts OFF as well as ON, without an HV check.
        app.set_value(2, 9, 0)
        app.handle_callback("empoweroptoutcall", 0, panel=2, control=9)
        settle(app)
        assert "[2036]EMPOPTOUT 0" in sent_lines(app)
        # Use the original readback to confirm the setting.
        app.scheduler.push(1068)
        settle(app)
        assert app.state["emp_optout"] == 0
        app.connect()
        settle(app)
        assert sent_lines(app).count("[2036]EMPOPTOUT 1") == 1
        assert app.state["emp_optout"] == 1
    finally:
        app.stop()


def test_write_ack_does_not_replace_board_readback(monkeypatch):
    class RejectingBoard(SimulatedTransport):
        def _command(self, tag, title, parameter):
            if tag != 2036:
                super()._command(tag, title, parameter)

    monkeypatch.setattr("spitfire.controller.SimulatedTransport", RejectingBoard)
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: 0.0)
    try:
        app.start()
        settle(app)
        assert "[2036]EMPOPTOUT 1" in sent_lines(app)
        assert app.state["emp_optout"] == 0
        assert app.view.read(2, 9) == 0
    finally:
        app.stop()

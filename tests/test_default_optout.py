"""post2 uses the original board setting, with no External-mode policy."""
import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.protocol import PACKET_PREFIX
from spitfire.simulator import SimulatedTransport


class MissingDefaultAckTransport(SimulatedTransport):
    """Firmware fixture: apply a write but omit its receipt on the wire."""
    def __init__(self, *, accept_setting=True, drop_readback=False):
        super().__init__()
        self.accept_setting = accept_setting
        self.drop_readback = drop_readback
        self.values["TDG:HV:ON?"] = "1"

    def _command(self, tag, title, parameter):
        if tag != 2036 or self.accept_setting:
            super()._command(tag, title, parameter)

    def receive(self):
        replies = super().receive()
        blocked = ("<2036>", "<1068>") if self.drop_readback else ("<2036>",)
        return [reply for reply in replies if not reply.body.startswith(blocked)]


def missing_ack_app(monkeypatch, **transport_options):
    now = [0.0]
    transport = MissingDefaultAckTransport(**transport_options)
    monkeypatch.setattr("spitfire.controller.SimulatedTransport", lambda: transport)
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: now[0])
    app.start()
    settle(app)
    # No next request is allowed before the bounded receipt wait has elapsed.
    assert sent_lines(app)[-1] == "[2036]EMPOPTOUT 1"
    assert "[1068]EMPOPTOUT?" not in sent_lines(app)
    assert app.state["emp_optout"] == 0
    assert app.state["curtain_not_open"] == 1
    return app, transport, now


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


@pytest.mark.parametrize("accept_setting", [True, False])
def test_missing_default_write_ack_continues_to_real_readback_and_opens_screen(monkeypatch, accept_setting):
    app, transport, now = missing_ack_app(monkeypatch, accept_setting=accept_setting)
    try:
        now[0] = 0.99
        app.tick()
        assert sent_lines(app)[-1] == "[2036]EMPOPTOUT 1"
        now[0] = 1.0
        app.tick()
        assert sent_lines(app)[-1] == "[1068]EMPOPTOUT?"
        # Sending a query cannot fabricate a successful readback.
        assert app.state["emp_optout"] == 0
        settle(app)
        assert app.state["emp_optout"] == int(accept_setting)
        assert app.view.read(2, 9) == int(accept_setting)
        assert sent_lines(app).count("[2036]EMPOPTOUT 1") == 1
        assert "[1085]STATUS?" in sent_lines(app)
        assert app.state["curtain_not_open"] == 0
        assert app.view.attributes[6, 49, 530] == 0
        assert app.view.attributes[6, 54, 530] == 0
        assert app.view.menu_attributes[6, 0, 500] == 0
    finally:
        app.stop()


def test_late_default_write_ack_does_not_release_outstanding_readback(monkeypatch):
    app, transport, now = missing_ack_app(monkeypatch)
    try:
        now[0] = 1.0
        app.tick()
        assert app.scheduler.last_sent.tag == 1068
        assert app.scheduler.balance == 1
        pending_queries = list(app.scheduler.inside)
        app._receive("(100,1)<2036>0")
        assert app.scheduler.balance == 1
        assert app.scheduler.last_sent.tag == 1068
        assert list(app.scheduler.inside) == pending_queries
        assert app.state["emp_optout"] == 0
        # The genuine queued board readback remains the only setting update.
        app.tick()
        assert app.state["emp_optout"] == 1
        settle(app)
        assert app.state["curtain_not_open"] == 0
    finally:
        app.stop()


def test_missing_write_ack_and_missing_readback_never_claim_optout_or_open_screen(monkeypatch):
    app, transport, now = missing_ack_app(monkeypatch, drop_readback=True)
    try:
        now[0] = 1.0
        app.tick()
        settle(app)
        assert sent_lines(app)[-1] == "[1068]EMPOPTOUT?"
        assert app.scheduler.balance == 1
        assert app.state["emp_optout"] == 0
        assert app.state["curtain_not_open"] == 1
        assert app.view.attributes[6, 49, 530] == 1
        assert "[1085]STATUS?" not in sent_lines(app)
    finally:
        app.stop()


def test_reconnect_gives_new_default_write_its_own_bounded_ack_wait(monkeypatch):
    app, transport, now = missing_ack_app(monkeypatch)
    try:
        now[0] = 0.5
        app.connect()
        settle(app)
        assert sent_lines(app).count("[2036]EMPOPTOUT 1") == 2
        now[0] = 1.0
        app.tick()
        assert sent_lines(app)[-1] == "[2036]EMPOPTOUT 1"
        assert app.scheduler.balance == 1
        now[0] = 1.5
        app.tick()
        assert sent_lines(app)[-1] == "[1068]EMPOPTOUT?"
        settle(app)
        assert app.state["emp_optout"] == 1
        assert app.state["curtain_not_open"] == 0
    finally:
        app.stop()

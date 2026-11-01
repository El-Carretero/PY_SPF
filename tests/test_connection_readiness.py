"""A previous successful session must not leave a failed reconnect looking ready."""
from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.simulator import SimulatedTransport


def settle(app):
    for _ in range(200):
        app.tick()


def assert_curtain(app, visible):
    assert app.state["curtain_not_open"] == visible
    assert app.view.attributes[6, 49, 530] == visible
    assert app.view.attributes[6, 54, 530] == visible
    assert app.view.menu_attributes[6, 0, 500] == visible


def test_ready_session_then_silent_reconnect_shows_failure_and_closes_controls(monkeypatch):
    class SilentBoard(SimulatedTransport):
        def receive(self):
            return []

    now = [0.0]
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: now[0])
    try:
        app.start()
        settle(app)
        assert app.state["connected"]
        assert_curtain(app, 0)
        monkeypatch.setattr("spitfire.controller.SimulatedTransport", SilentBoard)
        app.connect()
        assert not app.state["connected"]
        assert_curtain(app, 1)
        for deadline in (3.0, 6.0, 9.0):
            now[0] = deadline
            app.tick()
        assert not app.state["connected"]
        assert_curtain(app, 1)
        assert "No reply from 10.19.70.13:1024" in app.view.read(6, 54)
    finally:
        app.stop()


def test_ready_session_then_successful_reconnect_reopens_only_after_new_status():
    app = Controller(MemoryView(), demo=True, tcp_port=None, clock=lambda: 0.0)
    try:
        app.start()
        settle(app)
        assert app.state["connected"]
        assert_curtain(app, 0)
        app.connect()
        assert not app.state["connected"]
        assert_curtain(app, 1)
        # Identity/Opt-out replies can mark the link connected, but may not
        # expose controls using a previous session's STATUS readback.
        for _ in range(15):
            app.tick()
        assert app.state["connected"]
        assert app.state["emp_optout"] == 1
        assert_curtain(app, 1)
        settle(app)
        assert app.state["connected"]
        assert_curtain(app, 0)
        packets = b"".join(app.transport.sent_packets)
        assert b"[1085]STATUS?\n" in packets
    finally:
        app.stop()

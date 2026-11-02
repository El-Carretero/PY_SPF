"""Offline regressions for actual duplicate, loss and source-address failure modes."""
from collections import Counter, deque
import re
import socket
import time

import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.protocol import PACKET_PREFIX, UDPTransport
from spitfire.scheduling import Request, Scheduler, StartupAttempts
from spitfire.simulator import SimulatedTransport


class LossyBoard(SimulatedTransport):
    """Apply commands normally, then independently drop selected wire receipts."""
    def __init__(self):
        super().__init__()
        self.drop = Counter()

    def receive(self):
        result = []
        for reply in super().receive():
            tag = int(re.match(r"<(\d+)>", reply.body)[1])
            if self.drop[tag]:
                self.drop[tag] -= 1
            else:
                result.append(reply)
        return result


@pytest.fixture
def apps(monkeypatch):
    monkeypatch.setattr("socket.socket", lambda *a, **kw: pytest.fail("These tests must not open sockets"))
    created = []

    def make(*, read_only=False, board=None, **kwargs):
        board = board or LossyBoard()
        now = [0.0]
        monkeypatch.setattr("spitfire.controller.SimulatedTransport", lambda: board)
        app = Controller(MemoryView(), demo=True, tcp_port=None, read_only=read_only,
                         clock=lambda: now[0], **kwargs)
        created.append(app)
        return app, board, now

    yield make
    for app in created:
        app.stop()


def settle(app, ticks=220):
    for _ in range(ticks):
        app.tick()


def lines(board):
    return [line for packet in board.sent_packets
            for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines()]


def tags(board):
    return [int(re.match(r"\[(\d+)\]", line)[1]) for line in lines(board)]


def ready(app):
    app.start()
    settle(app)
    assert app.state["gui_ready"] is True


def isolate(app, board, requests):
    """Select a small transaction sequence after a real simulated startup."""
    app.scheduler.clear()
    board.pending.clear()
    for tag, parameter in requests:
        app.scheduler.push(tag, parameter)


def test_scheduler_requires_the_outstanding_tag_and_ignores_duplicate_receipts():
    now = [0.0]
    scheduler = Scheduler(clock=lambda: now[0])
    scheduler.push(1040)
    scheduler.push(1041)
    assert scheduler.next_request(auto_poll=False).tag == 1040
    now[0] = 0.25
    assert scheduler.acknowledge(1041) is False
    assert scheduler.balance == 1
    assert scheduler.last_received == 0.0
    assert scheduler.acknowledge(1040) is True
    assert scheduler.last_received == 0.25
    assert scheduler.acknowledge(1040) is False
    assert scheduler.next_request(auto_poll=False).tag == 1041
    assert scheduler.acknowledge(1040) is False
    assert scheduler.balance == 1


def test_late_a_cannot_release_b_or_replace_its_ui_values(apps):
    app, board, now = apps()
    ready(app)
    isolate(app, board, [(1040, ""), (1041, ""), (1055, "")])
    app.tick()  # A is outstanding.
    app.tick()  # A accepted, B is now outstanding.
    assert app.scheduler.last_sent.tag == 1041
    old_value = app.view.read(5, 35)
    last_received = app.scheduler.last_received
    now[0] = 0.1
    app._receive("(999,1)<1040>9.999 KV")
    assert app.scheduler.balance == 1
    assert app.scheduler.last_sent.tag == 1041
    assert app.scheduler.last_received == last_received
    assert app.view.read(5, 35) == old_value
    assert app.diagnostics["ignored_replies"] >= 1
    # The genuine B reply, rather than stale A, permits C to be transmitted.
    app.tick()
    assert app.scheduler.last_sent.tag == 1055


def test_idle_balance_zero_still_drains_stale_packets_without_decoding(apps):
    app, board, now = apps()
    ready(app)
    isolate(app, board, [])
    app.scheduler.hold = True
    old_value = app.view.read(5, 35)
    last_received = app.scheduler.last_received
    board.pending.append(b"Spectra-Physics:REPLY_ECLIPSE:<1040>9.999 KV\n")
    now[0] = 0.1
    app.tick()
    assert not board.pending
    assert app.scheduler.balance == 0
    assert app.view.read(5, 35) == old_value
    assert app.scheduler.last_received == last_received
    assert app.diagnostics["ignored_replies"] >= 1


def test_one_lost_query_retries_only_that_query_without_startup_or_writes(apps):
    app, board, now = apps()
    ready(app)
    isolate(app, board, [(1040, ""), (1041, "")])
    before = len(lines(board))
    board.drop[1040] = 1
    app.tick()
    app.tick()
    assert app.scheduler.balance == 1
    now[0] = 0.71
    app.tick()
    settle(app, 12)
    emitted = tags(board)[before:]
    assert emitted.count(1040) == 2
    assert 1041 in emitted
    assert 1000 not in emitted
    assert all(tag < 2000 for tag in emitted)
    assert app.state["gui_ready"] is True
    assert app.diagnostics["query_retries"] == 1


def test_exhausted_query_retries_do_not_strand_polling_or_repeat_initialization(apps):
    app, board, now = apps()
    ready(app)
    isolate(app, board, [(1040, ""), (1041, "")])
    before = len(lines(board))
    board.drop[1040] = 20
    app.tick()
    app.tick()
    for at in (0.71, 1.42, 2.13):
        now[0] = at
        app.tick()
        app.tick()
    settle(app, 12)
    emitted = tags(board)[before:]
    assert emitted.count(1040) == 3  # Initial query plus two bounded retries.
    assert 1041 in emitted
    assert 1000 not in emitted
    assert all(tag < 2000 for tag in emitted)
    assert app.diagnostics["query_retries"] == 2
    assert app.diagnostics["query_timeouts"] >= 1
    assert app.state["gui_ready"] is True


def test_missing_actuator_ack_never_replays_the_actuator(apps):
    app, board, now = apps()
    ready(app)
    isolate(app, board, [(2014, " 90.00"), (1060, "")])
    before = len(lines(board))
    board.drop[2014] = 20
    app.tick()
    app.tick()
    now[0] = 1.01
    app.tick()
    settle(app, 12)
    emitted = tags(board)[before:]
    assert emitted.count(2014) == 1
    assert 1060 in emitted
    assert 1000 not in emitted
    assert app.view.read(6, 3) == 90
    assert app.diagnostics["write_ack_timeouts"] >= 1


def test_read_only_startup_preserves_existing_optout_and_emits_only_real_queries(apps):
    board = LossyBoard()
    board.values["EMPOPTOUT?"] = "1"
    board.values["TDG:OSC:MODE?"] = "EXT"  # Original decoder asks for INT/EXT writes.
    board.values["STATUS?"] = "3"  # Original status requests RES12.
    board.values["TDG:DEL1?"] = " DELAY 1 ON BWD NENA 85.82"
    board.values["TDG:DEL2?"] = " DELAY 2 ON BWD NENA 990.25"
    app, board, now = apps(read_only=True, board=board)
    ready(app)
    assert app.read_only is True
    assert app.state["emp_optout"] == 1
    assert board.values["EMPOPTOUT?"] == "1"
    assert all(tag < 2000 for tag in tags(board))
    assert all(line.endswith("?") for line in lines(board))
    assert 1068 in tags(board) and 1085 in tags(board)
    assert app.view.read(6, 23) == 1
    assert app.view.read(6, 21) == 1


@pytest.mark.parametrize("tag,parameter", [(2036, " 0"), (2047, " 1"), (2030, " INT"),
                                           (2054, ""), (2027, ""), (2017, ""),
                                           (2021, " 1.10"), (2034, "TDG:HV:ON")])
def test_read_only_final_send_gate_blocks_every_actuator_path(apps, tag, parameter):
    app, board, now = apps(read_only=True)
    ready(app)
    before = len(board.sent_packets)
    assert app._send(Request(tag, parameter)) is False
    assert len(board.sent_packets) == before
    assert app.diagnostics["blocked_writes"] >= 1


def test_read_only_skips_automatic_write_without_stranding_the_next_readback(apps):
    app, board, now = apps(read_only=True)
    ready(app)
    isolate(app, board, [(2036, " 1"), (1032, "")])
    before = len(lines(board))
    settle(app, 8)
    emitted = tags(board)[before:]
    assert 1032 in emitted
    assert all(tag < 2000 for tag in emitted)


def test_read_only_never_fabricates_the_default_optout_setting(apps):
    board = LossyBoard()
    board.values["EMPOPTOUT?"] = "0"
    app, board, now = apps(read_only=True, board=board)
    ready(app)
    assert app.state["emp_optout"] == 0
    assert app.view.read(2, 9) == 0
    assert board.values["EMPOPTOUT?"] == "0"
    assert all(tag < 2000 for tag in tags(board))


@pytest.mark.parametrize("candidate", [Request(1026, " 1?"), Request(1000, "\n[2017]TDG:HV:ON"), Request(1999)])
def test_read_only_final_gate_rejects_partial_unknown_or_parameterized_queries(apps, candidate):
    app, board, now = apps(read_only=True)
    ready(app)
    before = len(board.sent_packets)
    assert app._send(candidate) is False
    assert len(board.sent_packets) == before


def test_read_only_final_gate_rejects_non_integer_tags_even_when_numeric_value_matches(apps):
    app, board, now = apps(read_only=True)
    ready(app)
    before = len(board.sent_packets)
    assert app._send(Request(1068.0)) is False
    assert len(board.sent_packets) == before


def test_read_only_final_gate_checks_actual_message_instead_of_trusting_tag_metadata(apps):
    class ForgedQuery(Request):
        @property
        def message(self):
            return "[2027]ON"

    app, board, now = apps(read_only=True)
    ready(app)
    before = len(board.sent_packets)
    assert app._send(ForgedQuery(1068)) is False
    assert len(board.sent_packets) == before


def test_read_only_blocks_manual_escape_held_run_and_motor_release_paths(apps):
    app, board, now = apps(read_only=True)
    ready(app)
    isolate(app, board, [])
    before = len(lines(board))
    for name, value, event, panel, control in [("HV_switch", 1, 1, 5, 34),
                                               ("parse_command5", 0, 3, 6, 11),
                                               ("picture_Callback1", 0, 3, 6, 52),
                                               ("ecu_set_temp", 1.1, 1, 2, 7)]:
        app.handle_callback(name, value, event, panel, control)
    app.key_pressed("\x1b")
    app._button_started = 0.0
    app.state["evnt_cmt"] = 1
    app._held_turn_on(5.0)
    app.state["motor_mouse_button"] = 1
    app.mouse_released()
    settle(app, 8)
    assert all(tag < 2000 for tag in tags(board)[before:])
    assert app.state["evnt_cmt"] == 0
    assert app._button_started is None


def test_empty_reply_is_unavailable_instead_of_reusing_previous_payload(apps):
    board = LossyBoard()
    board.values["HEDOPTOUT?"] = "1"
    app, board, now = apps(read_only=True, board=board)
    ready(app)
    assert app.state["hed_optout"] == 1
    board.values["HEDOPTOUT?"] = ""
    isolate(app, board, [(1021, ""), (1069, "")])
    settle(app, 4)
    assert app.state["hed_optout"] == 1  # No fabricated value from the preceding HV=0 reply.
    assert app.diagnostics["empty_replies"] >= 1


def test_explicit_request_pacing_uses_the_injected_monotonic_clock(apps):
    app, board, now = apps(min_request_interval=0.25)
    app.transport = board
    app.startup = StartupAttempts(attempts=3, complete=True, received=True)
    app.scheduler.push(1040)
    app.scheduler.push(1041)
    app.tick()
    assert tags(board) == [1040]
    app.tick()
    assert tags(board) == [1040]
    now[0] = 0.249
    app.tick()
    assert tags(board) == [1040]
    now[0] = 0.25
    app.tick()
    assert tags(board) == [1040, 1041]


def test_default_controller_clock_is_monotonic_even_when_wall_clock_changes(monkeypatch):
    monkeypatch.setattr("time.time", lambda: -1e20)
    before = time.monotonic()
    app = Controller(MemoryView(), demo=True, tcp_port=None)
    try:
        assert before <= app.clock() <= time.monotonic()
    finally:
        app.stop()


def test_udp_transport_rejects_wrong_source_ip_and_port_without_real_sockets(monkeypatch):
    class DatagramSocket:
        def __init__(self):
            reply = b"Spectra-Physics:REPLY_ECLIPSE:<1000>real configured peer\n"
            self.pending = deque([(reply, ("10.19.70.99", 1024)),
                                  (reply, ("10.19.70.13", 1200)),
                                  (b"malformed", ("10.19.70.13", 1024)),
                                  (reply, ("10.19.70.13", 1024))])

        def setsockopt(self, *args): pass
        def bind(self, *args): pass
        def settimeout(self, *args): pass
        def close(self): pass
        def recvfrom(self, *args):
            if not self.pending:
                raise BlockingIOError()
            return self.pending.popleft()

    fake = DatagramSocket()
    monkeypatch.setattr("socket.socket", lambda *args: fake)
    monkeypatch.setattr("socket.gethostbyname", lambda host: "10.19.70.13")
    transport = UDPTransport("instrument.local", 1024, timeout=0)
    try:
        transport.open()
        received = []
        for _ in range(5):
            received.extend(transport.receive())
        assert [reply.body for reply in received] == ["<1000>real configured peer"]
        assert transport.diagnostics["wrong_peer_packets"] == 2
        assert transport.diagnostics["malformed_packets"] == 1
        assert transport.diagnostics["rx_packets"] == 4
    finally:
        transport.close()


def test_diagnostics_snapshot_exposes_pending_and_read_only_scope(apps):
    app, board, now = apps(read_only=True)
    ready(app)
    snapshot = app.communication_diagnostics()
    assert snapshot["read_only"] is True
    assert isinstance(snapshot["controller"], dict)
    assert isinstance(snapshot["transport"], dict)
    assert snapshot["controller"]["tx_packets"] == len(board.sent_packets)
    assert "pending_tag" in snapshot


def test_initial_and_later_identity_send_failures_stay_bounded_and_do_not_crash(apps):
    class FailingIdentityBoard(LossyBoard):
        def __init__(self):
            super().__init__()
            self.attempted = []

        def send_packet(self, packet):
            self.attempted.append(packet)
            raise OSError("synthetic transient IDN send failure")

    app, board, now = apps(read_only=True, board=FailingIdentityBoard())
    app.start()
    assert len(board.attempted) == 1
    for at in (3.0, 6.0, 9.0):
        now[0] = at
        app.tick()
    assert len(board.attempted) == 3
    assert app.diagnostics["startup_attempts"] == 3
    assert app.diagnostics["send_errors"] == 3
    assert app.state["gui_ready"] is False
    assert app.scheduler.hold is True
    now[0] = 10.99
    settle(app, 20)
    assert len(board.attempted) == 3
    now[0] = 11.0
    app.tick()
    assert len(board.attempted) == 4
    assert app.diagnostics["connect_attempts"] == 2
    assert app.diagnostics["reconnects"] == 1
    assert all(packet == PACKET_PREFIX + b"[1000]*idn?\n" for packet in board.attempted)


def test_failed_query_sends_wait_for_each_deadline_instead_of_bursting_on_ui_ticks(apps):
    class FailingQueryBoard(LossyBoard):
        def __init__(self):
            super().__init__()
            self.fail_query = False
            self.failed_attempts = 0

        def send_packet(self, packet):
            if self.fail_query and packet == PACKET_PREFIX + b"[1040]TDG:HV1:VOLT?\n":
                self.failed_attempts += 1
                raise OSError("synthetic query send failure")
            super().send_packet(packet)

    app, board, now = apps(board=FailingQueryBoard())
    ready(app)
    isolate(app, board, [(1040, ""), (1041, "")])
    board.fail_query = True
    app.tick()
    settle(app, 100)
    assert board.failed_attempts == 1
    now[0] = 0.71
    settle(app, 100)
    assert board.failed_attempts == 2
    now[0] = 1.42
    settle(app, 100)
    assert board.failed_attempts == 3
    now[0] = 2.13
    settle(app, 12)
    assert board.failed_attempts == 3
    assert app.diagnostics["query_retries"] == 2
    assert app.diagnostics["query_timeouts"] == 1
    assert app.diagnostics["send_errors"] == 3
    assert app.diagnostics["connect_attempts"] == 1
    assert app.scheduler.last_sent.tag != 1040


def test_reconnect_aggregates_closed_transport_counters_and_reports_match_status_age(apps, monkeypatch):
    first = LossyBoard()
    first.diagnostics = Counter(rx_packets=7, wrong_peer_packets=2)
    app, board, now = apps(read_only=True, board=first)
    ready(app)
    assert app.communication_diagnostics()["transport"]["rx_packets"] == 7
    second = LossyBoard()
    second.diagnostics = Counter(rx_packets=3, wrong_peer_packets=1)
    monkeypatch.setattr("spitfire.controller.SimulatedTransport", lambda: second)
    app.connect()
    settle(app)
    now[0] = 0.5
    snapshot = app.communication_diagnostics()
    assert snapshot["transport"]["rx_packets"] == 10
    assert snapshot["transport"]["wrong_peer_packets"] == 3
    assert snapshot["controller"]["connect_attempts"] == 2
    assert snapshot["controller"]["reconnects"] == 1
    assert snapshot["controller"]["open_attempts"] == 2
    assert snapshot["controller"]["startup_attempts"] == 6
    assert snapshot["last_match_monotonic"] == 0.0
    assert snapshot["last_status_monotonic"] == 0.0
    assert snapshot["last_match_age_seconds"] == 0.5
    assert snapshot["last_status_age_seconds"] == 0.5
    assert app.communication_diagnostics()["transport"] == snapshot["transport"]


def test_losing_only_status_disables_controls_while_other_queries_keep_connection_alive(apps):
    app, board, now = apps(read_only=True)
    ready(app)
    board.drop[1085] = 1000
    for step in range(1, 312):
        now[0] = step / 10
        app.tick()
    assert app.state["connected"] is True
    assert app.state["gui_ready"] is False
    assert app.state["curtain_not_open"] == 1
    assert app.diagnostics["status_stale_events"] == 1
    assert app.diagnostics["connect_attempts"] == 1
    snapshot = app.communication_diagnostics()
    assert snapshot["last_status_age_seconds"] > 30
    assert snapshot["last_match_age_seconds"] < 3
    board.drop[1085] = 0
    for _ in range(100):
        now[0] += 0.1
        app.tick()
        if app.state["gui_ready"]:
            break
    assert app.state["gui_ready"] is True
    assert app.state["curtain_not_open"] == 0
    assert app.diagnostics["connect_attempts"] == 1
    assert app.communication_diagnostics()["last_status_age_seconds"] == 0.0
    assert all(tag < 2000 for tag in tags(board))


def test_malformed_matching_status_does_not_acknowledge_or_refresh_status_age(apps):
    app, board, now = apps(read_only=True)
    ready(app)
    isolate(app, board, [(1085, "")])
    board.values["STATUS?"] = "not a numeric status"
    now[0] = 0.25
    app.tick()
    app.tick()
    assert app.scheduler.balance == 1
    assert app.scheduler.last_sent.tag == 1085
    assert app.communication_diagnostics()["last_status_monotonic"] == 0.0
    assert app.diagnostics["malformed_replies"] >= 1
    board.values["STATUS?"] = "0"
    now[0] = 0.96
    app.tick()
    app.tick()
    assert app.communication_diagnostics()["last_status_monotonic"] == 0.96


def test_failed_port_open_is_paced_and_recovers_after_automatic_retry_deadline(monkeypatch):
    now = [0.0]
    opened_at = []
    failures = []
    board = LossyBoard()
    monkeypatch.setattr("socket.socket", lambda *a, **kw: pytest.fail("Port recovery test cannot open a socket"))

    class FailedPort:
        def __init__(self):
            self.closed = False

        def open(self):
            raise OSError("synthetic bind failure")

        def close(self):
            self.closed = True

    def transport_factory(*args, **kwargs):
        opened_at.append(now[0])
        if len(opened_at) <= 2:
            failed = FailedPort()
            failures.append(failed)
            return failed
        return board

    monkeypatch.setattr("spitfire.controller.UDPTransport", transport_factory)
    app = Controller(MemoryView(), demo=False, read_only=True, tcp_port=None,
                     clock=lambda: now[0])
    try:
        app.start()
        settle(app, 100)
        assert opened_at == [0.0]
        now[0] = 0.249
        app.tick()
        assert opened_at == [0.0]
        now[0] = 2.0
        settle(app, 100)
        assert opened_at == [0.0, 2.0]
        now[0] = 3.0
        app.tick()
        assert app._opening_deadline is None
        assert app._startup_retry_deadline == 5.0
        assert app.state["gui_ready"] is False
        now[0] = 4.99
        settle(app, 100)
        assert opened_at == [0.0, 2.0]
        now[0] = 5.0
        app.tick()
        assert opened_at == [0.0, 2.0, 5.0]
        assert all(port.closed for port in failures)
        for _ in range(100):
            now[0] += 0.25
            app.tick()
            if app.state["gui_ready"]:
                break
        assert app.state["gui_ready"] is True
        assert app.diagnostics["open_errors"] == 2
        assert app.diagnostics["connect_attempts"] == 2
        assert all(tag < 2000 for tag in tags(board))
    finally:
        app.stop()


@pytest.mark.parametrize("payload,valid", [("-99", False), ("-1", False),
                                           ("4294967296", False), ("0", True), ("3", True)])
def test_status_requires_nonnegative_uint32_before_acknowledging_or_enabling_gui(apps, payload, valid):
    app, board, now = apps(read_only=True)
    app.transport = board
    app.startup = StartupAttempts(attempts=3, complete=True, received=True)
    board.values["STATUS?"] = payload
    app.scheduler.push(1085)
    app.tick()
    app.tick()
    if valid:
        assert app.state["gui_ready"] is True
        assert app.communication_diagnostics()["last_status_monotonic"] == 0.0
        assert app.diagnostics["matched_replies"] == 1
    else:
        assert app.scheduler.balance == 1
        assert app.scheduler.last_sent.tag == 1085
        assert app.state["gui_ready"] is False
        assert app.communication_diagnostics()["last_status_monotonic"] is None
        assert app.communication_diagnostics()["last_match_monotonic"] is None
        assert app.diagnostics["matched_replies"] == 0
        assert app.diagnostics["malformed_replies"] == 1
    assert all(tag < 2000 for tag in tags(board))


def test_udp_transport_sets_windows_exclusive_binding_before_any_bind(monkeypatch):
    calls = []

    class ExclusiveSocket:
        def setsockopt(self, level, option, value):
            calls.append(("setsockopt", level, option, value))

        def bind(self, endpoint): calls.append(("bind", endpoint))
        def settimeout(self, value): calls.append(("timeout", value))
        def close(self): calls.append(("close",))

    fake = ExclusiveSocket()
    monkeypatch.setattr(socket, "SO_EXCLUSIVEADDRUSE", -5, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *args: fake)
    monkeypatch.setattr(socket, "gethostbyname", lambda host: "127.0.0.1")
    transport = UDPTransport("127.0.0.1", 65431, bind_port=65432, timeout=0)
    try:
        transport.open()
        assert calls[0] == ("setsockopt", socket.SOL_SOCKET, -5, 1)
        assert ("bind", ("0.0.0.0", 65432)) in calls
        assert calls.index(("setsockopt", socket.SOL_SOCKET, -5, 1)) < calls.index(("bind", ("0.0.0.0", 65432)))
    finally:
        transport.close()


def test_udp_exclusive_option_failure_closes_socket_without_binding_or_fallback(monkeypatch):
    calls = []

    class RejectedExclusiveSocket:
        def setsockopt(self, level, option, value):
            calls.append(("setsockopt", level, option, value))
            if option == -5:
                raise OSError("exclusive binding option rejected")

        def bind(self, endpoint): pytest.fail("No bind is permitted after an exclusive-option failure")
        def settimeout(self, value): pytest.fail("No unsafe fallback socket setup is permitted")
        def close(self): calls.append(("close",))

    fake = RejectedExclusiveSocket()
    monkeypatch.setattr(socket, "SO_EXCLUSIVEADDRUSE", -5, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *args: fake)
    monkeypatch.setattr(socket, "gethostbyname", lambda host: "127.0.0.1")
    transport = UDPTransport("127.0.0.1", 65431, bind_port=65432, timeout=0)
    with pytest.raises(OSError, match="exclusive binding option rejected"):
        transport.open()
    assert calls == [("setsockopt", socket.SOL_SOCKET, -5, 1), ("close",)]
    assert transport.socket is None

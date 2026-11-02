"""A blocked Native event loop must recover without modal waits or stale writes."""
import re

import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.protocol import PACKET_PREFIX, parse_datagram
from spitfire.simulator import SimulatedTransport


class PauseView(MemoryView):
    native_timers = True

    def connection_presentation(self):
        return {"controls": {(6, 10): 0, (6, 11): 0, (5, 34): 0, (5, 35): 0, (2, 7): 0},
                "alarm": {500: 0, 641: "FAULT (click here)", 880: 0xffff00}}

    def set_connection_status(self, ready, message):
        pass

    def show_warning(self, *args):
        pytest.fail("Communication recovery must not enter a modal acknowledgement")


class ControlledBoard(SimulatedTransport):
    silent = False

    def receive(self):
        replies = super().receive()
        return [] if self.silent else replies


@pytest.fixture
def apps(monkeypatch):
    monkeypatch.setattr("socket.socket", lambda *a, **kw: pytest.fail("Pause recovery tests cannot open sockets"))
    controllers = []

    def make(*, native=True, read_only=False):
        now = [0.0]
        boards = []

        def factory():
            board = ControlledBoard()
            boards.append(board)
            return board

        monkeypatch.setattr("spitfire.controller.SimulatedTransport", factory)
        view = PauseView()
        view.native_timers = native
        app = Controller(view, demo=True, tcp_port=None, clock=lambda: now[0], read_only=read_only)
        controllers.append(app)
        return app, boards, now

    yield make
    for app in controllers:
        app.stop()


def settle(app, ticks=220):
    for _ in range(ticks):
        app.tick()


def lines(board):
    return [line for packet in board.sent_packets
            for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines()]


def tags(board):
    return [int(re.match(r"\[(\d+)\]", line)[1]) for line in lines(board)]


def start_ready(app):
    app.start()
    settle(app)
    assert app.state["gui_ready"] is True


def isolate(app, board, request=None):
    app.scheduler.clear()
    board.pending.clear()
    if request:
        app.scheduler.push(*request)
        app.tick()


def test_long_non_native_network_gap_reconnects_without_modal_warning(apps):
    app, boards, now = apps(native=False)
    start_ready(app)
    old = boards[0]
    old.silent = True
    app.state["pardon_first_time_user"] = 0
    now[0] = 31.0
    app.tick()
    assert len(boards) == 2
    assert app.diagnostics["connect_attempts"] == 2
    assert app.state["gui_ready"] is False
    assert tags(boards[1]) == [1000]
    settle(app)
    assert app.state["gui_ready"] is True
    assert app.diagnostics["gui_pause_events"] == 0


def test_native_pause_quarantines_cached_status_until_a_post_pause_probe_without_startup(apps):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    isolate(app, board, (1085, ""))
    before = len(lines(board))
    app.scheduler.push(2027)
    app.scheduler.push(2017)
    app.scheduler.push(2021, " 1.10")
    app.state["evnt_cmt"] = 1
    app._button_started = 0.0
    now[0] = 58.0
    app.tick()
    assert app.state["gui_ready"] is False
    assert app.state["curtain_not_open"] == 1
    assert app.state["evnt_cmt"] == 0
    assert app._button_started is None
    assert app._last_status_at == 0.0
    assert tags(board)[before:] == [1085]
    assert app.diagnostics["ignored_replies"] >= 1
    assert app.diagnostics["cancelled_run_holds"] == 1
    app.tick()  # Only the newly sent probe's response may reopen the UI.
    assert app.state["gui_ready"] is True
    assert app._last_status_at == 58.0
    assert len(boards) == 1
    assert all(tag < 2000 for tag in tags(board)[before:])
    assert app.diagnostics["gui_pause_events"] == 1
    assert app.diagnostics["connect_attempts"] == 1


def test_invalid_buffered_status_during_held_run_cannot_enable_the_gui_or_resume_run(apps):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    isolate(app, board, (1085, ""))
    board.pending.clear()
    board.pending.append(b"Spectra-Physics:REPLY_ECLIPSE:<1085>-99\n")
    app.state["evnt_cmt"] = 1
    app._button_started = 0.0
    app.scheduler.push(2027)
    before = len(lines(board))
    now[0] = 58.0
    app.tick()
    assert app.state["gui_ready"] is False
    assert app._last_status_at == 0.0
    assert app.state["evnt_cmt"] == 0
    assert app._button_started is None
    assert tags(board)[before:] == [1085]
    assert app.diagnostics["cancelled_run_holds"] == 1
    assert app.diagnostics["ignored_replies"] >= 1
    app.tick()
    assert app.state["gui_ready"] is True
    assert app._last_status_at == 58.0
    assert app.diagnostics["connect_attempts"] == 1
    assert 2027 not in tags(board)[before:]


def test_native_pause_probes_status_then_recovers_without_replaying_initialization(apps):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    isolate(app, board, (1040, ""))  # Cached voltage is not a fresh STATUS.
    before = len(lines(board))
    now[0] = 58.0
    app.tick()
    assert tags(board)[before:] == [1085]
    assert app.state["gui_ready"] is False
    assert app.state["curtain_not_open"] == 1
    app.tick()
    assert app.state["gui_ready"] is True
    assert app.state["curtain_not_open"] == 0
    assert app._last_status_at == 58.0
    assert app.diagnostics["connect_attempts"] == 1
    assert all(tag < 2000 for tag in tags(board)[before:])


def test_silent_native_pause_probe_retries_three_times_then_reconnects_automatically(apps):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    isolate(app, board)
    board.silent = True
    before = len(lines(board))
    now[0] = 58.0
    app.tick()
    for at in (58.71, 59.42, 60.13):
        now[0] = at
        app.tick()
    assert tags(board)[before:] == [1085, 1085, 1085]
    assert len(boards) == 2
    assert tags(boards[1]) == [1000]
    assert app.diagnostics["connect_attempts"] == 2
    assert app.state["gui_ready"] is False
    settle(app)
    assert app.state["gui_ready"] is True


def test_native_pause_before_first_status_preserves_unsent_default_optout_initialization(apps):
    app, boards, now = apps()
    app.start()
    for _ in range(8):
        if app.scheduler.default_optout_write is not None:
            break
        app.tick()
    board = boards[0]
    default = app.scheduler.default_optout_write
    assert default is not None and default in app.scheduler.inside
    assert 2036 not in tags(board)
    assert app._last_status_at is None
    app.scheduler.push(2027)
    app.state["evnt_cmt"] = 1
    app._button_started = 0.0
    now[0] = 58.0
    app.tick()
    assert default in app.scheduler.inside
    settle(app)
    assert tags(board).count(2036) == 1
    assert "[2036]EMPOPTOUT 1" in lines(board)
    assert 2027 not in tags(board)
    assert app.state["emp_optout"] == 1
    assert app.state["gui_ready"] is True
    assert app.diagnostics["connect_attempts"] == 1


def test_pause_cancels_stale_actuation_but_sends_only_exact_shutdowns_once_before_status(apps):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    isolate(app, board)
    shutdowns = [2006, 2013, 2016, 2023, 2028]
    for tag in shutdowns:
        app.scheduler.push(tag)
        app.scheduler.push(tag, " ")
        app.scheduler.push(tag, "\n[2027]ON")
    for tag, parameter in [(2005, ""), (2027, ""), (2017, ""), (2021, " 1.10"), (2034, "OFF")]:
        app.scheduler.push(tag, parameter, inside=False)
    app.state["evnt_cmt"] = 1
    app._button_started = 0.0
    before = len(lines(board))
    now[0] = 1.0
    app.notify_ui_pause("explicit menu-pause notification")
    assert [r.tag for r in app.scheduler.inside] == shutdowns
    assert not app.scheduler.outside
    assert app.state["evnt_cmt"] == 0
    assert app._button_started is None
    settle(app, 20)
    emitted = lines(board)[before:]
    emitted_tags = tags(board)[before:]
    assert emitted_tags[:6] == shutdowns + [1085]
    for tag in shutdowns:
        assert emitted_tags.count(tag) == 1
    assert all(tag < 2000 or tag in shutdowns for tag in emitted_tags)
    assert not any("\n" in line for line in emitted)
    assert app.state["gui_ready"] is True
    assert app.diagnostics["connect_attempts"] == 1


def test_recursive_tick_is_skipped_and_outer_tick_keeps_one_scheduler_owner(apps, monkeypatch):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    original = board.receive
    reentered = []

    def receive():
        if not reentered:
            reentered.append(True)
            app.tick()
        return original()

    monkeypatch.setattr(board, "receive", receive)
    before = len(lines(board))
    app.tick()
    assert app.diagnostics["reentrant_ticks_skipped"] == 1
    assert app._tick_active is False
    assert len(lines(board)) == before + 1


def test_tick_exception_releases_reentry_guard(apps, monkeypatch):
    app, boards, now = apps()

    def failed_tick():
        raise RuntimeError("synthetic Native callback failure")

    monkeypatch.setattr(app, "_tick_once", failed_tick)
    with pytest.raises(RuntimeError, match="synthetic Native callback failure"):
        app.tick()
    assert app._tick_active is False


def test_ordinary_run_cancel_removes_run_but_preserves_separate_empower_on_request(apps):
    app, boards, now = apps()
    start_ready(app)
    isolate(app, boards[0])
    app.scheduler.push(2005)
    app.scheduler.push(2027)
    app.scheduler.push(1040)
    app.scheduler.push(2027, inside=False)
    app.state["evnt_cmt"] = 1
    app._button_started = 0.0
    app.cancel_pending_run("ordinary mouse release")
    assert [r.tag for r in app.scheduler.inside] == [2005, 1040]
    assert not app.scheduler.outside
    assert app.state["evnt_cmt"] == 0
    assert app._button_started is None
    assert app.diagnostics["cancelled_run_requests"] == 2
    assert app.diagnostics["cancelled_run_holds"] == 1


def test_stale_status_cancels_queued_actuation_before_send_but_preserves_exact_shutdowns(apps):
    app, boards, now = apps(native=False)
    start_ready(app)
    board = boards[0]
    isolate(app, board)
    app.scheduler.push(2017)
    app.scheduler.push(2021, " 1.10")
    app.scheduler.push(2034, "[2027]ON")
    shutdowns = [2006, 2013, 2016, 2023, 2028]
    for tag in shutdowns:
        app.scheduler.push(tag)
    before = len(lines(board))
    now[0] = 31.0
    # Other actual query replies may remain fresh while STATUS alone is stale.
    app.scheduler.last_received = now[0]
    app._last_matched_at = now[0]
    app.tick()
    assert app.state["gui_ready"] is False
    assert app.diagnostics["status_stale_events"] == 1
    assert tags(board)[before:] == [2006]
    settle(app, 12)
    emitted = tags(board)[before:]
    assert emitted[:5] == shutdowns
    assert all(tag < 2000 or tag in shutdowns for tag in emitted)
    assert all(emitted.count(tag) == 1 for tag in shutdowns)
    assert app.diagnostics["cancelled_write_requests"] == 3
    assert app.diagnostics["connect_attempts"] == 1


def test_same_clock_pause_after_status_still_requires_a_new_probe_response(apps):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    isolate(app, board, (1040, ""))
    assert now[0] == app._last_status_at == 0.0
    before = len(lines(board))
    app.notify_ui_pause("same-clock menu notification")
    app.tick()
    assert app.state["gui_ready"] is False
    assert tags(board)[before:] == [1085]
    assert app._pause_recovery_since == 0.0
    app.tick()
    assert app.state["gui_ready"] is True
    assert app._pause_recovery_since is None
    assert app.diagnostics["connect_attempts"] == 1
    assert all(tag < 2000 for tag in tags(board)[before:])


def test_pause_waits_for_more_than_one_drain_batch_before_sending_the_status_probe(apps):
    app, boards, now = apps()
    start_ready(app)
    board = boards[0]
    isolate(app, board)
    for _ in range(64):
        board.pending.append(b"Spectra-Physics:REPLY_ECLIPSE:<1039>0\n")
    board.pending.append(b"Spectra-Physics:REPLY_ECLIPSE:<1085>0\n")
    before = len(lines(board))
    now[0] = 58.0
    app.tick()
    assert len(board.pending) == 1
    assert len(lines(board)) == before
    assert app.state["gui_ready"] is False
    assert app.state["curtain_not_open"] == 1
    assert app._pause_probe_sent is False
    assert app._last_status_at == 0.0
    assert app.diagnostics["pause_quarantine_wait_ticks"] >= 1
    app.tick()  # The 65th old frame is quarantined, then the queue is observed empty.
    assert tags(board)[before:] == [1085]
    assert app.state["gui_ready"] is False
    assert app._last_status_at == 0.0
    assert app._pause_probe_sent is True
    app.tick()  # Only the reply to the newly sent STATUS probe permits recovery.
    assert app.state["gui_ready"] is True
    assert app._last_status_at == 58.0
    assert app.diagnostics["connect_attempts"] == 1
    assert app.diagnostics["reconnects"] == 0
    assert all(tag < 2000 for tag in tags(board)[before:])


@pytest.mark.parametrize("read_only", [False, True])
def test_continuous_quarantine_preserves_shutdown_progress_without_unsafe_writes_or_replay(apps, monkeypatch, read_only):
    app, boards, now = apps(read_only=read_only)
    start_ready(app)
    board = boards[0]
    isolate(app, board)
    app.min_request_interval = 0.25
    shutdowns = [2006, 2013, 2016, 2023, 2028]
    for tag in shutdowns:
        app.scheduler.push(tag)
    app.scheduler.push(2017)
    app.scheduler.push(2034, "[2027]ON")
    app.scheduler.push(2027)
    # Every receive batch stays full, even after the five shutdowns are sent.
    monkeypatch.setattr(board, "receive", lambda: parse_datagram(b"Spectra-Physics:REPLY_ECLIPSE:<1085>0\n"))
    now[0] = 1.0
    app.notify_ui_pause("continuous buffered traffic")
    before = len(lines(board))
    for step in range(1, 13):
        now[0] = 1.0 + step * 0.25
        app.tick()
    emitted = tags(board)[before:]
    assert emitted == ([] if read_only else shutdowns)
    assert app.diagnostics["quarantine_shutdowns_sent"] == (0 if read_only else 5)
    assert app.state["gui_ready"] is False
    assert app.state["curtain_not_open"] == 1
    assert app._pause_probe_sent is False
    assert app._last_status_at == 0.0
    assert not app.scheduler.inside
    assert not app.scheduler.outside
    assert app.diagnostics["connect_attempts"] == 1
    if read_only:
        assert app.diagnostics["blocked_writes"] >= 5

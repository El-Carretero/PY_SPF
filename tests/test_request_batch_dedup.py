"""Regression coverage for Reset bursts and post-write fault readback ordering."""
from collections import Counter
import re

import pytest

from spitfire.__main__ import MemoryView
from spitfire.callbacks import dispatch, fault_update_actions
from spitfire.controller import Controller
from spitfire.protocol import PACKET_PREFIX
from spitfire.scheduling import (BWD_RESET_TAGS, FAULT_QUERY_TAGS,
                                 FAULT_RESET_TAGS, Scheduler)
from spitfire.simulator import SimulatedTransport


def entries(tags):
    return [(tag, "") for tag in tags]


def finish_all(queue, *, outcome="completed"):
    sent = []
    while queue.inside or queue.outside or queue.balance:
        request = queue.last_sent if queue.balance else queue.next_request(auto_poll=False)
        sent.append(request.tag)
        if outcome == "completed":
            assert queue.acknowledge(request.tag)
        else:
            queue.finish_current(outcome)
    return sent


def test_complete_reset_is_shared_while_queued_and_inflight_then_released():
    events = []
    queue = Scheduler(on_event=events.append)
    accepted = queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset")
    assert len(accepted) == 14
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is None
    request = queue.next_request(auto_poll=False)
    assert request.tag == 2044
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is None
    assert finish_all(queue) == list(FAULT_RESET_TAGS)
    assert queue.suppressed_reset_batches == 2
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is not None
    assert any(event["event"] == "batch_completed" and event["result"] == "completed"
               for event in events)


def test_fault_refresh_preserves_two_passes_and_never_crosses_write_barrier():
    queue = Scheduler()
    first = queue.queue_batch("fault_update", entries(FAULT_QUERY_TAGS), origin="health")
    assert queue.queue_batch("fault_update", entries(FAULT_QUERY_TAGS), origin="health") is None
    # This write requires another complete readback after it. Merely finding
    # the same query tags in the older batch must not suppress those reads.
    write = queue.push(2018, origin="BW_reset")
    second = queue.queue_batch("fault_update", entries(FAULT_QUERY_TAGS), origin="health")
    assert len(first) == len(second) == 10
    assert queue.queue_batch("fault_update", entries(FAULT_QUERY_TAGS), origin="health") is None
    assert list(queue.inside) == first + [write] + second
    assert finish_all(queue) == list(FAULT_QUERY_TAGS) + [2018] + list(FAULT_QUERY_TAGS)


def test_reset_readback_can_satisfy_fault_refresh_after_its_writes():
    queue = Scheduler()
    queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset")
    assert queue.queue_batch("fault_update", entries(FAULT_QUERY_TAGS), origin="health") is None
    assert finish_all(queue) == list(FAULT_RESET_TAGS)
    assert queue.suppressed_fault_batches == 1


def test_refresh_before_reset_cannot_replace_reset_post_write_readback():
    queue = Scheduler()
    queue.queue_batch("fault_update", entries(FAULT_QUERY_TAGS), origin="health")
    queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset")
    assert finish_all(queue) == list(FAULT_QUERY_TAGS) + list(FAULT_RESET_TAGS)


def test_bwd_reset_has_separate_lock_and_preserves_its_readback():
    queue = Scheduler()
    queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset")
    assert queue.queue_batch("bwd_reset", entries(BWD_RESET_TAGS), origin="BW_reset") is not None
    assert queue.queue_batch("bwd_reset", entries(BWD_RESET_TAGS), origin="BW_reset") is None
    assert finish_all(queue) == list(FAULT_RESET_TAGS) + list(BWD_RESET_TAGS)
    assert queue.queue_batch("bwd_reset", entries(BWD_RESET_TAGS), origin="BW_reset") is not None


@pytest.mark.parametrize("outcome", ["timeout", "canceled"])
def test_terminal_members_release_lock_without_overlapping_remaining_reset(outcome):
    events = []
    queue = Scheduler(on_event=events.append)
    queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset")
    queue.next_request(auto_poll=False)
    queue.finish_current(outcome)
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is None
    finish_all(queue, outcome=outcome)
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is not None
    assert any(event["event"] == "batch_completed" and event["result"] == outcome
               for event in events)


def test_queued_cancellation_and_clear_release_batch_tracking():
    queue = Scheduler()
    queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset")
    assert queue.remove_queued(lambda request: True) == 14
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is not None
    queue.next_request(auto_poll=False)
    queue.clear(reason="reconnect")
    assert queue.balance == 0
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is not None


def test_partial_enqueue_failure_cannot_leave_reset_members_or_lock(monkeypatch):
    queue = Scheduler()
    push = queue.push

    def fail_after_reset_writes(tag, parameter="", **kwargs):
        if tag == 1089:
            raise RuntimeError("enqueue failed")
        return push(tag, parameter, **kwargs)

    monkeypatch.setattr(queue, "push", fail_after_reset_writes)
    with pytest.raises(RuntimeError, match="enqueue failed"):
        queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset")
    assert not queue.inside
    monkeypatch.setattr(queue, "push", push)
    assert queue.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="reset") is not None


class DroppingBoard(SimulatedTransport):
    def __init__(self):
        super().__init__()
        self.drop = Counter()

    def receive(self):
        replies = []
        for reply in super().receive():
            tag = int(re.match(r"<(\d+)>", reply.body)[1])
            if self.drop[tag]:
                self.drop[tag] -= 1
            else:
                replies.append(reply)
        return replies


@pytest.fixture
def running_app(monkeypatch, tmp_path):
    monkeypatch.setattr("socket.socket", lambda *a, **kw: pytest.fail("Offline test opened a socket"))
    board = DroppingBoard()
    now = [0.0]
    monkeypatch.setattr("spitfire.controller.SimulatedTransport", lambda: board)
    app = Controller(MemoryView(), demo=True, tcp_port=None, data_dir=tmp_path,
                     clock=lambda: now[0], min_request_interval=0.25)
    app.start()
    advance(app, now, 25)
    assert app.state["gui_ready"]
    app.scheduler.clear()
    board.pending.clear()
    app._last_status_at = now[0]
    app._next_send_at = now[0]
    yield app, board, now
    app.stop()


def advance(app, now, seconds):
    stop = now[0] + seconds
    while now[0] < stop:
        now[0] = min(stop, now[0] + 0.01)
        app.tick()


def wire_tags(board):
    return [int(re.match(r"\[(\d+)\]", line)[1])
            for packet in board.sent_packets
            for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines()]


def test_eight_reset_clicks_do_not_starve_existing_status_poll(running_app):
    app, board, now = running_app
    app.scheduler.queue_poll()
    before = len(wire_tags(board))
    started = now[0]
    for _ in range(8):
        app.handle_callback("cllbckcmd_reset")
    app.handle_callback("parse_command5", event=3)  # Existing TEC OFF FIFO behavior.
    assert len(app.scheduler.inside) == 16  # One 14-request Reset plus OFF/readback.
    advance(app, now, 13)
    emitted = wire_tags(board)[before:]
    assert [tag for tag in emitted if tag in (2044, 2049, 2052, 2050)] == [2044, 2049, 2052, 2050]
    assert 2028 in emitted
    assert 1085 in emitted
    assert app._last_status_at - started < 13
    assert app.diagnostics["status_stale_events"] == 0
    assert app.state["gui_ready"]
    assert app.communication_diagnostics()["suppressed_reset_batches"] == 7
    sent = [payload for _, kind, payload in app.events
            if kind == "QUEUE" and payload["event"] == "sent" and payload["tag"] == 2028]
    assert sent and sent[0]["wait_seconds"] < 4


def test_controller_fault_effect_coalesces_only_until_a_new_write(running_app):
    app, _, _ = running_app
    for _ in range(3):
        app.decoder.effects = [("fault_update", True)]
        app._decoder_effects()
    assert [request.tag for request in app.scheduler.inside] == list(FAULT_QUERY_TAGS)
    app.apply(dispatch("BW_reset", event=3))
    app.apply(fault_update_actions(), automatic=True)
    assert [request.tag for request in app.scheduler.inside] == (
        list(FAULT_QUERY_TAGS) + list(BWD_RESET_TAGS) + list(FAULT_QUERY_TAGS))
    assert app.scheduler.suppressed_fault_batches == 2


def test_controller_exhausted_last_query_releases_reset_lock(running_app):
    app, board, now = running_app
    app.handle_callback("cllbckcmd_reset")
    # Finish all but the final read without letting an automatic poll intrude.
    for tag in FAULT_RESET_TAGS[:-1]:
        request = app.scheduler.next_request(auto_poll=False)
        assert request.tag == tag
        assert app.scheduler.acknowledge(tag)
    board.drop[1057] = 3
    app.tick()
    app.handle_callback("cllbckcmd_reset")
    assert app.scheduler.suppressed_reset_batches == 1
    advance(app, now, 2.2)
    assert app.diagnostics["query_timeouts"] == 1
    app.handle_callback("cllbckcmd_reset")
    assert any(request.tag == 2044 for request in app.scheduler.inside)
    assert app.scheduler.suppressed_reset_batches == 1


def test_controller_cancel_keeps_original_reads_and_releases_after_they_finish(running_app):
    app, _, _ = running_app
    app.handle_callback("cllbckcmd_reset")
    app.cancel_pending_actuation()
    assert [request.tag for request in app.scheduler.inside] == list(FAULT_QUERY_TAGS)
    app.handle_callback("cllbckcmd_reset")
    assert app.scheduler.suppressed_reset_batches == 1
    finish_all(app.scheduler)
    app.handle_callback("cllbckcmd_reset")
    assert [request.tag for request in app.scheduler.inside] == list(FAULT_RESET_TAGS)


def test_diagnostics_include_queue_origin_wait_and_ids(running_app):
    app, _, now = running_app
    app.handle_callback("cllbckcmd_reset")
    app.tick()
    now[0] += 0.1
    snapshot = app.communication_diagnostics()
    assert snapshot["queue_inside"] == snapshot["queue_total"] == 13
    assert snapshot["pending_tag"] == 2044
    assert snapshot["pending_request_id"] is not None
    assert snapshot["pending_origin"] == "cllbckcmd_reset"
    assert snapshot["pending_batch_id"].startswith("fault_reset:")
    assert snapshot["pending_wait_seconds"] == pytest.approx(0.1)
    assert snapshot["oldest_queued_age_seconds"] == pytest.approx(0.1)


def test_reconnect_and_stop_release_controller_batch_state(running_app):
    app, _, _ = running_app
    app.handle_callback("cllbckcmd_reset")
    app.connect()
    assert app.scheduler.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="test") is not None
    app.stop()
    assert app.scheduler.queue_batch("fault_reset", entries(FAULT_RESET_TAGS), origin="test") is not None

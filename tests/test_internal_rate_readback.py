"""Frequency confirmation is a matched device readback, never an edited widget."""
import math

import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.decoders import ResponseDecoder, parse_internal_trigger_reply
from spitfire.protocol import PACKET_PREFIX
from spitfire.simulator import SimulatedTransport


class RateBoard(SimulatedTransport):
    def __init__(self):
        super().__init__()
        self.reject_write = False
        self.readback = None
        self.drop_readback = False
        self.drop_write_ack = False

    def _command(self, tag, title, parameter):
        if tag != 2032 or not self.reject_write:
            super()._command(tag, title, parameter)

    def send_packet(self, packet):
        if b'[1053]' in packet and self.readback is not None:
            self.values['TDG:TRIG:FREQ?'] = self.readback
        super().send_packet(packet)
        if b'[2032]' in packet and self.reject_write:
            self.pending[-1] = self.pending[-1].replace(b'<2032>0', b'<2032>ERROR unsupported')

    def receive(self):
        return [reply for reply in super().receive()
                if not (self.drop_readback and reply.body.startswith('<1053>'))
                and not (self.drop_write_ack and reply.body.startswith('<2032>'))]


def packets(board):
    return [line for packet in board.sent_packets
            for line in packet[len(PACKET_PREFIX):].decode('ascii').splitlines()]


def settle(controller, ticks=20):
    for _ in range(ticks):
        controller.tick()


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setattr('socket.socket', lambda *a, **kw: pytest.fail('Frequency tests must not open sockets'))
    created = []

    def make(*, read_only=False):
        now = [0.0]
        board = RateBoard()
        monkeypatch.setattr('spitfire.controller.SimulatedTransport', lambda: board)
        controller = Controller(MemoryView(), demo=True, tcp_port=None,
                                read_only=read_only, clock=lambda: now[0])
        created.append(controller)
        controller.start()
        settle(controller, 220)
        assert controller.state['gui_ready']
        assert controller.state['internal_trigger_actual_hz'] == 1000
        assert controller.state['internal_trigger_requested_hz'] is None
        controller.scheduler.clear()
        board.pending.clear()
        monkeypatch.setattr(controller.scheduler, 'queue_poll', lambda: None)
        board.sent_packets.clear()
        return controller, board, now

    yield make
    for controller in created:
        controller.stop()


def commit(controller, value=10):
    # CVI changes its editable widget before delivering EVENT_COMMIT.
    controller.view.set_value(5, 28, value)
    controller.handle_callback('trig_reprate', value, event=1, panel=5, control=28)


def test_closed_loop_off_waits_for_actual_readback_before_displaying_ten(application):
    controller, board, _ = application()
    assert controller.read(6, 48) == 0
    commit(controller)
    assert controller.view.read(5, 28) == 1000
    assert controller.state['internal_trigger_pending']
    assert not controller.state['internal_trigger_confirmed']
    settle(controller)
    assert packets(board) == ['[2032]TDG:TRIG:FREQ 10.00', '[1053]TDG:TRIG:FREQ?']
    assert controller.state['internal_trigger_actual_hz'] == 10
    assert controller.state['internal_trigger_requested_hz'] == 10
    assert not controller.state['internal_trigger_pending']
    assert controller.state['internal_trigger_confirmed']
    assert controller.state['internal_trigger_result'] == 'confirmed'
    assert controller.view.read(5, 28) == controller.view.read(6, 8) == 10


def test_negative_write_receipt_and_old_readback_do_not_confirm_ten(application):
    controller, board, _ = application()
    board.reject_write = True
    commit(controller)
    settle(controller)
    assert controller.state['internal_trigger_requested_hz'] == 10
    assert controller.state['internal_trigger_actual_hz'] == controller.view.read(5, 28) == 1000
    assert not controller.state['internal_trigger_pending']
    assert not controller.state['internal_trigger_confirmed']
    assert controller.state['internal_trigger_result'] == 'mismatch'
    assert any(kind == 'frequency' and 'NOT confirmed' in text for _, kind, text in controller.events)


@pytest.mark.parametrize('payload', ['ERROR', 'nan', 'inf', '-inf', '10junk', '10 Hz',
                                    '1e999', '0', '-99', '9.99', '10000.01', ''])
def test_invalid_readback_preserves_last_actual_and_never_confirms(application, payload):
    controller, board, _ = application()
    board.readback = payload
    commit(controller)
    settle(controller)
    assert controller.state['internal_trigger_actual_hz'] == controller.view.read(5, 28) == 1000
    assert not controller.state['internal_trigger_pending']
    assert not controller.state['internal_trigger_confirmed']
    assert controller.state['internal_trigger_result'] == 'invalid_readback'
    assert controller.diagnostics['malformed_replies'] == 1


def test_missing_readback_times_out_without_replaying_the_write(application):
    controller, board, now = application()
    board.drop_readback = True
    commit(controller)
    settle(controller)
    for instant in (0.71, 1.42, 2.13):
        now[0] = instant
        settle(controller)
    assert packets(board).count('[2032]TDG:TRIG:FREQ 10.00') == 1
    assert packets(board).count('[1053]TDG:TRIG:FREQ?') == 3
    assert controller.view.read(5, 28) == controller.state['internal_trigger_actual_hz'] == 1000
    assert not controller.state['internal_trigger_pending']
    assert not controller.state['internal_trigger_confirmed']
    assert controller.state['internal_trigger_result'] == 'readback_timeout'


def test_lost_write_ack_can_be_confirmed_by_actual_readback_without_write_replay(application):
    controller, board, now = application()
    board.drop_write_ack = True
    commit(controller)
    settle(controller)
    now[0] = 1.01
    settle(controller)
    assert packets(board) == ['[2032]TDG:TRIG:FREQ 10.00', '[1053]TDG:TRIG:FREQ?']
    assert controller.state['internal_trigger_confirmed']
    assert controller.state['internal_trigger_actual_hz'] == 10


def test_read_only_edit_is_restored_and_creates_no_request(application):
    controller, board, _ = application(read_only=True)
    commit(controller)
    settle(controller)
    assert not packets(board)
    assert controller.view.read(5, 28) == 1000
    assert controller.state['internal_trigger_requested_hz'] is None
    assert not controller.state['internal_trigger_pending']
    assert not controller.state['internal_trigger_confirmed']


def test_unrelated_older_readback_cannot_confirm_the_new_transaction(application):
    controller, board, _ = application()
    controller.scheduler.push(1053)
    commit(controller)
    controller.tick()  # The preexisting query is transmitted ahead of the write.
    controller.tick()  # Its response updates actual, but cannot confirm this edit.
    assert controller.state['internal_trigger_pending']
    assert not controller.state['internal_trigger_confirmed']
    settle(controller)
    assert controller.state['internal_trigger_confirmed']


def test_overlapping_commit_does_not_replace_the_pending_request(application):
    controller, board, _ = application()
    commit(controller, 10)
    commit(controller, 20)
    assert controller.state['internal_trigger_requested_hz'] == 10
    assert controller.view.read(5, 28) == 1000
    settle(controller)
    assert packets(board) == ['[2032]TDG:TRIG:FREQ 10.00', '[1053]TDG:TRIG:FREQ?']
    assert controller.state['internal_trigger_actual_hz'] == 10
    assert controller.state['internal_trigger_confirmed']


def test_no_actual_frequency_yet_blocks_edit_instead_of_confirming_default():
    view = MemoryView()
    view.set_value(5, 28, 5000)
    controller = Controller(view, demo=True, tcp_port=None)
    commit(controller)
    assert not controller.scheduler.inside
    assert controller.view.read(5, 28) == 5000
    assert controller.state['internal_trigger_actual_hz'] is None
    assert not controller.state['internal_trigger_pending']
    assert not controller.state['internal_trigger_confirmed']


@pytest.mark.parametrize('payload,expected', [('10', 10), ('  +1.0e1\r\n', 10), ('10000.00', 10000)])
def test_strict_frequency_reply_accepts_complete_finite_numbers(payload, expected):
    assert parse_internal_trigger_reply(payload) == expected


def test_legacy_numeric_decoder_sentinel_is_preserved_but_not_a_valid_live_setting():
    decoder = ResponseDecoder()
    updates = decoder.decode(1053, '-99')
    assert next(u.value for u in updates if (u.panel_id, u.control_id) == (5, 28)) == -99
    assert math.isfinite(parse_internal_trigger_reply('-99'))

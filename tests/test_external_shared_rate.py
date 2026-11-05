"""EXT rate displays use the confirmed shared input, not Empower or OSC Hz."""
import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.protocol import PACKET_PREFIX
from spitfire.simulator import SimulatedTransport


class SharedRateBoard(SimulatedTransport):
    def __init__(self):
        super().__init__()
        self.values.update({'TDG:TRIG:MODE?': 'EXT', 'TDG:DIV?': '1',
                            'TDG:TRIG:FREQ?': '1000', 'EMP:QSW:PRF?': '1000'})
        self.reject_frequency = False
        self.forced_readback = None
        self.drop_frequency_readback = False

    def _command(self, tag, title, parameter):
        if tag != 2032 or not self.reject_frequency:
            super()._command(tag, title, parameter)

    def send_packet(self, packet):
        if b'[1053]' in packet and self.forced_readback is not None:
            self.values['TDG:TRIG:FREQ?'] = self.forced_readback
        super().send_packet(packet)

    def receive(self):
        return [line for line in super().receive()
                if not (self.drop_frequency_readback and line.body.startswith('<1053>'))]


class PresentedView(MemoryView):
    def connection_presentation(self):
        return {'controls': {(6, 7): 0, (6, 9): 0, (5, 28): 0},
                'alarm': {500: 0, 641: 'ALL SYS OK', 880: 0xc0c0c0}}


def settle(controller, count=24):
    for _ in range(count):
        controller.tick()


def messages(board):
    return [line for packet in board.sent_packets
            for line in packet[len(PACKET_PREFIX):].decode('ascii').splitlines()]


def ext_rates(controller):
    return controller.read(6, 9), controller.read(6, 7)


def commit(controller, frequency):
    controller.view.set_value(5, 28, frequency)
    controller.handle_callback('trig_reprate', frequency, event=1, panel=5, control=28)


@pytest.fixture
def application(monkeypatch):
    monkeypatch.setattr('socket.socket', lambda *a, **kw: pytest.fail('Shared-rate tests must not open sockets'))
    created = []

    def make(*, read_only=False, presented=False):
        now = [0.0]
        board = SharedRateBoard()
        monkeypatch.setattr('spitfire.controller.SimulatedTransport', lambda: board)
        controller = Controller(PresentedView() if presented else MemoryView(),
                                demo=True, read_only=read_only, tcp_port=None,
                                clock=lambda: now[0])
        created.append(controller)
        controller.start()
        settle(controller, 240)
        assert controller.state['gui_ready']
        assert controller.read(5, 3) == 1  # External Amplifier Trigger
        assert controller.state['internal_trigger_actual_hz'] == 1000
        controller.scheduler.clear()
        board.pending.clear()
        monkeypatch.setattr(controller.scheduler, 'queue_poll', lambda: None)
        board.sent_packets.clear()
        return controller, board, now

    yield make
    for controller in created:
        controller.stop()


def test_external_ten_hz_waits_for_readback_and_sends_only_existing_frequency_pair(application):
    controller, board, _ = application()
    assert ext_rates(controller) == (1000, 1000)
    commit(controller, 10)
    assert ext_rates(controller) == (1000, 1000)
    assert controller.read(5, 28) == 1000
    settle(controller)
    assert messages(board) == ['[2032]TDG:TRIG:FREQ 10.00', '[1053]TDG:TRIG:FREQ?']
    assert ext_rates(controller) == (10, 10)
    assert controller.read(5, 28) == controller.read(6, 8) == controller.read(6, 6) == 10
    assert controller.state['internal_trigger_confirmed']
    assert board.values['TDG:TRIG:MODE?'] == 'EXT'
    assert board.values['TDG:HV:ON?'] == '0'


@pytest.mark.parametrize('closed_loop', [0, 1])
def test_divisor_two_recalculates_external_amp_and_keeps_external_pump_ten(application, closed_loop):
    controller, board, _ = application()
    commit(controller, 10)
    settle(controller)
    board.sent_packets.clear()
    controller.view.set_value(6, 48, closed_loop)
    controller.view.set_value(5, 43, 2)
    controller.handle_callback('DivisorCallback', 2, event=1, panel=5, control=43)
    settle(controller)
    assert ext_rates(controller) == (10, 5)
    assert messages(board) == (['[2020]TDG:DIV  2.00', '[1025]TDG:DIV?']
                               if closed_loop else ['[2020]TDG:DIV  2.00'])


def test_empower_and_oscillator_queries_cannot_replace_external_shared_source(application):
    controller, board, _ = application()
    commit(controller, 10)
    settle(controller)
    cached_empower = controller.read(9, 9)
    board.values['EMP:QSW:PRF?'] = '2345'
    for tag in (1010, 1024, 1062):
        controller.scheduler.push(tag)
        settle(controller)
        assert ext_rates(controller) == (10, 10)
    assert controller.read(9, 4) == 23450
    assert controller.read(9, 9) == cached_empower
    assert controller.state['internal_trigger_actual_hz'] == 10
    # Preserve the original decoder's 1024 field write; it is not the EXT source.
    assert controller.read(5, 28) != 10


def test_initial_empower_fill_cannot_replace_external_rate(application):
    controller, board, _ = application()
    commit(controller, 10)
    settle(controller)
    controller.state['initial_secrets_fill'] = 1
    board.values['EMP:QSW:PRF?'] = '2500'
    controller.scheduler.push(1010)
    settle(controller)
    assert controller.read(9, 9) == controller.read(9, 4) == 25000
    assert ext_rates(controller) == (10, 10)


def test_local_empower_callback_preserves_its_own_setting_without_overwriting_external_rates(application):
    controller, board, _ = application()
    commit(controller, 10)
    settle(controller)
    board.sent_packets.clear()
    controller.view.set_value(6, 48, 0)
    controller.view.set_value(9, 9, 2340)
    controller.handle_callback('slideqswprf', 2340, event=1, panel=9, control=9)
    settle(controller)
    assert messages(board) == ['[2004]EMP:QSW:PRF 234.00']
    assert controller.read(9, 9) == 2340
    assert ext_rates(controller) == (10, 10)


def test_mismatching_readback_keeps_external_reference_at_actual_thousand(application):
    controller, board, _ = application()
    board.reject_frequency = True
    commit(controller, 10)
    settle(controller)
    assert controller.state['internal_trigger_result'] == 'mismatch'
    assert ext_rates(controller) == (1000, 1000)
    assert controller.read(5, 28) == 1000
    assert messages(board) == ['[2032]TDG:TRIG:FREQ 10.00', '[1053]TDG:TRIG:FREQ?']


@pytest.mark.parametrize('payload', ['', 'ERROR', '10 Hz', '10000.1'])
def test_invalid_readback_never_publishes_requested_external_ten(application, payload):
    controller, board, _ = application()
    board.forced_readback = payload
    commit(controller, 10)
    settle(controller)
    assert controller.state['internal_trigger_result'] == 'invalid_readback'
    assert ext_rates(controller) == (1000, 1000)


def test_timeout_preserves_external_actual_and_never_replays_frequency_write(application):
    controller, board, now = application()
    board.drop_frequency_readback = True
    commit(controller, 10)
    settle(controller)
    for instant in (.71, 1.42, 2.13):
        now[0] = instant
        settle(controller)
    assert controller.state['internal_trigger_result'] == 'readback_timeout'
    assert ext_rates(controller) == (1000, 1000)
    assert messages(board).count('[2032]TDG:TRIG:FREQ 10.00') == 1


def test_readonly_does_not_write_or_publish_a_local_edit(application):
    controller, board, _ = application(read_only=True)
    commit(controller, 10)
    settle(controller)
    assert messages(board) == []
    assert controller.read(5, 28) == 1000
    assert ext_rates(controller) == (1000, 1000)


def test_older_unrelated_query_does_not_publish_pending_requested_value(application):
    controller, board, _ = application()
    controller.scheduler.push(1053)
    commit(controller, 10)
    controller.tick()
    controller.tick()
    assert controller.state['internal_trigger_pending']
    assert ext_rates(controller) == (1000, 1000)
    settle(controller)
    assert ext_rates(controller) == (10, 10)


def test_reconnect_and_oscillator_response_cannot_reuse_an_unverified_external_source(application):
    controller, board, _ = application(presented=True)
    commit(controller, 10)
    settle(controller)
    assert ext_rates(controller) == (10, 10)
    assert controller.attributes[6, 7, 500] == controller.attributes[6, 9, 500] == 0
    board.forced_readback = 'ERROR'
    controller.connect()
    assert ext_rates(controller) == (0, 0)
    assert controller.attributes[6, 7, 500] == controller.attributes[6, 9, 500] == 1
    settle(controller, 240)
    controller.scheduler.push(1085)
    settle(controller)
    # A valid STATUS may open the GUI despite unavailable 1053. The EXT source
    # remains unavailable rather than displaying an OSC/Empower/default value.
    assert controller.state['gui_ready']
    assert controller.state['internal_trigger_actual_hz'] is None
    assert ext_rates(controller) == (0, 0)
    assert controller.attributes[6, 7, 500] == controller.attributes[6, 9, 500] == 1
    board.forced_readback = '10'
    controller.scheduler.push(1053)
    settle(controller)
    assert ext_rates(controller) == (10, 10)
    assert controller.attributes[6, 7, 500] == controller.attributes[6, 9, 500] == 0

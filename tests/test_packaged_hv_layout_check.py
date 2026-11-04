"""HV layout verification regressions; real NI rendering is tested on Windows."""
import ctypes
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.native import RESOURCES
from spitfire.packaged_check import (
    _SimulatorWriteGuard, _assert_timing_rectangles, _control_rectangle,
    _exercise_timing_hv_layout, _packet_messages,
)
from spitfire.simulator import SimulatedTransport


def rectangle(left, top, width, height):
    return dict(left=left, top=top, width=width, height=height)


def test_original_hv_position_overlaps_mode_labels_even_with_separate_hit_targets():
    original = {
        34: rectangle(312, 354, 38, 50),
        48: rectangle(282, 311, 92, 95),
        7: rectangle(18, 328, 146, 77),
        43: rectangle(162, 349, 75, 49),
    }
    with pytest.raises(AssertionError, match='overlapping timing controls'):
        _assert_timing_rectangles(original, width=390, height=446)


def test_new_full_control_and_label_extents_fit_and_do_not_overlap():
    new = {
        34: rectangle(170, 299, 90, 71),
        48: rectangle(282, 311, 92, 95),
        7: rectangle(18, 361, 146, 77),
        43: rectangle(170, 382, 75, 49),
        5: rectangle(126, 265, 249, 29),
    }
    _assert_timing_rectangles(new, width=390, height=446)
    new[7]['height'] = 90  # Native/font growth past the lower panel edge.
    with pytest.raises(AssertionError, match='clipped timing control'):
        _assert_timing_rectangles(new, width=390, height=446)


def test_rectangle_probe_reads_ni_full_bounds_without_a_setter():
    class Call:
        calls = []

        def __call__(self, panel, control, *pointers):
            self.calls.append((panel, control))
            for pointer, value in zip(pointers, (299, 170, 71, 90)):
                pointer._obj.value = value
            return 0

    call = Call()
    view = SimpleNamespace(panels={5: 555}, dll=SimpleNamespace(GetCtrlBoundingRect=call),
                           _check=lambda result, label: result)
    assert _control_rectangle(view, 5, 34) == rectangle(170, 299, 90, 71)
    assert call.calls == [(555, 34)]
    assert call.argtypes == [ctypes.c_int, ctypes.c_int] + [ctypes.POINTER(ctypes.c_int)] * 4


@pytest.mark.parametrize('original_hv_fixture', ['0', ' 0.0'])
def test_full_layout_phase_uses_only_queries_and_restores_simulated_hv(monkeypatch, tmp_path, original_hv_fixture):
    def no_socket(*args, **kwargs):
        pytest.fail('Layout verification unit test must not create a socket')

    monkeypatch.setattr('socket.socket', no_socket)

    class Board(_SimulatorWriteGuard, SimulatedTransport):
        pass

    class View(MemoryView):
        def __init__(self):
            super().__init__()
            self.spec = json.loads((RESOURCES / 'gui_spec.json').read_text())
            self.defaults = {(p['id'], c['id']): dict(c['attributes'])
                             for p in self.spec['panels'] for c in p['controls']}

        def read_attribute(self, panel, control, attr):
            attributes = json.loads((RESOURCES / 'cvi_attributes.json').read_text())
            names = {v['id']: k.removeprefix('ATTR_').lower() for k, v in attributes.items()}
            return self.attributes.get((panel, control, attr), self.defaults[panel, control].get(names[attr], 0))

        def process_events(self):
            pass

    now = [0.0]
    view = View()
    board = Board()
    board.values['TDG:HV:ON?'] = original_hv_fixture
    monkeypatch.setattr('spitfire.controller.SimulatedTransport', lambda: board)
    controller = Controller(view, demo=True, tcp_port=None, clock=lambda: now[0])

    class Ticker:
        def tick(self):
            now[0] += .01
            controller.tick()

        def raise_if_failed(self):
            pass

    ticker = Ticker()
    for c in (34, 7, 43):
        assert view.defaults[5, c]['visible'] == 1

    def panel_attr(target, panel, attribute):
        if attribute == 530:
            return int(target.panels.get(panel, False))
        return target.panel_attributes[panel, attribute]

    def control_rect(target, panel, control):
        top, left, height, width = target.defaults[panel, control]['bounding_rect']
        return rectangle(left, top, width, height)

    snapshots = []
    monkeypatch.setattr('spitfire.packaged_check._panel_attribute', panel_attr)
    monkeypatch.setattr('spitfire.packaged_check._control_rectangle', control_rect)
    monkeypatch.setattr('spitfire.packaged_check._snapshot', lambda target, path, *, panel=6: snapshots.append((Path(path).name, panel)))
    monkeypatch.setattr('spitfire.packaged_check.time.sleep', lambda _: None)
    try:
        controller.start()
        for _ in range(220):
            ticker.tick()
        assert controller.state['gui_ready']
        assert view.read(5, 34) == 0
        before = len(board.sent_packets)
        report = {}
        _exercise_timing_hv_layout(view, controller, ticker, report, snapshot=tmp_path / 'native-self-test.bmp')
        result = report['timing_hv_layout']
        assert result['restored'] and result['hv_commands_sent'] == []
        assert [r['level'] for r in result['access_levels']] == [0, 1, 2, 3]
        assert [r['hv_display'] for r in result['access_levels']] == [0, 1, 1, 1]
        assert snapshots == [('native-self-test_timing_user.bmp', 5), ('native-self-test_timing_service.bmp', 5)]
        messages = _packet_messages(board.sent_packets[before:])
        assert messages.count('[1061]TDG:HV:ON?') == 2
        assert all(int(message[1:message.index(']')]) < 2000 for message in messages)
        assert board.values['TDG:HV:ON?'] == original_hv_fixture and view.read(5, 34) == 0
        assert controller.state['gAccessLevel'] == 0
    finally:
        controller.stop()

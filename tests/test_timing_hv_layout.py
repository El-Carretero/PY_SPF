"""The exposed HV control must remain visible, separate and presentation-only."""
import ctypes
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from spitfire.layout import (
    HV_SWITCH_LABEL, TIMING_HV_LAYOUT, TIMING_HV_NATIVE_ATTRIBUTES,
)
from spitfire.native import NativeGui, RESOURCES


def timing_panel():
    spec = json.loads((RESOURCES / 'gui_spec.json').read_text())
    return next(panel for panel in spec['panels'] if panel['id'] == 5)


def full_rect(control):
    attrs = control['attributes']
    top, left, height, width = attrs['bounding_rect']
    return left, top, left + width, top + height


def intersects(first, second):
    return (first[0] < second[2] and second[0] < first[2]
            and first[1] < second[3] and second[1] < first[3])


def test_native_and_portable_geometry_share_an_explicit_visible_hv_control():
    controls = {control['id']: control for control in timing_panel()['controls']}
    for control_id, attributes in TIMING_HV_LAYOUT.items():
        for name, value in attributes.items():
            if name == 'bounding_rect':
                value = list(value)
            assert controls[control_id]['attributes'][name] == value
    hv = controls[34]
    assert hv['attributes']['visible'] == 1
    assert hv['attributes']['hidden_when_loaded'] == 0
    assert hv['attributes']['label_text'] == HV_SWITCH_LABEL
    assert hv['value'] == hv['attributes']['value'] == hv['attributes']['dflt_value'] == 0
    assert hv['callback'] == 'HV_switch'


@pytest.mark.parametrize('width,height', [(390, 446), (750, 446), (750, 546)])
def test_hv_and_its_label_fit_each_access_layout_without_overlapping_any_visible_control(width, height):
    controls = timing_panel()['controls']
    hv = full_rect(next(control for control in controls if control['id'] == 34))
    assert 0 <= hv[0] < hv[2] <= width
    assert 0 <= hv[1] < hv[3] <= height
    for control in controls:
        attrs = control['attributes']
        if control['id'] == 34 or not attrs.get('visible', 1):
            continue
        other = full_rect(control)
        assert not intersects(hv, other), (control['id'], hv, other)
        if attrs.get('label_text') and attrs.get('label_visible', 1) and 'label_left' in attrs:
            label = (attrs['label_left'], attrs['label_top'],
                     attrs['label_left'] + attrs['label_width'],
                     attrs['label_top'] + attrs['label_height'])
            assert not intersects(hv, label), (control['id'], hv, label)
    for control_id in (7, 43):
        bounds = full_rect(next(control for control in controls if control['id'] == control_id))
        assert bounds[3] <= height
        for other in controls:
            if other['id'] != control_id and other['attributes'].get('visible', 1):
                assert not intersects(bounds, full_rect(other)), (control_id, other['id'])


def test_native_layout_override_sets_attributes_without_changing_a_hardware_value():
    view = NativeGui.__new__(NativeGui)
    view.controller = None
    view.panels = {5: 505}
    view.values = {(5, 34): 0, (5, 7): 79390000.0, (5, 43): 1.0}
    initial = dict(view.values)
    view.attributes = json.loads((RESOURCES / 'cvi_attributes.json').read_text())
    view._bytes = lambda value: str(value).encode('ascii')
    view.varargs = SimpleNamespace(SetCtrlAttribute=Mock(return_value=0), SetCtrlVal=Mock())
    view._configure_timing_hv_layout()
    calls = view.varargs.SetCtrlAttribute.call_args_list
    assert len(calls) == len(TIMING_HV_NATIVE_ATTRIBUTES)
    for call, (control, attribute, value) in zip(calls, TIMING_HV_NATIVE_ATTRIBUTES):
        assert call.args[:3] == (505, control, attribute)
        argument = call.args[3]
        assert isinstance(argument, ctypes.c_char_p if isinstance(value, str) else ctypes.c_int)
        assert argument.value == (value.encode('ascii') if isinstance(value, str) else value)
    view.varargs.SetCtrlVal.assert_not_called()
    assert view.values == initial


def test_qt_preview_draws_both_hv_states_and_keeps_mode_hit_region_separate(monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from spitfire.gui import SpitfireWindow

    monkeypatch.setattr('socket.socket', lambda *a, **kw: pytest.fail('Layout preview must not open sockets'))
    app = QApplication.instance() or QApplication([])
    window = SpitfireWindow()
    emitted = []
    window.callback.connect(lambda *args: emitted.append(args))
    try:
        window.show_panel(5)
        app.processEvents()
        panel = window.panels[5]
        assert panel.hit(QPoint(204, 340)) == 34
        assert panel.hit(QPoint(364, 370)) == 48
        off = panel.grab().toImage().convertToFormat(QImage.Format_ARGB32)
        dark = sum(off.pixelColor(x, y).lightness() < 80
                   for x in range(170, 260) for y in range(299, 316))
        assert dark > 30, 'The HV ON/OFF heading must render despite the blank original sprite'
        window.set_value(5, 34, 1)
        app.processEvents()
        on = panel.grab().toImage().convertToFormat(QImage.Format_ARGB32)
        crop = QRect(190, 316, 54, 60)
        off_crop, on_crop = off.copy(crop), on.copy(crop)
        assert bytes(off_crop.bits()) != bytes(on_crop.bits())
        assert not emitted, 'Display/layout changes must not generate an HV callback'
    finally:
        window.close()
        app.processEvents()

"""Exercise CVI callback routing without loading NI or opening a socket."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest

from spitfire.native import NativeGui, RESOURCES


@pytest.fixture
def view():
    result = NativeGui.__new__(NativeGui)
    result.controller = SimpleNamespace(read_only=False, handle_callback=Mock(), mouse_released=Mock())
    result.values = {}
    result._types = {(6, 4): 9, (6, 64): 9}
    result._user = SimpleNamespace(GetAsyncKeyState=Mock(return_value=0))
    result._read_only_controls = {(6, 10), (6, 11), (6, 52), (2, 7)}
    result.read = Mock(return_value=30.0)
    return result


@pytest.mark.parametrize('name,panel,control', [
    ('ecu_set_temp', 2, 7), ('strnsendcllback', 6, 60),
    ('cllbck', 6, 10), ('tmr_Data_Logger', 6, 64),
])
@pytest.mark.parametrize('event', [0, 2, 8, 9, 12, 13, 14, 16])
def test_focus_redraw_and_value_change_notifications_do_not_read_or_dispatch(view, name, panel, control, event):
    view._control_event(name, panel, control, event)
    view.read.assert_not_called()
    view.controller.handle_callback.assert_not_called()


def test_timer_tick_and_motor_release_never_read_timer_values(view):
    view._control_event('tmr_Data_Logger', 6, 64, 15)
    view.controller.handle_callback.assert_called_once_with('tmr_Data_Logger', 0, 15, 6, 64)
    view._control_event('tmr_Mouse_Callback1', 6, 4, 15)
    view.controller.mouse_released.assert_called_once_with()
    view.read.assert_not_called()


def test_motor_hold_timer_remains_forwarded_when_mouse_down(view):
    view._user.GetAsyncKeyState.return_value = 0x8000
    view._control_event('tmr_Mouse_Callback1', 6, 4, 15)
    view.controller.handle_callback.assert_called_once_with('tmr_Mouse_Callback1', 0, 15, 6, 4)
    view.controller.mouse_released.assert_not_called()


@pytest.mark.parametrize('name,control,events', [
    ('cllbck', 10, [3, 1]), ('parse_command5', 11, [3]),
    ('BW_reset', 5, [3]), ('picture_Callback1', 52, [3, 5]),
    ('picture_Callback2', 51, [3, 4, 5, 6]),
])
def test_original_run_stop_and_motor_activation_events_are_preserved(view, name, control, events):
    for event in events:
        view._control_event(name, 6, control, event)
    assert [call.args for call in view.controller.handle_callback.call_args_list] == [
        (name, 0, event, 6, control) for event in events]
    view.read.assert_not_called()


def test_motor_speed_commit_reads_its_actual_numeric_value_once(view):
    view._control_event('com_motor_speed', 6, 3, 1)
    view.read.assert_called_once_with(6, 3)
    view.controller.handle_callback.assert_called_once_with('com_motor_speed', 30.0, 1, 6, 3)


def test_readonly_queued_hardware_events_do_not_read_or_reset_controls(view):
    view.controller.read_only = True
    view._control_event('ecu_set_temp', 2, 7, 1)
    view._control_event('cllbck', 6, 10, 3)
    view._control_event('parse_command5', 6, 11, 3)
    view.read.assert_not_called()
    view.controller.handle_callback.assert_not_called()
    view._control_event('display_faults', 6, 50, 1)
    view.controller.handle_callback.assert_called_once_with('display_faults', 0, 1, 6, 50)


def test_direct_read_of_no_value_timer_does_not_call_ni_getctrlval():
    view = NativeGui.__new__(NativeGui)
    view.values = {}
    view._types = {(6, 64): 9}
    view.dll = SimpleNamespace(GetCtrlVal=Mock(side_effect=AssertionError('timer has no value')))
    assert view.read(6, 64) == 0
    view.dll.GetCtrlVal.assert_not_called()


def test_initial_native_layout_preserves_original_dimming_for_ready_restoration():
    view = NativeGui.__new__(NativeGui)
    view.spec = json.loads((RESOURCES / 'gui_spec.json').read_text())
    view._read_only_controls = view._hardware_controls()
    view._initial_device_dimming = {}
    view.read_attribute = Mock(side_effect=lambda p, c, a: int((p, c) == (5, 35)) if a == 500 else 0)
    view.set_attribute = Mock()
    view.set_menu_attribute = Mock()
    view._initialize_connection_layout()
    view.set_attribute.assert_any_call(6, 49, 530, 0)
    view.set_attribute.assert_any_call(6, 54, 530, 0)
    view.set_menu_attribute.assert_called_once_with(6, 0, 500, 0)
    presentation = view.connection_presentation()
    assert presentation['controls'][6, 10] == 0
    assert presentation['controls'][5, 35] == 1
    assert (6, 50) not in view._read_only_controls  # Fault navigation.
    assert (6, 63) not in view._read_only_controls  # Local coarse precision.
    assert (6, 59) in view._read_only_controls  # Raw command editor.


def test_native_readonly_attribute_mask_does_not_disable_navigation(view):
    view.controller.read_only = True
    view.attributes = {'ATTR_DIMMED': {'id': 500, 'type': 1}}
    view.panels = {6: 600, 2: 200}
    view.varargs = SimpleNamespace(SetCtrlAttribute=Mock(return_value=0))
    view.set_attribute(2, 7, 500, 0)
    assert view.varargs.SetCtrlAttribute.call_args.args[-1].value == 1
    view.set_attribute(6, 50, 500, 0)
    assert view.varargs.SetCtrlAttribute.call_args.args[-1].value == 0

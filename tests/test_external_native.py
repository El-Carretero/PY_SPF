"""Native adapter boundaries tested without loading Windows/CVI or devices."""
import os
from types import SimpleNamespace
from unittest.mock import Mock

from spitfire.native import NativeGui


def test_native_constraints_cannot_be_undone_by_legacy_actions():
    view = object.__new__(NativeGui)
    view.external = True
    view.panels = {6: 60, 8: 80, 9: 90}
    view.attributes = {'ATTR_VISIBLE': {'id': 530, 'type': 1}}
    view.varargs = SimpleNamespace(SetCtrlAttribute=Mock(return_value=0),
                                   SetPanelAttribute=Mock(return_value=0))
    view.dll = SimpleNamespace(DisplayPanel=Mock(), HidePanel=Mock())
    view.set_attribute(6, 19, 530, 1)
    assert view.varargs.SetCtrlAttribute.call_args.args[-1].value == 0
    for panel in (8, 9):
        view.set_panel_attribute(panel, 530, 1)
        view.show_panel(panel, True)
    view.varargs.SetPanelAttribute.assert_not_called()
    view.dll.DisplayPanel.assert_not_called()


def test_native_run_hold_requires_foreground_main_panel_and_pointer_inside():
    view = object.__new__(NativeGui)
    view.panels = {6: 60}
    state = {'pid': os.getpid(), 'panel': 60, 'x': 25, 'y': 25, 'left': 1}

    def foreground_process(window, pid):
        pid._obj.value = state['pid']

    def mouse(panel, control, x, y, left, right):
        x._obj.value, y._obj.value = state['x'], state['y']
        left._obj.value, right._obj.value = state['left'], 0
        return 0

    view._user = SimpleNamespace(GetForegroundWindow=lambda: 1,
                                 GetWindowThreadProcessId=foreground_process)
    view.dll = SimpleNamespace(GetActivePanel=lambda: state['panel'],
                               GetRelativeMouseState=mouse)
    view.read_attribute = lambda panel, control, attribute: 50
    assert view._run_button_still_held()
    for key, value in [('pid', 0), ('panel', 70), ('x', 50), ('y', -1), ('left', 0)]:
        original = state[key]
        state[key] = value
        assert not view._run_button_still_held()
        state[key] = original

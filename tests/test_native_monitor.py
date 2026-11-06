"""Device-free checks for local monitor state, callbacks and lifecycle."""
import ctypes as C
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from spitfire.native import NativeGui
from spitfire.native_monitor import NativeCommunicationMonitor
from spitfire.monitor_presentation import event_key, format_snapshot, is_problem


def sample(events=()):
    return {'log_status': 'live', 'device_status': 'ready',
            'heartbeat_age_seconds': .2, 'last_reply_age_seconds': .3,
            'last_status_age_seconds': 1.1, 'main_sample_age_seconds': .4,
            'heartbeat': {'communication': {'queue_total': 12, 'pending_tag': 1085,
                                             'suppressed_reset_batches': 7}},
            'counters': {'controller': {'write_ack_timeouts': 3}}, 'events': list(events)}


def row(seq, kind='RX', payload='value'):
    return {'session_id': 'test', 'seq': seq, 'utc': '2026-11-06T12:00:00+00:00',
            'kind': kind, 'payload': payload}


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setattr('socket.socket', Mock(side_effect=AssertionError('Monitor must not open sockets')))
    controls = iter(range(1, 200))
    view = SimpleNamespace(
        dll=SimpleNamespace(NewPanel=Mock(return_value=900), NewCtrl=Mock(side_effect=lambda *a: next(controls)),
                            InstallCtrlCallback=Mock(return_value=0), InstallPanelCallback=Mock(return_value=0),
                            DisplayPanel=Mock(return_value=0), HidePanel=Mock(return_value=0),
                            DiscardPanel=Mock(return_value=0), ClipboardPutText=Mock(return_value=0)),
        varargs=SimpleNamespace(SetCtrlAttribute=Mock(return_value=0), SetPanelAttribute=Mock(return_value=0),
                                SetCtrlVal=Mock(return_value=0)),
        _callbacks=[], _bytes=lambda s: str(s).encode(), _argument=lambda v: C.c_int(v) if isinstance(v, int) else C.c_char_p(str(v).encode()),
        _check=NativeGui._check, panels={6: 600},
        controller=SimpleNamespace(handle_callback=Mock(side_effect=AssertionError('Local action must not dispatch'))))
    reader = SimpleNamespace(snapshot=Mock(return_value=sample([row(1)])), close=Mock())
    reader.start = Mock(return_value=reader)
    factory = Mock(return_value=reader)
    now = [0.]
    panel = NativeCommunicationMonitor(view, Path('exact-session'), reader_factory=factory, clock=lambda: now[0])
    yield panel, view, reader, factory, now
    panel.close()


def test_lazy_panel_and_reader_are_separate_from_hardware_panels(monitor):
    panel, view, reader, factory, _ = monitor
    factory.assert_not_called()
    assert panel.panel is None
    panel.show()
    assert panel.panel == 900 and panel.visible
    assert view.panels == {6: 600}
    factory.assert_called_once_with(Path('exact-session'))
    reader.start.assert_called_once_with()
    assert 'DEVICE (saved)' in panel._painted['device']
    assert 'value' in panel.rendered_text
    assert view.dll.NewPanel.call_args.args[0] == 0


def test_pause_filter_clear_copy_and_close_are_local(monitor):
    panel, view, reader, factory, now = monitor
    panel.show()
    panel.local_action('pause')
    before = reader.snapshot.call_count
    reader.snapshot.return_value = sample([row(1), row(2, 'timeout', '1085 skipped')])
    now[0] = 1
    panel.refresh()
    assert reader.snapshot.call_count == before
    assert 'DISPLAY PAUSED' in panel._painted['warning']
    panel.local_action('pause')
    panel.local_action('filter')
    assert '1085 skipped' in panel.rendered_text and 'value' not in panel.rendered_text
    panel.local_action('copy')
    assert view.dll.ClipboardPutText.call_args.args == (panel.rendered_text.encode(),)
    panel.local_action('clear')
    assert panel.rendered_text == ''
    reader.snapshot.return_value = sample([row(1), row(2, 'timeout'), row(3, 'retry', 'new retry')])
    now[0] = 2
    panel.refresh()
    assert 'new retry' in panel.rendered_text
    panel.local_action('close')
    assert not panel.visible
    view.controller.handle_callback.assert_not_called()
    reader.close.assert_not_called()
    panel.close()
    panel.close()
    reader.close.assert_called_once_with()
    view.dll.DiscardPanel.assert_called_once_with(900)


def test_refresh_is_throttled_hidden_and_unchanged_values_not_repainted(monitor):
    panel, view, reader, _, now = monitor
    panel.show()
    calls = view.varargs.SetCtrlVal.call_count
    panel.refresh()
    reader.snapshot.assert_called_once_with()
    now[0] = .3
    panel.refresh()
    assert reader.snapshot.call_count == 2
    assert view.varargs.SetCtrlVal.call_count == calls
    panel.hide()
    now[0] = 2
    panel.refresh()
    assert reader.snapshot.call_count == 2


def test_disabled_logging_explains_state_without_starting_a_reader(monitor):
    panel, view, reader, factory, now = monitor
    panel.path = None
    panel.show()
    factory.assert_not_called()
    assert 'Logging disabled' in panel._painted['warning']
    assert 'UNKNOWN' in panel._painted['device']
    assert any(call.args[1:3] == (panel.controls['folder'], 500)
               and call.args[3].value == 1 for call in view.varargs.SetCtrlAttribute.call_args_list)


def test_bad_native_creation_can_retry_and_does_not_leak_partial_panel(monitor):
    panel, view, *_ = monitor
    view.dll.NewCtrl.side_effect = RuntimeError('synthetic library error')
    with pytest.raises(RuntimeError):
        panel.show()
    assert panel.panel is None and not panel.visible
    view.dll.DiscardPanel.assert_called_once_with(900)


def test_native_gui_configuration_selects_exact_path_without_creating_ui():
    view = NativeGui.__new__(NativeGui)
    view._communication_monitor = SimpleNamespace(close=Mock())
    previous = view._communication_monitor
    view.configure_communication_monitor('exact/session')
    previous.close.assert_called_once_with()
    assert view._communication_monitor is None
    assert view._communication_log_path == Path('exact/session')
    view.configure_communication_monitor(None)
    assert view._communication_log_path is None


def test_monitor_item_reuses_original_view_menu_and_its_callback_is_local():
    view = NativeGui.__new__(NativeGui)
    view.panels = {6: 600}
    view._callbacks = []
    view._bytes = lambda value: str(value).encode()
    view.show_communication_monitor = Mock()
    def menu_attribute(bar, item, attribute, buffer):
        if item == 3:
            buffer.value = b'CONTROLx'
            return 0
        return -1
    view.dll = SimpleNamespace(GetPanelMenuBar=Mock(return_value=100),
                               GetMenuBarAttribute=Mock(side_effect=menu_attribute),
                               NewMenu=Mock(return_value=19), NewPanel=Mock(), NewCtrl=Mock(),
                               ClipboardPutText=Mock(), NewMenuItem=Mock(return_value=25))
    view._install_communication_menu()
    view.dll.NewMenu.assert_not_called()
    assert view.dll.NewMenuItem.call_args.args[1:3] == (3, b'Communication Monitor')
    view._callbacks[-1](100, 25, None, 600)
    view.show_communication_monitor.assert_called_once_with()


def test_formatter_bounds_rows_characters_and_clear_identities():
    rows = [row(i, 'timeout', 'x' * 1000) for i in range(500)]
    result = format_snapshot(sample(rows), cleared={event_key(rows[-1])}, max_events=20, max_chars=2000)
    assert result['event_count'] <= 20 and len(result['events']) <= 2000
    assert result['log_ok'] and result['device_ok']
    assert 'ACK timeouts 3' in result['traffic']
    assert '12' in result['queue']
    assert not is_problem(row(1, 'RX', '<1039>garbage'))
    assert is_problem({**row(2, 'QUEUE'), 'fields': {'event': 'reset_suppressed'}})
    assert is_problem({**row(2, 'QUEUE'), 'fields': {'event': 'coalesced'}})


def test_bad_saved_nested_fields_do_not_break_filter_or_status_presentation():
    snapshot = {'heartbeat': {'communication': []}, 'counters': {'controller': 'bad', 'logger': {'errors': []}},
                'errors': [], 'events': [None, {**row(1, 'QUEUE'), 'fields': 'bad'}]}
    assert format_snapshot(snapshot, problems_only=True)['events'] == ''
    assert not is_problem({**row(1, 'QUEUE'), 'fields': 'bad'})


def test_structured_queue_rows_are_readable_without_horizontal_scrolling():
    event = {**row(1, 'QUEUE', "{'long': 'raw dict representation'}"),
             'fields': {'event': 'coalesced', 'batch_id': 'fault_reset:9',
                        'suppressed': 8, 'queue_inside': 12, 'queue_outside': 0,
                        'origin': 'callback:cllbckcmd_reset'}}
    formatted = format_snapshot(sample([event, row(2, 'RX', 'x' * 800)]))['events']
    assert 'duplicate suppressed' in formatted
    assert 'batch fault_reset:9' in formatted
    assert 'raw dict representation' not in formatted
    assert '11-06 12:00:00.000Z' in formatted
    assert all(len(line) <= 105 for line in formatted.splitlines())


def test_native_monitor_uses_larger_font_word_wrap_and_vertical_scroll(monitor):
    panel, view, *_ = monitor
    panel.show()
    settings = {call.args[2]: call.args[3].value for call in view.varargs.SetCtrlAttribute.call_args_list
                if call.args[1] == panel.controls['events']}
    assert settings[686] == 12
    assert settings[551] == 2
    assert settings[791] == 4

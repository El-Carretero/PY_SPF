"""UI-thread timer invariants without NI, Windows, or device access."""
from collections import deque
import ctypes as C
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from spitfire.native_ticker import GUIThreadInfo, NativeEventTicker
from spitfire.scheduling import Request


@pytest.fixture
def ticker():
    flags = [0]
    keys = {1: 0x8000}
    user = SimpleNamespace(SetTimer=Mock(return_value=123), KillTimer=Mock(return_value=1),
                           GetAsyncKeyState=Mock(side_effect=lambda key: keys.get(key, 0)),
                           GetForegroundWindow=Mock(return_value=100))
    def info(thread, ptr):
        C.cast(ptr, C.POINTER(GUIThreadInfo)).contents.flags = flags[0]
        return 1
    def owner(hwnd, ptr):
        C.cast(ptr, C.POINTER(C.c_uint)).contents.value = 77
        return 777
    user.GetGUIThreadInfo = Mock(side_effect=info)
    user.GetWindowThreadProcessId = Mock(side_effect=owner)
    kernel = SimpleNamespace(GetCurrentThreadId=Mock(return_value=777), GetCurrentProcessId=Mock(return_value=77))
    controller = SimpleNamespace(state={'evnt_cmt': 0}, _button_started=None,
                                  scheduler=SimpleNamespace(inside=deque(), outside=deque()),
                                  tick=Mock(), log=Mock(), running=True)
    def cancel(reason):
        controller.state['evnt_cmt'] = 0
        controller._button_started = None
        for queue in (controller.scheduler.inside, controller.scheduler.outside):
            retained = [r for r in queue if r.tag != 2027]
            queue.clear()
            queue.extend(retained)
    controller.cancel_pending_run = Mock(side_effect=cancel)
    diagnostics = SimpleNamespace(tick=Mock())
    result = NativeEventTicker(controller, diagnostics, user=user, kernel=kernel, main_window=100)
    yield result, controller, diagnostics, user, kernel, flags, keys
    result.close()


def test_ui_timer_and_outer_loop_share_controller_and_diagnostics(ticker):
    timer, controller, diagnostics, *_ = ticker
    timer.tick()
    timer.callback(None, 0, 123, 0)
    assert controller.tick.call_count == diagnostics.tick.call_count == 2
    assert timer.stats['outer_ticks'] == timer.stats['timer_ticks'] == 1


def test_nested_dispatch_does_not_reenter_scheduler(ticker):
    timer, controller, diagnostics, *_ = ticker
    controller.tick.side_effect = lambda: timer.callback(None, 0, 123, 0)
    timer.tick()
    controller.tick.assert_called_once_with()
    diagnostics.tick.assert_called_once_with()
    assert timer.stats['reentrant_skips'] == 1


def test_callback_on_another_thread_cannot_call_controller_or_gui(ticker):
    timer, controller, diagnostics, user, kernel, *_ = ticker
    kernel.GetCurrentThreadId.return_value = 999
    timer.callback(None, 0, 123, 0)
    controller.tick.assert_not_called()
    diagnostics.tick.assert_not_called()
    user.GetGUIThreadInfo.assert_not_called()
    assert timer.stats['wrong_thread_skips'] == 1


def test_python_worker_thread_is_rejected_even_if_mock_win32_id_matches(ticker):
    timer, controller, diagnostics, user, *_ = ticker
    worker = threading.Thread(target=lambda: timer.callback(None, 0, 123, 0))
    worker.start()
    worker.join(timeout=1)
    assert not worker.is_alive()
    controller.tick.assert_not_called()
    user.GetGUIThreadInfo.assert_not_called()
    assert timer.stats['wrong_thread_skips'] == 1


@pytest.mark.parametrize('flag', [2, 4, 8, 16])
def test_standard_menu_or_move_cancels_only_held_run_before_tick(ticker, flag):
    timer, controller, diagnostics, user, kernel, flags, keys = ticker
    flags[0] = flag
    controller.state['evnt_cmt'] = 1
    controller._button_started = 1
    controller.scheduler.inside.extend((Request(2027), Request(2005), Request(2028)))
    def check_before_tick():
        assert controller.state['evnt_cmt'] == 0
        assert controller._button_started is None
    controller.tick.side_effect = check_before_tick
    timer.tick()
    assert timer.error is None
    diagnostics.tick.assert_called_once_with()
    controller.cancel_pending_run.assert_called_once()
    assert [request.tag for request in controller.scheduler.inside] == [2005, 2028]
    assert timer.stats['menu_ticks'] == 1


def test_released_mouse_cancels_an_unsent_run_after_hold_fields_were_cleared(ticker):
    timer, controller, diagnostics, user, kernel, flags, keys = ticker
    keys[1] = 0
    controller.scheduler.outside.extend((Request(2027), Request(2005)))
    timer.tick()
    assert [request.tag for request in controller.scheduler.outside] == [2005]
    controller.cancel_pending_run.assert_called_once()


@pytest.mark.parametrize('key', [0x12, 0x79])
def test_alt_or_f10_cancels_run_even_when_cvi_menu_flags_are_zero(ticker, key):
    timer, controller, diagnostics, user, kernel, flags, keys = ticker
    controller.state['evnt_cmt'] = 1
    keys[key] = 0x8000
    timer.tick()
    controller.cancel_pending_run.assert_called_once()
    assert timer.stats['menu_ticks'] == 0


def test_owned_popup_interrupts_pending_run(ticker):
    timer, controller, diagnostics, user, *_ = ticker
    controller.state['evnt_cmt'] = 1
    user.GetForegroundWindow.return_value = 200
    timer.tick()
    controller.cancel_pending_run.assert_called_once()


def test_healthy_physical_run_hold_and_separate_emp_on_are_preserved(ticker):
    timer, controller, diagnostics, user, *_ = ticker
    controller.state['evnt_cmt'] = 1
    controller._button_started = 1
    controller.scheduler.inside.append(Request(2005))
    timer.tick()
    controller.cancel_pending_run.assert_not_called()
    assert controller.state['evnt_cmt'] == 1
    assert controller.scheduler.inside[0].tag == 2005


def test_timer_exception_is_reported_to_outer_run_as_failure(ticker):
    timer, controller, diagnostics, *_ = ticker
    controller.tick.side_effect = ValueError('synthetic failure')
    timer.callback(None, 0, 123, 0)
    assert not controller.running
    assert timer.stats['tick_errors'] == 1
    with pytest.raises(RuntimeError, match='scheduler failed') as error:
        timer.raise_if_failed()
    assert isinstance(error.value.__cause__, ValueError)


def test_killtimer_is_idempotent_and_already_queued_callbacks_are_safe(ticker):
    timer, controller, diagnostics, user, *_ = ticker
    callback = timer.callback
    timer.close()
    timer.close()
    callback(None, 0, 123, 0)
    controller.tick.assert_not_called()
    user.KillTimer.assert_called_once_with(None, 123)

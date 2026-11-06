"""Keep the controller on the UI thread during native modal message loops."""
from __future__ import annotations
import ctypes as C
import threading


class GUIThreadInfo(C.Structure):
    _fields_ = [('cbSize', C.c_uint), ('flags', C.c_uint)] + [
        (name, C.c_void_p) for name in ('hwndActive', 'hwndFocus', 'hwndCapture',
                                       'hwndMenuOwner', 'hwndMoveSize', 'hwndCaret')
    ] + [('rcCaret', C.c_int * 4)]


class NativeEventTicker:
    """Dispatch on the creating UI thread; never start a background GUI worker.

    Keep this object alive through the last ProcessSystemEvents during teardown:
    KillTimer does not remove already queued WM_TIMER messages. Those callbacks
    safely return after close while their ctypes callback remains alive.
    """
    def __init__(self, controller, diagnostics, *, user=None, kernel=None, main_window=None):
        self.controller, self.diagnostics = controller, diagnostics
        self.user = user or C.WinDLL('user32', use_last_error=True)
        self.kernel = kernel or C.WinDLL('kernel32', use_last_error=True)
        self.owner_thread = self.kernel.GetCurrentThreadId()
        self.owner_process = self.kernel.GetCurrentProcessId()
        self.python_thread = threading.get_ident()
        self.closed = self.busy = False
        self.error = None
        self.stats = {'timer_ticks': 0, 'outer_ticks': 0, 'reentrant_skips': 0,
                      'wrong_thread_skips': 0, 'menu_ticks': 0, 'cancelled_run': 0,
                      'owner_thread': self.owner_thread, 'last_gui_flags': 0,
                      'outer_event_cycles': 0, 'tick_errors': 0}
        callback_type = getattr(C, 'WINFUNCTYPE', C.CFUNCTYPE)
        self.callback_type = callback_type(None, C.c_void_p, C.c_uint, C.c_size_t, C.c_uint)
        self.callback = self.callback_type(lambda *args: self.tick(from_timer=True))
        self.user.SetTimer.argtypes = [C.c_void_p, C.c_size_t, C.c_uint, self.callback_type]
        self.user.SetTimer.restype = C.c_size_t
        self.user.KillTimer.argtypes = [C.c_void_p, C.c_size_t]
        self.user.GetGUIThreadInfo.argtypes = [C.c_uint, C.POINTER(GUIThreadInfo)]
        self.user.GetForegroundWindow.restype = C.c_void_p
        self.user.GetWindowThreadProcessId.argtypes = [C.c_void_p, C.POINTER(C.c_uint)]
        self.main_window = main_window if main_window is not None else self._find_main_window()
        self.timer = self.user.SetTimer(None, 0, 25, self.callback)
        if not self.timer:
            raise OSError(C.get_last_error(), 'Cannot start native UI-thread scheduler timer')

    def _find_main_window(self):
        windows = []
        self.user.GetWindowTextW.argtypes = [C.c_void_p, C.c_wchar_p, C.c_int]
        callback_type = getattr(C, 'WINFUNCTYPE', C.CFUNCTYPE)(C.c_int, C.c_void_p, C.c_void_p)
        def visit(handle, _):
            owner = C.c_uint()
            self.user.GetWindowThreadProcessId(handle, C.byref(owner))
            title = C.create_unicode_buffer(512)
            self.user.GetWindowTextW(handle, title, len(title))
            if owner.value == self.owner_process and title.value.startswith('Spitfire'):
                windows.append(handle)
            return True
        callback = callback_type(visit)
        self.user.EnumWindows(callback, None)
        return windows[0] if windows else None

    def _owned_popup_active(self):
        foreground = self.user.GetForegroundWindow()
        if not self.main_window or not foreground or foreground == self.main_window:
            return False
        owner = C.c_uint()
        self.user.GetWindowThreadProcessId(foreground, C.byref(owner))
        return owner.value == self.owner_process

    def tick(self, *, from_timer=False):
        if self.closed or not self.controller.running:
            return
        if self.kernel.GetCurrentThreadId() != self.owner_thread or threading.get_ident() != self.python_thread:
            self.stats['wrong_thread_skips'] += 1
            return
        if self.busy:
            self.stats['reentrant_skips'] += 1
            return
        self.busy = True
        try:
            info = GUIThreadInfo(cbSize=C.sizeof(GUIThreadInfo))
            flags = info.flags if self.user.GetGUIThreadInfo(self.owner_thread, C.byref(info)) else 0
            self.stats['last_gui_flags'] = flags
            if flags & 0x1e:
                self.stats['menu_ticks'] += 1
            pending = (self.controller.state.get('evnt_cmt') or self.controller._button_started is not None
                       or any(request.tag == 2027
                              for queue in (self.controller.scheduler.inside, self.controller.scheduler.outside)
                              for request in queue))
            # CVI's custom menus do not always set the Win32 menu flags. A
            # released RUN mouse, Alt/F10 or another owned foreground panel also
            # cancels an unfinished hold or an unsent held-RUN command.
            interrupted = bool(flags & 0x1e)
            if pending:
                interrupted = interrupted or not self.user.GetAsyncKeyState(1) & 0x8000
                interrupted = interrupted or any(self.user.GetAsyncKeyState(key) & 0x8000 for key in (0x12, 0x79))
                interrupted = interrupted or self._owned_popup_active()
            if interrupted:
                self.controller.cancel_pending_run('Native menu/move mode or RUN input interrupted')
                self.stats['cancelled_run'] += int(bool(pending))
            self.controller.tick()
            self.diagnostics.tick()
            # This optional file-backed display is observational. A view/render
            # failure must never stop the controller or change its request queue.
            refresh = getattr(getattr(self.controller, 'view', None), 'refresh_communication_monitor', None)
            if refresh is not None:
                try:
                    refresh()
                except Exception as error:
                    self.stats['monitor_errors'] = self.stats.get('monitor_errors', 0) + 1
                    self.stats['last_monitor_error'] = repr(error)[:500]
            self.stats['timer_ticks' if from_timer else 'outer_ticks'] += 1
        except BaseException as exc:
            self.stats['tick_errors'] += 1
            self.stats['last_error'] = repr(exc)
            self.error = exc
            self.controller.running = False
            try:
                self.controller.log('GUI timer error', repr(exc))
            except BaseException:
                pass
        finally:
            self.busy = False

    def raise_if_failed(self):
        if self.error is not None:
            raise RuntimeError('Native UI-thread scheduler failed') from self.error

    def close(self):
        if not self.closed:
            self.closed = True
            self.user.KillTimer(None, self.timer)

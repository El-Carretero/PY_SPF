"""Original CVI drawing engine driven by Python application logic (Windows x86).

The supplied UIR records retain the original drawing data. Their callback names
are removed and explicitly rebound to Python, avoiding calls into SPITFIRE.EXE.
"""
from __future__ import annotations
import contextlib
import ctypes as C
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time
import uuid

from .external_ui import HIDDEN_PANELS, TITLE, apply_presentation, constrain_attribute

RESOURCES = Path(__file__).with_name('resources')


@contextlib.contextmanager
def _private_runtime_registry(runtime):
    """Select bundled NI resources with a temporary, process-local HKLM view.

    CVI 7.1 reads cvidir from this legacy key when its system runtime directory
    is absent. RegOverridePredefKey affects this process only; system settings
    and any installed NI runtime are left intact.
    """
    import winreg
    path = 'Software\\SpitfirePython\\Runtime_' + uuid.uuid4().hex
    root = winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
    branch = r'Software\National Instruments\CVI Run-Time Engine\4.0.1'
    with winreg.CreateKey(root, branch) as key:
        winreg.SetValueEx(key, 'cvidir', 0, winreg.REG_SZ, str(runtime))
    api = C.WinDLL('advapi32', use_last_error=True).RegOverridePredefKey
    api.argtypes = [C.c_void_p, C.c_void_p]
    api.restype = C.c_long
    result = api(C.c_void_p(0x80000002), C.c_void_p(int(root)))
    if result:
        root.Close()
        raise OSError(result, 'Cannot select bundled CVI runtime resources')
    try:
        yield
    finally:
        api(C.c_void_p(0x80000002), None)
        root.Close()
        def remove(parent, child):
            with winreg.OpenKey(parent, child, 0, winreg.KEY_ALL_ACCESS) as key:
                while True:
                    try:
                        sub = winreg.EnumKey(key, 0)
                    except OSError:
                        break
                    remove(key, sub)
            winreg.DeleteKey(parent, child)
        remove(winreg.HKEY_CURRENT_USER, path)


def _prepare_runtime():
    source = RESOURCES / 'runtime'
    def arrange(runtime):
        for folder, names in {
            'bin': ('cvirte.rsc', 'msgrte.txt', 'cvierror.txt'),
            'fonts': ('ni7seg.ttf', 'nisystem.ttf'),
        }.items():
            target = runtime / folder
            target.mkdir(exist_ok=True)
            for name in names:
                origin, destination = runtime / name, target / name
                if origin.exists() and not destination.exists():
                    shutil.copyfile(origin, destination)
        return runtime
    try:
        return arrange(source)
    except PermissionError:
        import tempfile
        cache = Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()))
        runtime = cache / 'SpitfirePython' / 'runtime-7.1'
        runtime.mkdir(parents=True, exist_ok=True)
        for origin in source.iterdir():
            if origin.is_file():
                destination = runtime / origin.name
                if not destination.exists() or destination.stat().st_size != origin.stat().st_size:
                    shutil.copyfile(origin, destination)
        return arrange(runtime)


class NativeGui:
    native_timers = True

    def __init__(self, *, external=True):
        self.external = external
        if sys.platform != 'win32' or struct.calcsize('P') != 4:
            raise RuntimeError('The original NI GUI requires 32-bit Windows Python.')
        self.controller = None
        self._callbacks = []
        self._closed = False
        self.values = {}
        self.events = []
        self.panels = {}
        self.menu_ids = {}
        self.spec = json.loads((RESOURCES / 'gui_spec.json').read_text(encoding='utf-8'))
        self.attributes = json.loads((RESOURCES / 'cvi_attributes.json').read_text())
        self.bindings = json.loads((RESOURCES / 'callback_bindings.json').read_text())
        self._types = {(p['id'], c['id']): c.get('data_type', 1)
                       for p in self.spec['panels'] for c in p['controls']}
        runtime = _prepare_runtime()
        self._search_handle = os.add_dll_directory(str(runtime))
        self._kernel = C.WinDLL('kernel32')
        self._user = C.WinDLL('user32')
        self._kernel.GetModuleHandleW.argtypes = [C.c_wchar_p]
        self._kernel.GetModuleHandleW.restype = C.c_void_p
        self._module = self._kernel.GetModuleHandleW(None)
        with _private_runtime_registry(runtime):
            self.dll = C.WinDLL(str(runtime / 'cvirte.dll'))
            self.varargs = C.CDLL(str(runtime / 'cvirte.dll'))
            init = self.dll.InitCVIRTDll
            init.argtypes = [C.c_void_p] * 11
            init.restype = C.c_int
            if not init(self._module, None, 0, None, 0, None, 0, None, 0, None, None):
                raise RuntimeError('NI CVI runtime initialization failed.')
        self.dll.DisableBreakOnLibraryErrors()
        for panel in (7, 5, 6, 9, 2, 3, 4, 8, 1):
            if self.external and panel in HIDDEN_PANELS:
                continue
            handle = self.dll.LoadPanel(0, self._bytes(RESOURCES / 'SPITFIRE.UIR'), panel)
            self._check(handle, 'load original panel ' + str(panel))
            self.panels[panel] = handle
        server = self.dll.LoadPanel(0, self._bytes(RESOURCES / 'SERVER.UIR'), 1)
        self._check(server, 'load original server panel')
        self.panels['server'] = server
        for key in self.panels:
            self._bind_panel(key)
        if self.external:
            self.set_panel_attribute(6, 573, TITLE)
            self._status_control = self.dll.NewCtrl(self.panels[6], 160, self._bytes(''), 125, 85)
            self._check(self._status_control, 'create external status text')
            self._types[6, self._status_control] = 5
            self.set_attribute(6, self._status_control, 533, 390)
            self.set_attribute(6, self._status_control, 540, 58)
            apply_presentation(self)
        self.show_panel(6)

    @staticmethod
    def _bytes(value):
        return str(value).encode('mbcs', errors='replace')

    @staticmethod
    def _check(code, operation):
        if code < 0:
            raise RuntimeError(f'CVI error {code}: {operation}')
        return code

    def _dtype(self, panel, control):
        key = panel, control
        if key not in self._types:
            result = C.c_int()
            rc = self.dll.GetCtrlAttribute(self.panels[panel], control, 710, C.byref(result))
            self._types[key] = result.value if rc >= 0 else 1
        return self._types[key]

    def read(self, panel, control):
        dtype = self._dtype(panel, control)
        val = C.create_string_buffer(8192)
        rc = self.dll.GetCtrlVal(self.panels[panel], control, val)
        if rc < 0:
            return self.values.get((panel, control), 0)
        if dtype == 5:
            return val.value.decode('mbcs', errors='replace')
        if dtype == 4:
            return struct.unpack('<d', val.raw[:8])[0]
        if dtype == 3:
            return struct.unpack('<f', val.raw[:4])[0]
        return struct.unpack('<i', val.raw[:4])[0]

    def read_attribute(self, panel, control, attribute):
        if panel not in self.panels:
            return 0
        spec = next((a for a in self.attributes.values() if a['id'] == attribute), {})
        dtype = spec.get('type', 1)
        if dtype == 9:
            dtype = self._dtype(panel, control)
        buffer = C.create_string_buffer(8192)
        code = self.dll.GetCtrlAttribute(self.panels[panel], int(control), int(attribute), buffer)
        self._check(code, f'read control attribute {attribute}')
        if dtype == 5:
            return buffer.value.decode('mbcs', errors='replace')
        if dtype == 4:
            return struct.unpack('<d', buffer.raw[:8])[0]
        if dtype == 3:
            return struct.unpack('<f', buffer.raw[:4])[0]
        return struct.unpack('<i', buffer.raw[:4])[0]

    def _argument(self, value, dtype=1):
        if dtype == 5 or isinstance(value, str):
            return C.c_char_p(self._bytes(value))
        if dtype in (3, 4) or isinstance(value, float):
            return C.c_double(float(value))
        return C.c_int(int(value))

    def set_value(self, panel, control, value):
        self.values[panel, control] = value
        if panel not in self.panels:
            return
        rc = self.varargs.SetCtrlVal(self.panels[panel], int(control),
                                    self._argument(value, self._dtype(panel, control)))
        self._check(rc, f'set panel {panel} control {control}')

    def set_attribute(self, panel, control, attribute, value):
        if panel not in self.panels:
            return
        if self.external:
            value = constrain_attribute(panel, control, attribute, value)
        spec = next((a for a in self.attributes.values() if a['id'] == attribute), {})
        dtype = spec.get('type', 1)
        if dtype == 9:
            dtype = self._dtype(panel, control)
        self._check(self.varargs.SetCtrlAttribute(self.panels[panel], int(control), int(attribute),
                                                 self._argument(value, dtype)),
                    f'set control attribute {attribute}')

    def set_panel_attribute(self, panel, attribute, value):
        if panel not in self.panels or (self.external and panel in HIDDEN_PANELS):
            return
        self._check(self.varargs.SetPanelAttribute(self.panels[panel], int(attribute),
                                                  self._argument(value)),
                    f'set panel attribute {attribute}')

    def set_menu_attribute(self, panel, item, attribute, value):
        menubar = self.dll.GetPanelMenuBar(self.panels[panel])
        return self.varargs.SetMenuBarAttribute(menubar, int(item), int(attribute),
                                                self._argument(value))

    def show_panel(self, panel, visible=True):
        if panel not in self.panels or (self.external and panel in HIDDEN_PANELS):
            return
        if self.external and ((panel != 6 and visible) or (panel == 6 and not visible)):
            self.cancel_run_hold()
        return (self.dll.DisplayPanel if visible else self.dll.HidePanel)(self.panels[panel])

    def show_server(self, visible=True):
        return self.show_panel('server', visible)

    def log(self, text):
        self.events.append(str(text))
        if len(self.events) > 2000:
            del self.events[:-1000]

    def show_warning(self, title, text, on_confirm=None):
        self.dll.MessagePopup(self._bytes(title), self._bytes(text))
        if on_confirm:
            on_confirm()

    def request_close(self):
        if self.controller:
            self.controller.running = False

    def attach(self, controller):
        self.controller = controller

    def _bind_panel(self, panel):
        entries = self.bindings['SERVER' if panel == 'server' else 'SPITFIRE']
        resource_panel = 1 if panel == 'server' else panel
        callback_type = C.CFUNCTYPE(C.c_int, C.c_int, C.c_int, C.c_int,
                                     C.c_void_p, C.c_int, C.c_int)
        for entry in entries:
            if entry['kind'] != 'control' or entry['panel'] != resource_panel:
                continue
            def callback(handle, control, event, data, event1, event2, *, name=entry['name'], p=panel):
                if self.controller is None:
                    return 0
                try:
                    if name == 'tmr_Mouse_Callback1':
                        if not (self._user.GetAsyncKeyState(1) & 0x8000 or
                                self._user.GetAsyncKeyState(2) & 0x8000):
                            self.controller.mouse_released()
                            return 0
                    self.controller.handle_callback(name, self.read(p, control), event, p, control)
                except Exception as exc:
                    self.log(f'{name}: {exc}')
                return 0
            cb = callback_type(callback)
            self._callbacks.append(cb)
            self._check(self.dll.InstallCtrlCallback(self.panels[panel], entry['control'], cb, None),
                        'install callback ' + entry['name'])
        panel_type = C.CFUNCTYPE(C.c_int, C.c_int, C.c_int, C.c_void_p, C.c_int, C.c_int)
        def on_panel(handle, event, data, event1, event2):
            if self.controller is None:
                return 0
            if event == 7 and panel == 6:
                key = event1 & 0xff
                if key:
                    self.controller.key_pressed(chr(key))
            elif event == 11:
                if panel == 6:
                    self.controller.stop()
                else:
                    self.show_panel(panel, False)
            return 0
        cb = panel_type(on_panel)
        self._callbacks.append(cb)
        self.dll.InstallPanelCallback(self.panels[panel], cb, None)
        if panel == 6:
            self._bind_menus()

    def _bind_menus(self):
        menubar = self.dll.GetPanelMenuBar(self.panels[6])
        if menubar <= 0:
            return
        names = {x['constant']: x['name'] for x in self.bindings['SPITFIRE'] if x['kind'] == 'menu'}
        menu_type = C.CFUNCTYPE(None, C.c_int, C.c_int, C.c_void_p, C.c_int)
        for item in range(1, 65):
            name = C.create_string_buffer(512)
            if self.dll.GetMenuBarAttribute(menubar, item, 501, name) < 0:
                continue
            constant = name.value.decode('mbcs', errors='replace')
            if constant not in names:
                continue
            callback_name = names[constant]
            if self.external and callback_name == 'show_setup':
                callback_name = 'apply_external_optout'
                self.varargs.SetMenuBarAttribute(menubar, item, 1060, self._bytes('Apply external pump opt-out'))
            self.menu_ids[constant] = item
            def menu_callback(bar, menu_item, data, panel, *, name=callback_name):
                if self.controller:
                    self.controller.handle_callback(name, 0, 1, 6, menu_item)
            cb = menu_type(menu_callback)
            self._callbacks.append(cb)
            self.dll.InstallMenuCallback(menubar, item, cb, None)

    def set_external_status(self, text):
        if self.external and hasattr(self, '_status_control'):
            self.set_value(6, self._status_control, str(text))

    def cancel_run_hold(self):
        if self.controller:
            self.controller.handle_callback('cancel_run_hold', 0, 1, 6, 10)

    def _run_button_still_held(self):
        process_id = C.c_ulong()
        self._user.GetWindowThreadProcessId(self._user.GetForegroundWindow(), C.byref(process_id))
        if process_id.value != os.getpid():
            return False
        if self.dll.GetActivePanel() != self.panels[6]:
            return False
        x, y, left, right = (C.c_int() for _ in range(4))
        result = self.dll.GetRelativeMouseState(self.panels[6], 10, C.byref(x), C.byref(y), C.byref(left), C.byref(right))
        if result < 0 or not left.value:
            return False
        width = self.read_attribute(6, 10, 533)
        height = self.read_attribute(6, 10, 540)
        return 0 <= x.value < width and 0 <= y.value < height

    def process_events(self):
        self.dll.ProcessSystemEvents()
        if self.external and self.controller and self.controller.state.get('evnt_cmt'):
            if not self._run_button_still_held():
                self.cancel_run_hold()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.controller = None
        self.dll.SuspendTimerCallbacks()
        for handle in reversed(list(self.panels.values())):
            self.dll.DiscardPanel(handle)
        self.panels.clear()
        self.dll.ProcessSystemEvents()
        self.dll.CloseCVIRTDll.argtypes = [C.c_void_p]
        self.dll.CloseCVIRTDll(self._module)
        # CDLL and WinDLL each own one LoadLibrary reference. Unload while
        # Python and ctypes are still alive, matching the original bootstrap.
        import _ctypes
        _ctypes.FreeLibrary(self.varargs._handle)
        _ctypes.FreeLibrary(self.dll._handle)
        self._callbacks.clear()
        self._search_handle.close()


def run(opts):
    """Own the native GUI process, including the original Win32 exit boundary.

    CloseCVIRTDll is followed by ExitProcess in the original bootstrap. Retain
    that order for this standalone backend: the legacy runtime installs native
    process hooks that must not outlive Python's ctypes callback machinery.
    NativeGui.close() remains usable without terminating an embedding process.
    """
    if sys.platform != 'win32' or struct.calcsize('P') != 4:
        raise SystemExit('The original NI GUI requires 32-bit Windows Python.')
    from .__main__ import make_controller
    import traceback
    view = controller = None
    code = 0
    try:
        view = NativeGui()
        controller = make_controller(view, opts)
        view.attach(controller)
        controller.start()
        while controller.running:
            view.process_events()
            controller.tick()
            time.sleep(0.005)
    except KeyboardInterrupt:
        code = 130
    except BaseException:
        traceback.print_exc()
        code = 1
    finally:
        try:
            if controller is not None:
                controller.stop()
            if view is not None:
                view.close()
        except BaseException:
            traceback.print_exc()
            code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    C.WinDLL('kernel32').ExitProcess(code)
    return code

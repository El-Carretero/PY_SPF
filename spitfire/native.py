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

RESOURCES = Path(__file__).with_name('resources')

# Focus, redraw and value-change notifications are not user commits. In
# particular, a CVI timer has no GetCtrlVal value at all.
_CONTROL_EVENTS = {
    'cllbck': frozenset((1, 3)),
    'parse_command5': frozenset((3,)),
    'BW_reset': frozenset((3,)),
    'picture_Callback1': frozenset((3, 5)),
    'picture_Callback2': frozenset((3, 4, 5, 6)),
    'tmr_Mouse_Callback1': frozenset((15,)),
    'tmr_Data_Logger': frozenset((15,)),
}
_LOCAL_CONTROLS = frozenset((
    'Ch1_Coarse_Check_Callback', 'Ch2_Coarse_Check_Callback',
    'SYNC_Coarse_Check_Callback', 'Ch3_Coarse_Check_Callback',
    'Ch4_Coarse_Check_Callback',
))


def _callback_needs_value(name):
    from .callbacks import NUMERIC_CALLBACKS, INTEGER_CALLBACKS
    if name in NUMERIC_CALLBACKS:
        return NUMERIC_CALLBACKS[name][3] is None
    if name in INTEGER_CALLBACKS:
        return INTEGER_CALLBACKS[name][2] is None
    return (name in _LOCAL_CONTROLS or name in {
        'osc_mode', 'trig_mode', 'humoverride', 'bwdpolarity', 'bwdduality',
        'HV_switch', 'teconoff', 'setopmode', 'Monitor_switch', 'tdg_fault_override',
    } or name.startswith(('swChannelEnableCallback_btn', 'SetCoarseCallback_btn',
                          'setbwd', 'setena', 'secretcall')))


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
    if getattr(sys, 'frozen', False):
        # A frozen application ships this complete tree. Never repair it from
        # or stage it into the source-mode shared cache.
        required = ('cvirte.dll', 'cvintwrk.dll', 'bin/cvirte.rsc',
                    'bin/msgrte.txt', 'bin/cvierror.txt',
                    'fonts/ni7seg.ttf', 'fonts/nisystem.ttf')
        if any(not (source / name).is_file() for name in required):
            raise RuntimeError('Incomplete private CVI runtime; reinstall PY_SPF.')
        return source
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

    def __init__(self):
        if sys.platform != 'win32' or struct.calcsize('P') != 4:
            raise RuntimeError('The original NI GUI requires 32-bit Windows Python.')
        self.controller = None
        self._callbacks = []
        self._closed = False
        self._private_fonts = None
        self.values = {}
        self.events = []
        self._read_diagnostics = {'get_ctrl_val_calls': 0, 'timer_values_skipped': 0,
                                  'get_ctrl_val_errors': 0, 'last_control': None}
        self.panels = {}
        self.menu_ids = {}
        self.spec = json.loads((RESOURCES / 'gui_spec.json').read_text(encoding='utf-8'))
        self.attributes = json.loads((RESOURCES / 'cvi_attributes.json').read_text())
        self.bindings = json.loads((RESOURCES / 'callback_bindings.json').read_text())
        self._types = {(p['id'], c['id']): c.get('data_type', 1)
                       for p in self.spec['panels'] for c in p['controls']}
        self._read_only_controls = self._hardware_controls()
        self._initial_device_dimming = {}
        runtime = _prepare_runtime()
        self._search_handle = os.add_dll_directory(str(runtime))
        self._kernel = C.WinDLL('kernel32')
        self._user = C.WinDLL('user32')
        self._kernel.GetModuleHandleW.argtypes = [C.c_wchar_p]
        self._kernel.GetModuleHandleW.restype = C.c_void_p
        self._module = self._kernel.GetModuleHandleW(None)
        # MPR reads Windows network-provider settings during DLL initialization.
        # Loading it under the temporary HKLM view fails on Windows 11 before
        # CVI's own entrypoint runs (WinError 1114). Initialize it against the
        # real registry first, using only the Windows system DLL directory.
        self._mpr = C.WinDLL('mpr.dll', winmode=0x800)
        frozen = bool(getattr(sys, 'frozen', False))
        if frozen:
            # CVI first looks next to the application executable for cvirte/bin
            # and cvirte/fonts, before its system/registry fallback. Its legacy
            # GetModuleFileNameA buffer has capacity259, including the NUL.
            if len(str(Path(sys.executable).resolve()).encode('mbcs')) >= 259:
                raise RuntimeError('The PY_SPF executable path exceeds the legacy NI limit; install in a shorter directory.')
            private_root = Path(sys.executable).resolve().parent / 'cvirte'
            required = ('bin/cvirte.rsc', 'bin/msgrte.txt', 'bin/cvierror.txt',
                        'fonts/ni7seg.ttf', 'fonts/nisystem.ttf')
            if any(not (private_root / name).is_file() for name in required):
                raise RuntimeError('Missing EXE-adjacent private CVI resources; reinstall PY_SPF.')
            from .private_fonts import PrivateNativeFonts
            self._private_fonts = PrivateNativeFonts(runtime / 'fonts', private_root / 'fonts')
        # Frozen mode uses the vendor's intended app-local resource layout and
        # never creates a temporary key or masks the process registry. Preserve
        # the original Python/source-mode initialization path.
        registry = contextlib.nullcontext() if frozen else _private_runtime_registry(runtime)
        with registry:
            self.dll = C.WinDLL(str(runtime / 'cvirte.dll'))
            self.varargs = C.CDLL(str(runtime / 'cvirte.dll'))
            init = self.dll.InitCVIRTDll
            init.argtypes = [C.c_void_p] * 11
            init.restype = C.c_int
            if not init(self._module, None, 0, None, 0, None, 0, None, 0, None, None):
                raise RuntimeError('NI CVI runtime initialization failed.')
        if frozen:
            resource_path = C.create_string_buffer(4096)
            getter = getattr(self.varargs, '__GetResDirPathString')
            getter.argtypes = [C.c_void_p]
            getter.restype = C.c_void_p
            getter(resource_path)
            self.resource_directory = Path(resource_path.value.decode('mbcs', errors='strict'))
            if not resource_path.value or not self.resource_directory.samefile(private_root / 'bin'):
                raise RuntimeError('NI selected resources outside this application; startup has been stopped.')
        self.dll.DisableBreakOnLibraryErrors()
        for panel in (7, 5, 6, 9, 2, 3, 4, 8, 1):
            handle = self.dll.LoadPanel(0, self._bytes(RESOURCES / 'SPITFIRE.UIR'), panel)
            self._check(handle, 'load original panel ' + str(panel))
            self.panels[panel] = handle
        server = self.dll.LoadPanel(0, self._bytes(RESOURCES / 'SERVER.UIR'), 1)
        self._check(server, 'load original server panel')
        self.panels['server'] = server
        for key in self.panels:
            self._bind_panel(key)
        self._initialize_connection_layout()
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
        diagnostics = getattr(self, '_read_diagnostics', None)
        if dtype == 9:
            if diagnostics is not None:
                diagnostics['timer_values_skipped'] += 1
            return self.values.get((panel, control), 0)
        if diagnostics is not None:
            diagnostics['get_ctrl_val_calls'] += 1
            diagnostics['last_control'] = [panel, control, dtype]
        val = C.create_string_buffer(8192)
        rc = self.dll.GetCtrlVal(self.panels[panel], control, val)
        if rc < 0:
            if diagnostics is not None:
                diagnostics['get_ctrl_val_errors'] += 1
            return self.values.get((panel, control), 0)
        if dtype == 5:
            return val.value.decode('mbcs', errors='replace')
        if dtype == 4:
            return struct.unpack('<d', val.raw[:8])[0]
        if dtype == 3:
            return struct.unpack('<f', val.raw[:4])[0]
        return struct.unpack('<i', val.raw[:4])[0]

    def _hardware_controls(self):
        from .callbacks import SHOW_PANELS, HIDE_PANELS
        navigation = set(SHOW_PANELS) | set(HIDE_PANELS) | {
            'QuitProgram', 'Shutdown', 'exit_from_menu', 'display_faults', 'cmtRETUSERMODE',
        }
        return {(panel['id'], control['id'])
                for panel in self.spec['panels'] if panel['id'] in (2, 3, 5, 6, 8, 9)
                for control in panel['controls']
                if control.get('attributes', {}).get('ctrl_mode') in (1, 2)
                and control.get('callback', '') not in navigation | _LOCAL_CONTROLS}

    def _initialize_connection_layout(self):
        # UIR defaults include a full-panel gray curtain. Establish the visible
        # native layout before DisplayPanel, even when a caller attaches a
        # controller later or embeds the view without Controller.start().
        for control in (49, 54):
            self.set_attribute(6, control, 530, 0)
        self.set_menu_attribute(6, 0, 500, 0)
        for panel, control in self._read_only_controls:
            self._initial_device_dimming[panel, control] = self.read_attribute(panel, control, 500)
            self.set_attribute(panel, control, 500, 1)

    def connection_presentation(self):
        """Keep the native layout visible offline without exposing device input."""
        from .callbacks import SHOW_PANELS, HIDE_PANELS
        navigation = set(SHOW_PANELS) | set(HIDE_PANELS) | {
            'QuitProgram', 'Shutdown', 'exit_from_menu', 'display_faults', 'cmtRETUSERMODE',
        }
        controls = {}
        for panel in self.spec['panels']:
            for control in panel['controls']:
                attrs = control.get('attributes', {})
                style = attrs.get('ctrl_style', 0)
                callback = control.get('callback', '')
                editable = attrs.get('ctrl_mode') in (1, 2)
                device_readout = panel['id'] in (2, 3, 5, 6, 8, 9) and (
                    100 <= style < 150 or 200 <= style < 290 or 300 <= style < 340)
                if (editable or device_readout) and callback not in navigation:
                    key = panel['id'], control['id']
                    controls[key] = (self._initial_device_dimming[key] if key in self._initial_device_dimming
                                     else self.read_attribute(*key, 500))
        return {'controls': controls,
                'alarm': {attribute: self.read_attribute(6, 50, attribute)
                          for attribute in (500, 641, 880)}}

    def set_connection_status(self, ready, message):
        demo = self.controller is not None and self.controller.demo
        read_only = self.controller is not None and getattr(self.controller, 'read_only', False)
        mode = ('DEMO - ' if demo else '') + ('READ ONLY - ' if read_only else '')
        if ready:
            title = f'Spitfire [{mode}CONNECTED]'
        else:
            detail = ' '.join(str(message).split())[:180]
            title = f'Spitfire [{mode}OFFLINE - no live data] - {detail}'
        self._check(self.varargs.SetPanelAttribute(self.panels[6], 573, C.c_char_p(self._bytes(title))),
                    'show connection status in native title')

    def read_attribute(self, panel, control, attribute):
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
        rc = self.varargs.SetCtrlVal(self.panels[panel], int(control),
                                    self._argument(value, self._dtype(panel, control)))
        self._check(rc, f'set panel {panel} control {control}')
        if panel == 6 and control == 54:
            # DARKSCREEN is intentionally shown before STATUS? arrives. Its
            # original z-order hides the loading/error text behind it on native
            # Windows, leaving a blank gray window. Keep the message in front.
            # Keep the connection message above the alarm button instead of
            # drawing the original 31-point centered text across that button.
            for attribute, setting in ((531, 40), (532, 96), (533, 600),
                                       (540, 140), (686, 18), (610, 0)):
                self._check(self.varargs.SetCtrlAttribute(self.panels[6], 54, attribute,
                                                         C.c_int(setting)),
                            'show readable connection message in front of curtain')

    def set_attribute(self, panel, control, attribute, value):
        if (attribute == 500 and self.controller is not None
                and getattr(self.controller, 'read_only', False)
                and (panel, control) in self._read_only_controls):
            value = 1
        spec = next((a for a in self.attributes.values() if a['id'] == attribute), {})
        dtype = spec.get('type', 1)
        if dtype == 9:
            dtype = self._dtype(panel, control)
        self._check(self.varargs.SetCtrlAttribute(self.panels[panel], int(control), int(attribute),
                                                 self._argument(value, dtype)),
                    f'set control attribute {attribute}')

    def set_panel_attribute(self, panel, attribute, value):
        self._check(self.varargs.SetPanelAttribute(self.panels[panel], int(attribute),
                                                  self._argument(value)),
                    f'set panel attribute {attribute}')

    def set_menu_attribute(self, panel, item, attribute, value):
        menubar = self.dll.GetPanelMenuBar(self.panels[panel])
        return self.varargs.SetMenuBarAttribute(menubar, int(item), int(attribute),
                                                self._argument(value))

    def show_panel(self, panel, visible=True):
        return (self.dll.DisplayPanel if visible else self.dll.HidePanel)(self.panels[panel])

    def show_server(self, visible=True):
        return self.show_panel('server', visible)

    def log(self, text):
        self.events.append(str(text))
        if len(self.events) > 2000:
            del self.events[:-1000]
        if str(text).startswith(('connection:', 'UDP error:')):
            print(text, file=sys.stderr, flush=True)

    def show_warning(self, title, text, on_confirm=None):
        self.dll.MessagePopup(self._bytes(title), self._bytes(text))
        if on_confirm:
            on_confirm()

    def request_close(self):
        if self.controller:
            self.controller.running = False

    def attach(self, controller):
        self.controller = controller

    def _control_event(self, name, panel, control, event):
        if self.controller is None or event not in _CONTROL_EVENTS.get(name, (1,)):
            return
        if (getattr(self.controller, 'read_only', False)
                and (panel, control) in self._read_only_controls):
            return
        if name == 'tmr_Mouse_Callback1':
            if not (self._user.GetAsyncKeyState(1) & 0x8000 or
                    self._user.GetAsyncKeyState(2) & 0x8000):
                self.controller.mouse_released()
                return
        value = self.read(panel, control) if event == 1 and _callback_needs_value(name) else 0
        self.controller.handle_callback(name, value, event, panel, control)

    def _bind_panel(self, panel):
        entries = self.bindings['SERVER' if panel == 'server' else 'SPITFIRE']
        resource_panel = 1 if panel == 'server' else panel
        callback_type = C.CFUNCTYPE(C.c_int, C.c_int, C.c_int, C.c_int,
                                     C.c_void_p, C.c_int, C.c_int)
        for entry in entries:
            if entry['kind'] != 'control' or entry['panel'] != resource_panel:
                continue
            def callback(handle, control, event, data, event1, event2, *, name=entry['name'], p=panel):
                try:
                    self._control_event(name, p, control, event)
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
            self.menu_ids[constant] = item
            def menu_callback(bar, menu_item, data, panel, *, name=callback_name):
                if self.controller:
                    self.controller.handle_callback(name, 0, 1, 6, menu_item)
            cb = menu_type(menu_callback)
            self._callbacks.append(cb)
            self.dll.InstallMenuCallback(menubar, item, cb, None)

    def process_events(self):
        self.dll.ProcessSystemEvents()

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
        if self._private_fonts is not None:
            self._private_fonts.close()


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
    from .diagnostics import SessionDiagnostics
    from .native_ticker import NativeEventTicker
    import traceback
    view = controller = diagnostics = ticker = None
    code = 0
    try:
        view = NativeGui()
        controller = make_controller(view, opts)
        view.attach(controller)
        diagnostics = SessionDiagnostics(controller, getattr(opts, 'diagnostics_dir', None))
        controller.start()
        ticker = NativeEventTicker(controller, diagnostics)
        view._ticker_diagnostics = ticker.stats
        while controller.running:
            view.process_events()
            ticker.stats['outer_event_cycles'] += 1
            ticker.raise_if_failed()
            ticker.tick()
            ticker.raise_if_failed()
            time.sleep(0.005)
    except KeyboardInterrupt:
        code = 130
    except BaseException:
        traceback.print_exc()
        code = 1
    finally:
        try:
            if ticker is not None:
                ticker.close()
            if controller is not None:
                controller.stop()
            if view is not None:
                view.close()
        except BaseException:
            traceback.print_exc()
            code = 1
        finally:
            if diagnostics is not None:
                diagnostics.close()
    sys.stdout.flush()
    sys.stderr.flush()
    C.WinDLL('kernel32').ExitProcess(code)
    return code

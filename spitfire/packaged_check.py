"""Bounded Native GUI verification using only an in-memory device simulator."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import traceback


def _module_path(handle):
    call = ctypes.WinDLL('kernel32').GetModuleFileNameW
    call.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
    call.restype = ctypes.c_uint32
    text = ctypes.create_unicode_buffer(32768)
    if not call(handle, text, len(text)):
        raise ctypes.WinError()
    return str(Path(text.value).resolve())


def _snapshot(view, path):
    class Rect(ctypes.Structure):
        _fields_ = [(n, ctypes.c_int) for n in ('top', 'left', 'height', 'width')]
    bitmap = ctypes.c_int()
    capture = view.dll.GetPanelDisplayBitmap
    capture.argtypes = [ctypes.c_int, ctypes.c_int, Rect, ctypes.POINTER(ctypes.c_int)]
    capture.restype = ctypes.c_int
    view._check(capture(view.panels[6], 1, Rect(0, 0, -1, -1), ctypes.byref(bitmap)), 'capture main panel')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        view._check(view.dll.SaveBitmapToBMPFile(bitmap.value, view._bytes(path)), 'save native BMP')
    finally:
        view.dll.DiscardBitmap(bitmap.value)


def main(argv=None, *, default_output=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=default_output)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--duration', type=float, default=20)
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument('--offline', action='store_true')
    scenario.add_argument('--drop-optout-ack', action='store_true')
    options = parser.parse_args(argv)
    report = {'schema_version': 1, 'mode': 'in-memory simulator only',
              'physical_device_io': False, 'frozen': bool(getattr(sys, 'frozen', False)),
              'python_bits': struct.calcsize('P') * 8, 'executable': sys.executable,
              'ignore_python_environment': bool(sys.flags.ignore_environment),
              'ignore_user_site': bool(sys.flags.no_user_site),
              'acp': ctypes.WinDLL('kernel32').GetACP(), 'phases': []}
    view = controller = diagnostics = ticker = None
    code = 1
    try:
        from .__main__ import arguments, make_controller
        from .diagnostics import SessionDiagnostics
        from .native import NativeGui, RESOURCES
        from .native_ticker import NativeEventTicker
        from . import controller as module
        from .simulator import SimulatedTransport
        from .protocol import PACKET_PREFIX
        class ForbiddenTransport:
            def __init__(self, *args, **kwargs):
                raise AssertionError('Self-test must not open a real UDP transport')
        module.UDPTransport = ForbiddenTransport
        class TestTransport(SimulatedTransport):
            def receive(self):
                replies = super().receive()
                if options.offline:
                    return []
                if options.drop_optout_ack:
                    return [x for x in replies if not x.body.startswith('<2036>')]
                return replies
        module.SimulatedTransport = TestTransport
        started = time.monotonic()
        report['resources'] = str(RESOURCES.resolve())
        view = NativeGui()
        report['phases'].append('ten_native_panels_loaded')
        report['panel_count'] = len(view.panels)
        opts = arguments(['--demo', '--backend', 'native', '--tcp-port', '0', '--local-port', '0', '--host', '127.0.0.1'])
        controller = make_controller(view, opts)
        view.attach(controller)
        diagnostics = SessionDiagnostics(controller)
        ticker = NativeEventTicker(controller, diagnostics)
        controller.start()
        assert isinstance(controller.transport, SimulatedTransport), 'Unexpected transport in simulator test'
        deadline = started + min(max(options.duration, 1.0), 40.0)
        while controller.running and time.monotonic() < deadline:
            view.process_events()
            ticker.tick()
            ticker.raise_if_failed()
            if options.offline:
                if controller.startup and controller.startup.complete and controller._startup_retry_deadline:
                    break
            elif controller.state.get('gui_ready') and controller.state.get('curtain_not_open') == 0:
                break
            time.sleep(.005)
        for _ in range(5):
            view.process_events()
            time.sleep(.01)
        visibility = {name: view.read_attribute(6, ctrl, 530)
                      for name, ctrl in [('curtain_visible', 49), ('loading_visible', 54), ('run_visible', 10), ('stop_visible', 11)]}
        menu = view.dll.GetPanelMenuBar(view.panels[6])
        menu_dimmed = ctypes.c_int()
        view._check(view.dll.GetMenuBarAttribute(menu, 0, 500, ctypes.byref(menu_dimmed)), 'read main menu')
        report.update(connected=bool(controller.state.get('connected')), gui_ready=bool(controller.state.get('gui_ready')),
                      optout=controller.state.get('emp_optout'), displayed_optout=view.read(2, 9),
                      visibility=visibility, menu_dimmed=menu_dimmed.value,
                      cvirte_loaded_from=_module_path(view.dll._handle),
                      expected_cvirte=str((RESOURCES / 'runtime/cvirte.dll').resolve()),
                      resource_directory=str(getattr(view, 'resource_directory', 'source mode')),
                      expected_resource_directory=str(Path(sys.executable).resolve().parent / 'cvirte/bin'),
                      elapsed_seconds=round(time.monotonic() - started, 3),
                      controls_updated=len(controller.values), timer=ticker.stats,
                      callback_errors=[str(v) for _, k, v in controller.events if k == 'callback'])
        report['transport_class'] = type(controller.transport).__name__
        report['tcp_server_enabled'] = controller.tcp is not None
        python_name = 'python%d%d.dll' % sys.version_info[:2]
        python_handle = view._kernel.GetModuleHandleW(python_name)
        report['python_dll_loaded_from'] = _module_path(python_handle)
        report['expected_python_dll'] = str(Path(sys.executable).resolve().parent / '_internal' / python_name)
        report['cvirte_sha256'] = hashlib.sha256((RESOURCES / 'runtime/cvirte.dll').read_bytes()).hexdigest()
        assert report['panel_count'] == 10, report
        assert Path(report['cvirte_loaded_from']) == Path(report['expected_cvirte']), report
        if report['frozen']:
            report['private_fonts'] = view._private_fonts.verify()
            report['font_loading'] = 'process-private memory; adjacent files are loader placeholders'
            assert report['acp'] == 65001, report
            assert Path(report['resource_directory']).samefile(report['expected_resource_directory']), report
            assert Path(report['python_dll_loaded_from']).samefile(report['expected_python_dll']), report
            assert not report['tcp_server_enabled'], report
        assert visibility == {'curtain_visible': 0, 'loading_visible': 0, 'run_visible': 1, 'stop_visible': 1}, report
        assert not report['callback_errors'] and menu_dimmed.value == 0, report
        if options.offline:
            assert not report['connected'] and not report['gui_ready'], report
            assert view.read_attribute(6, 10, 500) == 1, report
        else:
            assert report['connected'] and report['gui_ready'], report
            assert report['optout'] == report['displayed_optout'] == 1, report
        # Read/show every normal View panel using NI APIs, with no button callbacks.
        report['view_panels'] = []
        for panel in (2, 3, 4, 5, 8, 9):
            view.show_panel(panel)
            view.process_events()
            view.show_panel(panel, False)
            report['view_panels'].append(panel)
        view.show_panel(6)
        for _ in range(5):
            view.process_events()
            time.sleep(.01)
        if options.snapshot:
            _snapshot(view, options.snapshot.resolve())
            report['snapshot'] = str(options.snapshot.resolve())
        packets = [line for packet in controller.transport.sent_packets
                   for line in packet[len(PACKET_PREFIX):].decode('ascii').splitlines()]
        report['simulator_packets'] = len(controller.transport.sent_packets)
        report['identity_queries'] = packets.count('[1000]*idn?')
        if options.offline:
            assert packets == ['[1000]*idn?'] * 3, report
        report['phases'].append('native_simulator_validation_passed')
        code = 0
    except BaseException:
        report['error'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        try:
            if ticker is not None:
                ticker.close()
            if controller is not None:
                controller.stop()
            if view is not None:
                view.close()
            report['phases'].append('native_closed')
        except BaseException:
            report['close_error'] = traceback.format_exc()
            code = 1
        report['exit_code'] = code
        if options.output:
            options.output.parent.mkdir(parents=True, exist_ok=True)
            options.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        # Same mandatory shutdown boundary as the shipped Native application.
        ctypes.WinDLL('kernel32').ExitProcess(code)
    return code

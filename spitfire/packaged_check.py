"""Bounded Native GUI verification using only an in-memory device simulator."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import time
import traceback


_STARTUP_WRITES = frozenset(('[2036]EMPOPTOUT 1', '[2047]EMP:LBOBREAK 1'))
_TEN_HZ_WRITES = frozenset(('[2031]TDG:TRIG:MODE INT',
                            '[2032]TDG:TRIG:FREQ 10.00',
                            '[2020]TDG:DIV  1.00'))


def _packet_messages(packets):
    from .protocol import PACKET_PREFIX
    result = []
    for packet in packets:
        assert packet.startswith(PACKET_PREFIX), 'Unexpected simulator packet header'
        result.extend(packet[len(PACKET_PREFIX):].decode('ascii').splitlines())
    return result


class _SimulatorWriteGuard:
    """Final send gate for this simulator check, never a device-control policy."""
    def __init__(self):
        super().__init__()
        self.allowed_write_messages = _STARTUP_WRITES
        self.validation_phase = 'startup'
        self.write_audit = []
        self.forbidden_write_attempts = []

    def send_packet(self, packet):
        for message in _packet_messages((packet,)):
            match = re.fullmatch(r'\[(\d+)\].*', message)
            assert match, f'Malformed simulator request: {message!r}'
            if int(match[1]) >= 2000:
                if message not in self.allowed_write_messages:
                    self.forbidden_write_attempts.append(message)
                    raise AssertionError(f'Unexpected self-test write: {message}')
                self.write_audit.append({'phase': self.validation_phase, 'message': message})
        return super().send_packet(packet)


def _trigger_observation(view, controller):
    return {
        'mode_control': view.read(5, 3),
        'frequency_control_hz': view.read(5, 28),
        'divisor_control': view.read(5, 43),
        'int_pump_hz': view.read(6, 8),
        'int_amp_hz': view.read(6, 6),
        'ext_pump_hz': view.read(6, 9),
        'ext_amp_hz': view.read(6, 7),
        'confirmation': {key: controller.state.get(key) for key in (
            'internal_trigger_requested_hz', 'internal_trigger_actual_hz',
            'internal_trigger_pending', 'internal_trigger_confirmed',
            'internal_trigger_result')},
    }


def _exercise_internal_10hz(view, controller, ticker, report, *, timeout=5.0):
    """Exercise real Native set/read + commit adapter, using in-memory UDP only.

    Calling the shared Native adapter is not a Windows mouse or CVI event-delivery
    test. Fixture restoration is explicit and completed before the main bitmap.
    """
    from .simulator import SimulatedTransport
    board = controller.transport
    assert controller.demo and isinstance(board, SimulatedTransport)
    assert isinstance(board, _SimulatorWriteGuard) and controller.tcp is None
    baseline = _trigger_observation(view, controller)
    original_values = dict(board.values)
    preference = view.read(6, 48)
    record = report['internal_trigger_10hz'] = {
        'target_hz': 10.0, 'simulator_only': True,
        'event_path': 'NativeGui._control_event; EVENT_COMMIT=1',
        'windows_mouse_input_validated': False,
        'ni_event_delivery_validated': False,
        'baseline': baseline, 'restored_before_snapshot': False,
        'matched_readbacks': [],
    }
    callbacks = {'trig_mode': (5, 3), 'trig_reprate': (5, 28),
                 'DivisorCallback': (5, 43)}
    for name, (panel, control) in callbacks.items():
        bindings = [entry for entry in view.bindings['SPITFIRE']
                    if entry['kind'] == 'control' and entry['name'] == name]
        assert len(bindings) == 1 and (bindings[0]['panel'], bindings[0]['control']) == (panel, control)
    record['native_minimum_hz'] = view.read_attribute(5, 28, 731)
    record['native_maximum_hz'] = view.read_attribute(5, 28, 730)
    assert record['native_minimum_hz'] == 10.0 and record['native_maximum_hz'] == 10000.0, record

    original_receive = controller._receive
    packet_start = len(board.sent_packets)
    matched = record['matched_readbacks']

    def receive(line):
        before = controller.diagnostics['matched_replies']
        pending = controller.scheduler.last_sent
        pending_tag = pending.tag if pending and controller.scheduler.balance else None
        original_receive(line)
        match = re.search(r'<(\d+)>(.*)', line)
        if match and controller.diagnostics['matched_replies'] > before:
            tag = int(match[1])
            if tag in (1051, 1053, 1025):
                assert pending_tag == tag
                matched.append({'phase': board.validation_phase, 'tag': tag,
                                'payload': match[2], 'decorated': line})

    def wait_for(predicate, label):
        deadline = time.monotonic() + timeout
        while controller.running and time.monotonic() < deadline:
            view.process_events()
            ticker.tick()
            ticker.raise_if_failed()
            if predicate():
                return
            time.sleep(.005)
        raise AssertionError(f'Timed out waiting for {label}: {_trigger_observation(view, controller)}')

    def commit(name, value):
        panel, control = callbacks[name]
        view.set_value(panel, control, value)
        actual = view.read(panel, control)
        assert math.isclose(float(actual), float(value), rel_tol=0, abs_tol=1e-6), (name, value, actual)
        if name == 'trig_reprate' and value == 10.0 and board.validation_phase == 'internal-10hz':
            record['native_entered_hz'] = actual
        view._control_event(name, panel, control, 1)

    def target_verified():
        samples = [entry for entry in matched if entry['phase'] == 'internal-10hz']
        if not ({entry['tag'] for entry in samples} >= {1051, 1053, 1025}):
            return False
        state = controller.state
        return (state.get('internal_trigger_requested_hz') == 10.0
                and state.get('internal_trigger_actual_hz') == 10.0
                and state.get('internal_trigger_pending') is False
                and state.get('internal_trigger_confirmed') is True
                and state.get('internal_trigger_result') == 'confirmed'
                and float(view.read(5, 3)) == 0.0
                and float(view.read(5, 43)) == 1.0
                and float(view.read(6, 8)) == 10.0
                and float(view.read(6, 6)) == 10.0)

    controller._receive = receive
    changed = False
    try:
        board.validation_phase = 'internal-10hz'
        board.allowed_write_messages = _TEN_HZ_WRITES
        # The original mode/divisor callbacks use this local readback preference.
        # Its original value is restored; no device command changes it.
        view.set_value(6, 48, 1)
        changed = True
        commit('trig_mode', 0)
        commit('trig_reprate', 10.0)
        commit('DivisorCallback', 1.0)
        wait_for(target_verified, 'matched INT/10Hz/divisor1 readbacks and Native10Hz displays')
        record['confirmed'] = _trigger_observation(view, controller)
        target_packets = board.sent_packets[packet_start:]
        messages = _packet_messages(target_packets)
        writes = [message for message in messages if int(message[1:message.index(']')]) >= 2000]
        assert writes == ['[2031]TDG:TRIG:MODE INT', '[2032]TDG:TRIG:FREQ 10.00', '[2020]TDG:DIV  1.00'], writes
        samples = [entry for entry in matched if entry['phase'] == 'internal-10hz']
        assert any(entry['tag'] == 1051 and entry['payload'].strip() == 'INT' for entry in samples)
        assert any(entry['tag'] == 1053 and float(entry['payload']) == 10.0 for entry in samples)
        assert any(entry['tag'] == 1025 and float(entry['payload']) == 1.0 for entry in samples)
        record['messages'] = messages
        record['packets_hex'] = [packet.hex() for packet in target_packets]
    finally:
        try:
            if changed:
                board.validation_phase = 'restore-original'
                board.allowed_write_messages = frozenset((
                    '[2020]TDG:DIV %5.2f' % float(baseline['divisor_control']),
                    '[2032]TDG:TRIG:FREQ %5.2f' % float(baseline['frequency_control_hz']),
                    '[2031]TDG:TRIG:MODE ' + ('EXT' if baseline['mode_control'] else 'INT')))
                start = len(matched)
                commit('DivisorCallback', baseline['divisor_control'])
                commit('trig_reprate', baseline['frequency_control_hz'])
                commit('trig_mode', baseline['mode_control'])
                wait_for(lambda: {entry['tag'] for entry in matched[start:]} >= {1025, 1053, 1051},
                         'original Native setting readbacks')
                # Restore the exact fixture strings too. Native range handling can
                # make its divisor differ from the simulator's original raw value.
                # Refresh through matching queries rather than fabricating displays.
                board.values.clear()
                board.values.update(original_values)
                board.validation_phase = 'restore-fixture-readback'
                board.allowed_write_messages = frozenset()
                start = len(matched)
                for tag in (1051, 1053, 1025):
                    controller.scheduler.push(tag)
                wait_for(lambda: {entry['tag'] for entry in matched[start:]} >= {1051, 1053, 1025},
                         'restored in-memory fixture readbacks')
                restored = _trigger_observation(view, controller)
                for field, expected in baseline.items():
                    if field != 'confirmation':
                        assert math.isclose(float(restored[field]), float(expected), rel_tol=0, abs_tol=1e-6), (field, expected, restored[field])
                assert board.values == original_values
                record['restored'] = restored
                record['restoration_method'] = 'Native commits; exact in-memory fixture reset; matching query/decoder refresh'
                record['restored_before_snapshot'] = True
        except BaseException:
            record['restore_error'] = traceback.format_exc()
            raise
        finally:
            view.set_value(6, 48, preference)
            controller._receive = original_receive
            board.allowed_write_messages = frozenset()
            record['all_phase_messages'] = _packet_messages(board.sent_packets[packet_start:])


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
        class TestTransport(_SimulatorWriteGuard, SimulatedTransport):
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
        if not options.offline and not options.drop_optout_ack:
            _exercise_internal_10hz(view, controller, ticker, report)
            report['phases'].append('internal_trigger_10hz_verified_and_restored')
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
        packets = _packet_messages(controller.transport.sent_packets)
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
        if controller is not None and isinstance(getattr(controller, 'transport', None), _SimulatorWriteGuard):
            transport = controller.transport
            report['simulator_write_audit'] = transport.write_audit
            report['forbidden_write_attempts'] = transport.forbidden_write_attempts
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

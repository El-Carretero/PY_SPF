"""Validate the boundary between offline tests and fixed read-only device I/O."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from spitfire_control import __version__
from spitfire_control.app import main as app_main
from spitfire_control.commands import COMMANDS, CommandSpec, Risk
from spitfire_control.protocol import decode_command_datagram, encode_reply, Reply
from spitfire_control.state import DeviceState
from spitfire_control.transport import SimulatorTransport, UdpSettings
from spitfire_control.validation import (
    READ_ONLY_COMMANDS, ProbeOptions, ReadOnlyUdpTransport, RunReport,
    assess_reply, checked_line, hardware_probe, literal_ipv4, main,
    require_read_only_line, verify_exe_manifest,
)


class LoopbackController:
    """Only a local emulator. Never evidence from a physical controller."""
    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('127.0.0.1', 0))
        self.socket.settimeout(.05)
        self.port = self.socket.getsockname()[1]
        self.commands = []
        self.stop = threading.Event()
        self.sim = SimulatorTransport()
        self.sim.connect()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.is_set():
            try:
                packet, sender = self.socket.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            for command in decode_command_datagram(packet):
                self.commands.append(command)
                cid = command.command_id
                if cid in self.overrides:
                    value = self.overrides[cid]
                else:
                    value = self.sim.exchange(f'[{cid}]{command.command}', 1)[0].value
                if value is not None:
                    self.socket.sendto(encode_reply([(cid, value)]), sender)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(1)
        self.socket.close()
        self.sim.close()


class ValidationBoundaryTests(unittest.TestCase):
    def test_allowlist_blocks_every_write_and_ambiguous_read(self):
        for cid, spec in COMMANDS.items():
            if cid not in READ_ONLY_COMMANDS:
                with self.subTest(cid=cid), self.assertRaises(PermissionError):
                    require_read_only_line(f'[{cid}]{spec.text}')
        for cid in READ_ONLY_COMMANDS:
            self.assertEqual(require_read_only_line(checked_line(cid)), cid)

    def test_query_ids_cannot_smuggle_writes_or_arguments(self):
        for line in ('[1000]ON', '[1000]*idn?\n[2027]ON', '[1021]TDG:HV:ON',
                     '[1000]*idn?;ON', '[1000]*idn? x', '[1000]*idn?\r', '[1000]*idn?\n'):
            with self.subTest(line=line), self.assertRaises(PermissionError):
                require_read_only_line(line)

    def test_catalogue_change_is_fail_closed(self):
        with patch.dict(COMMANDS, {1000: CommandSpec(1000, 'ON', Risk.READ)}):
            with self.assertRaises(PermissionError):
                checked_line(1000)

    def test_literal_target_and_bounded_options(self):
        for host in ('laser.local', '255.255.255.255', '239.1.1.1', '0.0.0.0', '10.19.70.255', '::1'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                literal_ipv4(host)
        for kwargs in ({'timeout': float('nan')}, {'interval': .001}, {'cycles': 100},
                       {'max_seconds': float('inf')}, {'remote_port': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ProbeOptions('127.0.0.1', **kwargs).validate()

    def test_transport_rejects_write_before_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = RunReport(Path(tmp), 'test')
            try:
                transport = ReadOnlyUdpTransport(UdpSettings(), report, deadline=float('inf'))
                transport._socket = Mock()
                transport._remote = ('127.0.0.1', 1024)
                with self.assertRaises(PermissionError):
                    transport.exchange('[2027]ON', 1)
                transport._socket.sendto.assert_not_called()
            finally:
                report.finish()

    def test_journal_failure_prevents_actual_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = RunReport(Path(tmp), 'test')
            transport = ReadOnlyUdpTransport(UdpSettings(), report, deadline=float('inf'))
            transport._socket = Mock()
            transport._remote = ('127.0.0.1', 1024)
            try:
                with patch.object(report, 'event', side_effect=OSError('disk full')):
                    with self.assertRaises(Exception):
                        transport.exchange(checked_line(1000), 1)
                transport._socket.sendto.assert_not_called()
            finally:
                report.finish()

    def test_exe_selftest_never_loads_saved_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('spitfire_control.app.AppConfig.load') as load, \
                 patch('spitfire_control.validation_worker.write_result', return_value=0) as write:
                self.assertEqual(app_main(['--self-test-report', str(Path(tmp)/'result.json')]), 0)
                load.assert_not_called()
                write.assert_called_once()

    def test_exe_selftest_rejects_udp_before_loading_config(self):
        with patch('spitfire_control.app.AppConfig.load') as load, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                app_main(['--self-test-report', 'unused.json', '--udp'])
            self.assertEqual(exc.exception.code, 2)
            load.assert_not_called()

    def test_unknown_exe_or_changed_exe_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp)/'test.exe'
            exe.write_bytes(b'not executable; hash fixture only')
            with self.assertRaises(FileNotFoundError):
                verify_exe_manifest(exe)
            manifest = {'file': exe.name, 'self_test_protocol': 1, 'version': __version__,
                        'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()}
            exe.with_suffix('.validation.json').write_text(json.dumps(manifest), encoding='utf-8-sig')
            self.assertEqual(verify_exe_manifest(exe), manifest)
            exe.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                verify_exe_manifest(exe)


class HardwareProbeTests(unittest.TestCase):
    def run_probe(self, server, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        report = RunReport(Path(tmp.name), 'loopback-test')
        opts = ProbeOptions('127.0.0.1', local_host='127.0.0.1', local_port=0,
                            remote_port=server.port, timeout=.1, **kwargs)
        # Remove only inter-query sleeps in the local emulator tests.
        with patch('spitfire_control.validation.time.sleep'):
            hardware_probe(opts, report)
        code = report.finish()
        return report, code

    def test_complete_plan_sends_only_allowlisted_reads(self):
        with LoopbackController() as server:
            report, code = self.run_probe(server)
        self.assertEqual(code, 0)
        self.assertEqual([c.command_id for c in server.commands], list(READ_ONLY_COMMANDS))
        for command in server.commands:
            self.assertEqual(command.command, READ_ONLY_COMMANDS[command.command_id])
        self.assertFalse(report.data['physical_safety_verified'])
        self.assertFalse(report.data['windows_execution_verified'])
        trace = [json.loads(line) for line in (report.directory/'trace.jsonl').read_text().splitlines()]
        self.assertEqual(sum(e['event'] == 'tx_sent' for e in trace), len(READ_ONLY_COMMANDS))
        prf = next(c for c in report.data['checks'] if c['name'] == 'query 1010')
        self.assertEqual(prf['evidence']['decoded'], 1000)

    def test_hv_on_stops_without_off_or_further_queries(self):
        with LoopbackController({1021: '1'}) as server:
            report, code = self.run_probe(server)
        self.assertEqual(code, 2)
        self.assertEqual([c.command_id for c in server.commands], [1000, 1021])
        self.assertEqual(report.data['overall'], 'INCOMPLETE')

    def test_positive_output_stops_without_control_writes(self):
        with LoopbackController({1008: '0.01'}) as server:
            _, code = self.run_probe(server)
        self.assertEqual(code, 2)
        self.assertEqual([c.command_id for c in server.commands], [1000, 1021, 1007, 1008])

    def test_missing_identity_stops_after_one_request(self):
        with LoopbackController({1000: None}) as server:
            report, code = self.run_probe(server)
        self.assertEqual(code, 1)
        self.assertEqual([c.command_id for c in server.commands], [1000])
        self.assertEqual(report.data['overall'], 'FAIL')

    def test_identity_mismatch_stops_before_other_queries(self):
        with LoopbackController() as server:
            _, code = self.run_probe(server, expect_idn='different serial number')
        self.assertEqual(code, 1)
        self.assertEqual([c.command_id for c in server.commands], [1000])

    def test_two_consecutive_timeouts_stop_plan(self):
        with LoopbackController({1034: None, 1035: None}) as server:
            _, code = self.run_probe(server)
        self.assertEqual(code, 1)
        self.assertEqual(server.commands[-1].command_id, 1035)
        self.assertEqual(len(server.commands), 8)

    def test_busy_port_fails_without_transmitting(self):
        with LoopbackController() as server, tempfile.TemporaryDirectory() as tmp:
            report = RunReport(Path(tmp), 'loopback-test')
            opts = ProbeOptions('127.0.0.1', local_host='127.0.0.1', local_port=server.port,
                                remote_port=server.port, timeout=.1)
            hardware_probe(opts, report)
            self.assertEqual(report.finish(), 1)
            self.assertEqual(server.commands, [])

    def test_cancel_closes_socket_and_keeps_incomplete_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = RunReport(Path(tmp), 'test')
            with patch('spitfire_control.validation.ReadOnlyUdpTransport') as transport:
                transport.return_value._remote = ('127.0.0.1', 1024)
                transport.return_value._socket.getsockname.return_value = ('127.0.0.1', 1025)
                transport.return_value.exchange.side_effect = KeyboardInterrupt
                with self.assertRaises(KeyboardInterrupt):
                    hardware_probe(ProbeOptions('127.0.0.1'), report)
                transport.return_value.close.assert_called_once()
            self.assertEqual(report.finish(interrupted=True), 130)

    def test_deadline_is_checked_at_actual_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = RunReport(Path(tmp), 'test')
            transport = ReadOnlyUdpTransport(UdpSettings(), report, deadline=0)
            transport._socket = Mock()
            transport._remote = ('127.0.0.1', 1024)
            try:
                with self.assertRaises(Exception):
                    transport.exchange(checked_line(1000), 1)
                transport._socket.sendto.assert_not_called()
            finally:
                report.finish()

    def test_offline_failure_prevents_hardware_phase(self):
        with tempfile.TemporaryDirectory() as tmp, patch('spitfire_control.validation.offline_checks') as offline, \
             patch('spitfire_control.validation.hardware_probe') as hardware, contextlib.redirect_stdout(io.StringIO()):
            def failed(report, exe):
                report.add('preflight', 'FAIL', 'test failure')
                return False
            offline.side_effect = failed
            code = main(['hardware', '--host', '127.0.0.1', '--output', tmp])
            self.assertEqual(code, 1)
            hardware.assert_not_called()


class ProbeInterpretationTests(unittest.TestCase):
    def test_numeric_firmware_version_is_valid_text(self):
        status, _, _ = assess_reply(1034, Reply(1034, '1.6.0', '<1034>1.6.0'), DeviceState())
        self.assertEqual(status, 'PASS')

    def test_invalid_gate_response_is_not_zero(self):
        for raw in ('nan', 'ERROR: interlock', '', '-1', 'UNKNOWN', '2'):
            with self.subTest(raw=raw):
                status, _, stop = assess_reply(1021, Reply(1021, raw, raw), DeviceState())
                self.assertEqual(status, 'FAIL')
                self.assertTrue(stop)

    def test_delay_flags_must_be_observed(self):
        status, _, _ = assess_reply(1045, Reply(1045, '12.5', '<1045>12.5'), DeviceState())
        self.assertEqual(status, 'WARN')

    def test_module_fault_and_optout_are_not_healthy_passes(self):
        for cid, raw, expected in ((1013, '2048', 'FAIL'), (1068, '1', 'WARN'), (1014, '1 0 0 0', 'WARN')):
            status, _, _ = assess_reply(cid, Reply(cid, raw, raw), DeviceState())
            self.assertEqual(status, expected)

    def test_html_escapes_controller_supplied_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = RunReport(Path(tmp), 'test')
            report.add('identity', 'PASS', '<script>alert(1)</script>', raw='<img src=x onerror=alert(1)>')
            report.finish()
            text = (report.directory/'report.html').read_text(encoding='utf-8')
            self.assertNotIn('<script>', text)
            self.assertNotIn('<img src=x', text)
            self.assertIn('&lt;script&gt;', text)


if __name__ == '__main__':
    unittest.main()

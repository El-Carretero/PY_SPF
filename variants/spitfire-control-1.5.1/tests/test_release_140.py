"""Regressions grounded in the 2026-10-28 XP wire captures. No device I/O."""
import csv
import tempfile
import unittest

from spitfire_control.commands import engineering_argument, format_command
from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.profiles import validate_profile_command
from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState
from spitfire_control.transport import SimulatorTransport, TransportError
from test_external_profile import healthy


class ReceiptSimulator(SimulatorTransport):
    def __init__(self):
        super().__init__(); self.responses = {}; self.ignored = set()
    def exchange(self, line, timeout, *, send_guard=None):
        cid = int(line[1:line.index(']')])
        if cid in self.ignored:
            if send_guard: send_guard(lambda: self.command_history.append((cid, line)))
            replies = [Reply(cid, '', f'<{cid}>')]
        else:
            replies = super().exchange(line, timeout, send_guard=send_guard)
        if cid in self.responses:
            value = self.responses[cid]
            if isinstance(value, Exception): raise value
            return [Reply(cid, value, f'<{cid}>{value}')]
        if cid >= 2000: return [Reply(cid, '', f'<{cid}>')]
        return replies


class Release140Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.t = ReceiptSimulator(); self.t.connect()
        self.c = LaserController(self.t, auto_poll=False, log_directory=self.temp.name)
        healthy(self.c._state)
        self.addCleanup(self.c.stop)
    def drain(self, limit=150):
        for _ in range(limit):
            if not self.c._commands and not self.c._urgent: return
            self.c._execute((self.c._urgent or self.c._commands).popleft())
        self.fail('queue did not drain')
    def writes(self): return [cid for cid, _ in self.t.command_history if cid >= 2000]
    def audit(self):
        with self.c._audit.path.open(encoding='utf-8', newline='') as f: return list(csv.DictReader(f))
    def test_current_engineering_to_wire_matches_xp(self):
        self.assertEqual(engineering_argument(2003, '17.0'), '170.00')
        self.assertEqual(format_command(2003, '170.00'), '[2003]EMP:DIODE:CURR 170.00')
    def test_current_wire_to_engineering_matches_xp(self):
        for cid in (1007,1009):
            s=DeviceState(); self.assertTrue(s.apply(Reply(cid,'170.00',f'<{cid}>170.00')))
            self.assertEqual(s.value(cid),17.0)
    def test_current_sentinel_not_scaled(self):
        s=DeviceState(); s.apply(Reply(1009,'-99','<1009>-99'))
        self.assertEqual(s.value(1009),-99)
    def test_current_rejects_nonfinite_and_negative_input(self):
        for value in ('NaN','Inf','-1','1e9999'):
            with self.subTest(value=value), self.assertRaises(ValueError): engineering_argument(2003,value)
    def test_external_all_four_fault_resets_allowed(self):
        for cid in (2044,2049,2052,2050): validate_profile_command(cid,None,'external')
        for cid in (2005,2027,2034,2054):
            with self.assertRaises(PermissionError): validate_profile_command(cid,None,'external')
    def test_empty_source_receipts_do_not_cancel_second_write(self):
        self.c.submit(2030,'EXT');self.c.submit(2031,'EXT');self.drain()
        self.assertEqual(self.writes(),[2030,2031])
        self.assertEqual((self.c.state.value(1050),self.c.state.value(1051)),(1,1))
    def test_empty_hv_setpoint_receipts_do_not_cancel_second_write(self):
        self.c.submit(2025,'3.3');self.c.submit(2026,'3.1');self.drain()
        self.assertEqual(self.writes(),[2025,2026])
        self.assertEqual((self.c.state.value(1040),self.c.state.value(1041)),(3300,3100))
    def test_empty_resets_continue_all_four(self):
        for cid in (2044,2049,2052,2050):self.c.submit(cid)
        self.drain();self.assertEqual(self.writes(),[2044,2049,2052,2050])
    def test_explicit_error_cancels_remaining_and_audits_each(self):
        self.t.responses[2030]='NACK';self.c.submit(2030,'EXT');self.c.submit(2031,'EXT');self.drain()
        self.assertEqual(self.writes(),[2030])
        self.assertTrue(any(r['direction']=='CANCEL' and r['command_id']=='2031' for r in self.audit()))
    def test_receipt_without_application_is_not_confirmed(self):
        self.t.ignored.add(2030);self.c.submit(2030,'EXT');self.c.submit(2031,'EXT');self.drain()
        self.assertEqual(self.writes(),[2030])
        self.assertTrue(any(r['direction']=='READBACK_MISMATCH' for r in self.audit()))
    def test_timeout_never_retries_write(self):
        self.t.responses[2030]=TransportError('reply lost');self.c.submit(2030,'EXT');self.c.submit(2031,'EXT');self.drain()
        self.assertEqual(self.writes(),[2030])
    def test_simulator_default_current_is_18_A(self):
        self.c._execute(PendingCommand(1009,None,'test'))
        self.assertEqual(self.c.state.value(1009),18.0)
    def test_reset_batch_preflight_is_atomic_and_duplicate_click_is_blocked(self):
        self.c.clear_faults()
        with self.assertRaises(ValueError):self.c.clear_faults()
        self.assertEqual([r.command_id for r in self.c._commands],[2044,2049,2052,2050])
        self.c._commands.clear()
        with self.assertRaises(ValueError):self.c.submit_batch(((2030,'EXT'),(2031,'EXT\nBAD')))
        self.assertFalse(self.c._commands)
    def test_unknown_empty_service_receipt_is_rejected(self):
        first=self.c.submit(2045);later=self.c.submit(2030,'EXT');self.drain()
        results={r.token:r for r in self.c.command_results}
        self.assertEqual(results[first].status,'rejected')
        self.assertEqual(results[later].status,'cancelled')
    def test_cancelled_requests_have_no_sent_or_confirmed_status(self):
        a=self.c.submit(2030,'EXT');b=self.c.submit(2031,'EXT');self.c.submit(2016);self.drain()
        for token in (a,b):
            result=next(r for r in self.c.command_results if r.token==token)
            self.assertEqual(result.status,'cancelled')
        self.assertEqual(self.writes(),[2016])
    def test_watch_deadline_does_not_claim_application(self):
        token=self.c.submit(2030,'EXT')
        self.c._execute(self.c._commands.popleft())
        self.c._expire_watches(float('inf'))
        self.assertEqual(next(r for r in self.c.command_results if r.token==token).status,'unverified')


if __name__=='__main__': unittest.main()

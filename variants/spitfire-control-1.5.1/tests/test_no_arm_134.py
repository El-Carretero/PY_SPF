"""1.3.4 no-ARM/reset/fault regressions. In-memory transport, no device I/O."""
import csv
import tempfile
from datetime import timedelta
import tkinter as tk
import unittest
from unittest.mock import patch
from spitfire_control.config import AppConfig
from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.protocol import Reply
from spitfire_control.transport import BaseTransport, TransportError
from spitfire_control.ui import SpitfireApp
from test_external_profile import healthy

class HardwareReplyFixture(BaseTransport):
    name = "Offline hardware reply fixture"  # Exercises hardware readback requirements.
    def __init__(self):
        self.answers = {}; self.sent = []
    def connect(self): pass
    def close(self): pass
    def exchange(self, line, timeout, *, send_guard=None):
        cid = int(line[1:line.index(']')])
        send = lambda: self.sent.append((cid, line))
        (send_guard(send) if send_guard else send())
        value = self.answers.get(cid, 'OK' if cid >= 2000 else '0')
        if isinstance(value, Exception): raise value
        return [Reply(cid, value, f'<{cid}>{value}')]

class AttachedOfflineController(LaserController):
    @property
    def running(self): return not self._stop.is_set()


class NoArmReset134Tests(unittest.TestCase):
    def setUp(self):
        self.logs = tempfile.TemporaryDirectory()
        self.addCleanup(self.logs.cleanup)
        self.t = HardwareReplyFixture()
        self.c = AttachedOfflineController(self.t, pump_mode='external', auto_poll=False, log_directory=self.logs.name)
        healthy(self.c._state)
        try: self.root = tk.Tk()
        except tk.TclError as exc: self.skipTest(str(exc))
        self.root.attributes('-alpha', 0.0)
        with patch.object(SpitfireApp, 'connect'):
            self.app = SpitfireApp(self.root, AppConfig(mode='udp', pump_mode='external', auto_poll=False))
        self.app.controller = self.c
        self.root.geometry('1024x768')
        self.sync()
    def tearDown(self):
        with patch.object(AppConfig, 'save'): self.app.close()
    def sync(self):
        self.app.state = self.c.state; self.app._refresh_ui(); self.root.update_idletasks()
    def receive(self, cid, value):
        self.t.answers[cid] = value
        self.c._execute(PendingCommand(cid, None, 'captured reply replay', self.c._generation))
        self.sync()
    def queued_writes(self):
        return [r.command_id for r in self.c._commands if r.command_id >= 2000]
    def writes(self):
        return [cid for cid, _ in self.t.sent if cid >= 2000]
    def clear(self, accept=True):
        with patch('spitfire_control.ui.messagebox.askyesno', return_value=accept) as confirm, patch('spitfire_control.ui.messagebox.showwarning') as warn:
            self.app._clear_faults()
        return confirm, warn
    def execute_next(self):
        self.c._execute((self.c._urgent or self.c._commands).popleft())
    def test_no_software_permission_latch_or_button(self):
        self.assertFalse(hasattr(self.c, 'arm'))
        self.assertFalse(hasattr(self.c.state, 'armed'))
        self.assertFalse(hasattr(self.app, 'arm_button'))
        self.assertEqual(self.writes(), [])
    def test_repeated_empty_readbacks_block_output_but_allow_reset(self):
        for cid in (1044,1069,1044,1069):
            self.receive(cid, '')
            self.assertFalse(self.c.state.is_fresh(cid))
            for cmd,arg in ((2017,None),(2019,'1 ON'),(2048,'CONT')):
                with self.assertRaises(PermissionError): self.c.submit(cmd,arg)
        confirm,warn=self.clear()
        confirm.assert_called_once();warn.assert_not_called()
        self.assertEqual(self.queued_writes(),[2044,2049,2052,2050])
    def test_real_key_and_main_bits_are_visible_without_blocking_reset(self):
        self.receive(1066,'0X00334408');self.receive(1039,'0X00334428');self.receive(1089,'5')
        self.assertTrue(self.c.state.fault_state(7));self.assertTrue(self.c.state.fault_state(10))
        self.assertIn('PC link: reply received. Controller Main comm flag: SET', self.app.fault_diagnostic_var.get())
        self.assertIn('current SET / fault register SET', self.app.fault_diagnostic_var.get())
        confirm,warn=self.clear();confirm.assert_called_once();warn.assert_not_called()
        self.assertEqual(self.queued_writes(),[2044,2049,2052,2050])
    def test_empty_reset_receipts_do_not_cancel_second_reset_or_claim_success(self):
        self.receive(1066,'0X00334428');self.receive(1039,'0X00334428');self.receive(1089,'5')
        self.t.answers.update({2044:'',2049:'',2052:'',2050:'',1088:'3073.000000'})
        self.clear(); self.execute_next()
        self.assertEqual(self.queued_writes(),[2049,2052,2050])
        self.assertNotEqual(self.c.state.value(2044),'OK')
        self.assertEqual(self.c.state.last_error,'')
        for _ in range(40):
            if not self.c._commands:break
            self.execute_next()
        self.assertFalse(self.c._commands)
        self.assertEqual(self.writes(),[2044,2049,2052,2050])
        self.assertTrue(self.c.state.fault_state(7));self.assertTrue(self.c.state.fault_state(10))
        self.assertTrue(self.c.state.fault_active)
        self.assertEqual(self.c.state.raw_values[2052],'')
        with self.c._audit.path.open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
        self.assertEqual([int(r['command_id']) for r in rows if r['direction']=='UNCONFIRMED_WRITE'],[2044,2049,2052,2050])
        self.assertFalse(any(r['direction']=='INVALID_REPLY' and int(r['command_id']) in (2049,2052) for r in rows))
    def test_empty_receipt_does_not_clear_old_fault_before_readback(self):
        self.receive(1066,'0X00334428');self.t.answers[2052]=''
        self.c.submit(2052);self.execute_next()
        self.assertIn(1066,self.c.state.pending_readbacks)
        self.assertIsNone(self.c.state.fault_state(7))
        self.assertEqual(self.c._state.values[1066],int('00334428',16))
        self.assertIn(1066,[r.command_id for r in self.c._commands])
    def test_malformed_reset_receipt_still_cancels_second_reset(self):
        for value in ('NACK reset rejected','BUSY','ERROR 5'):
            with self.subTest(value=value):
                self.c._commands.clear();self.clear();self.t.answers[2044]=value;self.execute_next()
                self.assertEqual(self.queued_writes(),[])
                self.assertIn(value,self.c.state.last_error)
    def test_blank_setter_receipt_waits_for_readback_without_cancelling_next(self):
        self.t.answers[2036]='';self.c.submit(2036,1);self.c.submit(2049);self.execute_next()
        self.assertEqual(self.queued_writes(),[2049])
        self.assertIn(1068,self.c.state.pending_readbacks)
        self.assertEqual(self.c.state.last_error,'')
    def test_required_read_failure_cancels_old_enable_but_keeps_reset(self):
        self.c.submit(2017);self.c.submit(2019,'1 ON');self.c.submit(2048,'CONT');self.c.submit(2049)
        self.receive(1044,'');self.assertEqual(self.queued_writes(),[2049])
        self.receive(1044,'0');self.assertEqual(self.queued_writes(),[2049])
    def test_malformed_required_read_blocks_output(self):
        self.receive(1065,'invalid frequency')
        with self.assertRaises(PermissionError):self.c.submit(2017)
    def test_reset_hv_on_reaches_confirmation_and_only_queues_fault_resets(self):
        self.receive(1021,'1');confirm,warn=self.clear()
        confirm.assert_called_once();warn.assert_not_called()
        self.assertEqual(self.queued_writes(),[2044,2049,2052,2050]);self.assertEqual(self.writes(),[])
    def test_reset_hv_unknown_does_not_require_turning_off_key(self):
        self.receive(1021,'');confirm,warn=self.clear()
        confirm.assert_called_once();warn.assert_not_called();self.assertEqual(self.queued_writes(),[2044,2049,2052,2050])
    def test_reset_hv_stale_with_fresh_link_reaches_confirmation(self):
        self.c._state.updated_at[1021]-=timedelta(seconds=100)
        confirm,warn=self.clear();confirm.assert_called_once();warn.assert_not_called();self.assertEqual(self.queued_writes(),[2044,2049,2052,2050])
    def test_reset_send_time_has_no_hv_off_gate_or_automatic_hv_write(self):
        self.clear();self.receive(1021,'1')
        for cid in (2049,2052):
            reset=next(r for r in self.c._commands if r.command_id==cid)
            self.c._commands.remove(reset);self.c._execute(reset)
        self.assertEqual(self.writes(),[2049,2052]);self.assertIs(self.c.state.high_voltage,True)
    def test_reset_still_checks_live_connection_at_send_time(self):
        self.clear();reset=self.c._commands.popleft()
        self.c._state.last_reply_at-=timedelta(seconds=100);self.c._execute(reset)
        self.assertEqual(self.writes(),[])
    def test_captured_key_on_transition_allows_reset_without_changing_hv(self):
        for cid,value in ((1021,'1'),(1039,'0X00330429'),(1066,'0X00330429'),(1089,'5')):
            self.receive(cid,value)
        self.assertFalse(self.c.state.fault_state(7));self.assertTrue(self.c.state.fault_state(10))
        confirm,warn=self.clear();confirm.assert_called_once();warn.assert_not_called()
        self.assertEqual(self.queued_writes(),[2044,2049,2052,2050]);self.assertEqual(self.writes(),[])
    def test_timeout_cancels_old_writes_recovery_accepts_only_new_requests(self):
        self.c.submit(2049);self.receive(1019,TransportError('Timed out waiting for reply to command 1019'))
        self.assertFalse(self.c.state.connected);self.assertEqual(self.queued_writes(),[])
        self.receive(1000,'Spectra Physics,SASC,1.5.0');self.assertEqual(self.queued_writes(),[])
        confirm,warn=self.clear();confirm.assert_called_once();warn.assert_not_called()
        self.assertEqual(self.queued_writes(),[2044,2049,2052,2050]);self.assertEqual(self.writes(),[])
    def test_clear_with_stale_link_reports_connection_reason(self):
        self.c._state.last_reply_at-=timedelta(seconds=100)
        confirm,warn=self.clear();confirm.assert_not_called();self.assertIn('recent controller readback',warn.call_args.args[1]);self.assertEqual(self.queued_writes(),[])
    def test_reset_confirmation_cancel_sends_nothing(self):
        self.clear(accept=False);self.assertEqual(self.queued_writes(),[]);self.assertEqual(self.writes(),[])
    def test_first_submit_failure_stops_reset_sequence(self):
        with patch.object(self.c,'clear_faults',side_effect=PermissionError('preflight failed')) as submit:self.clear()
        submit.assert_called_once_with()
        self.assertEqual(self.queued_writes(),[])
    def test_fault_diagnostics_do_not_present_stale_bits_as_current(self):
        for cid,val in ((1066,'0X00334428'),(1039,'0X00334428'),(1089,'5')):
            self.receive(cid,val);self.c._state.updated_at[cid]-=timedelta(seconds=100)
        self.sync();self.assertEqual(self.app.fault_diagnostic_var.get().count('unknown/stale'),3)
    def test_fault_controls_fit_1024_by_768(self):
        self.receive(1066,'0X00334428');self.receive(1039,'0X00334428');self.receive(1089,'5')
        self.app.notebook.select(self.app.faults);self.root.update_idletasks()
        for w in self.app._walk_widgets(self.app.faults):
            if w.winfo_ismapped():
                x=w.winfo_rootx()-self.root.winfo_rootx();y=w.winfo_rooty()-self.root.winfo_rooty()
                self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                self.assertLessEqual(x+w.winfo_width(),self.root.winfo_width());self.assertLessEqual(y+w.winfo_height(),self.root.winfo_height())

if __name__=='__main__':unittest.main()

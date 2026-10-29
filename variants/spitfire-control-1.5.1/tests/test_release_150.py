"""1.5.0 PC output transactions over independent loopback UDP Twin Verifier.

Fixtures model protocol outcomes only; no laser, keyswitch, HV physics or 80 MHz
signal is generated. The combined PC order is a new application sequence.
"""
from datetime import timedelta
from pathlib import Path
import csv
import os
import tempfile
import time
import unittest
from test_verifier_140 import VirtualSpitfire, ResponseProfile, CaptureStore, VirtualDeviceServer
from spitfire_twin_verifier.model import DeviceAnswer
from spitfire_control.controller import LaserController, PendingCommand, OUTPUT_MONITOR_QUERY_IDS
from spitfire_control.protocol import Reply
from spitfire_control.transport import UdpTransport, UdpSettings
from test_external_profile import healthy, apply


class OutputTwin(VirtualSpitfire):
    def __init__(self):
        super().__init__(isolated_clients=False)
        self.ignore = set(); self.reject = set(); self.drop = set(); self.lose_request = set()
        self.key_reset_hv = False
        self._shared.values.update({1021:1,1040:3.3,1041:3.1,1042:3.3,1043:3.1,1068:1,1050:1,1051:1,1065:80})
    def _write(self, state, command):
        if command.command_id == 2019:
            if command.argument in self.reject: return 'NACK'
            if command.argument in self.ignore: return ''
        result = super()._write(state, command)
        if self.key_reset_hv and command.command_id == 2050:
            # Explicit scenario injection, not an assertion about firmware logic.
            state.values.update({1021:1,1042:3.3,1043:3.1,1023:0,1066:0})
        return '' if command.command_id >= 2000 else result
    def answer(self, client_key, command, profile=None):
        if command.command_id == 2019 and command.argument in self.lose_request:
            return DeviceAnswer(None, dropped=True, note='injected request loss', effect='not_executed')
        result=super().answer(client_key, command, profile)
        if command.command_id == 2019 and command.argument in self.drop:
            return DeviceAnswer(None, dropped=True, note='injected receipt loss', effect='write_applied')
        return result


class PCOutput150Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.model=OutputTwin(); self.capture=CaptureStore()
        self.server=VirtualDeviceServer('127.0.0.1',0,self.model,self.capture)
        self.server.start(); self.addCleanup(self.server.stop)
        transport=UdpTransport(UdpSettings('127.0.0.1',self.server.local_address[1],'127.0.0.1',0))
        transport.connect()
        self.c=LaserController(transport,timeout=.08,auto_poll=False,pump_mode='external',log_directory=self.temp.name)
        self.addCleanup(self.c.stop)
        healthy(self.c._state)
        for cid in (1021,1042,1043):self.query(cid)
    def tearDown(self):
        folder=os.environ.get('SPITFIRE_EVIDENCE_DIR')
        if folder:self.capture.snapshot().save_jsonl(Path(folder)/(self.id().split('.')[-1]+'.jsonl'))
    def query(self,cid):self.c._execute(PendingCommand(cid,None,'test readback'))
    def step(self):self.c._execute((self.c._urgent or self.c._commands).popleft())
    def drain(self):
        for _ in range(250):
            if not self.c._commands and not self.c._urgent:return
            self.step()
        self.fail('queue did not drain')
    def writes(self):return [(r.command_id,r.argument) for r in self.capture.snapshot().transactions if r.command_id>=2000]
    def status(self):return self.c.pc_output_status.status
    def test_run_waits_for_each_readback_and_sends_only_pc_commands(self):
        self.c.run_pc_outputs();self.step()
        self.assertEqual(self.writes(),[(2019,'2 ON')]);self.assertEqual(self.status(),'pending')
        self.assertEqual([r.command_id for r in self.c._commands],[1046])
        self.step();self.assertEqual(self.writes(),[(2019,'2 ON')])
        self.assertEqual(self.c._commands[-1].argument,'1 ON')
        self.drain()
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 ON')])
        self.assertEqual(self.status(),'confirmed')
        self.assertEqual([self.c.state.pc_output(ch) for ch in (1,2)],['ON','ON'])
    def test_run_does_not_turn_hv_on(self):
        apply(self.c._state,1021,0)
        with self.assertRaises(PermissionError):self.c.run_pc_outputs()
        self.assertEqual(self.writes(),[])
    def test_hv_status_one_is_not_pc_on_or_key_position(self):
        self.assertTrue(self.c.state.high_voltage)
        self.assertFalse(self.c.state.key_interlock)
        self.assertEqual([self.c.state.pc_output(ch) for ch in (1,2)],['OFF','OFF'])
        apply(self.c._state,1039,'0X4000')
        self.assertTrue(self.c.state.high_voltage);self.assertTrue(self.c.state.key_interlock)
        self.assertEqual(self.writes(),[])
    def test_stale_and_missing_voltage_blocks_run(self):
        for cid in (1042,1043):
            self.query(cid);self.c._state.updated_at[cid]-=timedelta(seconds=20)
            with self.assertRaises(PermissionError):self.c.run_pc_outputs()
            self.query(cid);apply(self.c._state,cid,'ERROR')
            with self.assertRaises(PermissionError):self.c.run_pc_outputs()
            self.query(cid)
        self.assertEqual(self.writes(),[])
    def test_zero_voltage_and_key_interlock_block_run(self):
        for cid,value in ((1042,'0'),(1043,'-99'),(1039,'0X4000')):
            before=self.c._state.copy();apply(self.c._state,cid,value)
            with self.assertRaises(PermissionError):self.c.run_pc_outputs()
            self.c._state=before
        self.assertEqual(self.writes(),[])
    def test_existing_fault_and_80mhz_checks_remain_required(self):
        for cid,value in ((1066,'0X2000'),(1065,'0'),(1065,'40'),(1050,'INT'),(1051,'INT'),(1089,'1')):
            before=self.c._state.copy();apply(self.c._state,cid,value)
            with self.assertRaises(PermissionError):self.c.run_pc_outputs()
            self.c._state=before
        self.assertEqual(self.writes(),[])
    def test_partial_channel_state_requires_stop_first(self):
        apply(self.c._state,1045,'DELAY 1 ON BWD ENA 0')
        with self.assertRaises(PermissionError):self.c.run_pc_outputs()
        self.c.stop_pc_outputs();self.drain();self.assertEqual(self.status(),'confirmed')
    def test_duplicate_run_and_interleaved_settings_are_rejected(self):
        self.c.run_pc_outputs()
        for action in (self.c.run_pc_outputs,self.c.clear_faults,lambda:self.c.submit(2025,'3.2')):
            with self.assertRaises((ValueError,PermissionError)):action()
        self.drain();self.assertEqual(len(self.writes()),2)
    def test_existing_pending_write_blocks_run(self):
        self.c.submit(2025,'3.2')
        with self.assertRaises(ValueError):self.c.run_pc_outputs()
    def test_first_channel_ignored_receipt_aborts_and_turns_both_off(self):
        self.model.ignore.add('2 ON');self.c.run_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'failed');self.assertIn('both PC OFF',self.c.pc_output_status.detail)
    def test_second_channel_nack_cleans_up_first_channel(self):
        self.model.reject.add('1 ON');self.c.run_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 ON'),(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'failed')
    def test_run_request_loss_never_replays_on(self):
        self.model.lose_request.add('2 ON');self.c.run_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'failed')
    def test_run_receipt_loss_cleans_up_applied_on_without_retry(self):
        self.model.drop.add('2 ON');self.c.run_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'failed')
    def test_stop_sends_both_even_if_first_is_nack(self):
        self.model.reject.add('1 OFF');self.c.stop_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'unverified')
    def test_stop_sends_both_even_if_first_times_out(self):
        self.model.drop.add('1 OFF');self.c.stop_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'unverified')
    def test_stop_works_with_unknown_link_hv_and_faults(self):
        self.c._state.connected=False;self.c._state.invalid_ids.update(self.c._state.values)
        self.c.stop_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'confirmed')
    def test_stop_cancels_unsent_run_and_repeated_stop_does_not_duplicate(self):
        self.c.run_pc_outputs();self.c.stop_pc_outputs();self.c.stop_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'confirmed')
    def test_stop_between_on_steps_cancels_remaining_on(self):
        self.c.run_pc_outputs();self.step();self.step();self.c.stop_pc_outputs();self.drain()
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'confirmed')
    def test_hv_off_interrupts_run_and_requests_pc_cleanup(self):
        self.c.run_pc_outputs();self.step();self.c.submit(2016);self.drain()
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2016,''),(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'failed')
    def test_send_time_hv_change_cancels_run(self):
        self.c.run_pc_outputs();apply(self.c._state,1021,0);self.drain()
        self.assertEqual(self.writes(),[(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertEqual(self.status(),'failed')
    def test_fault_before_final_confirmation_cleans_up_both_outputs(self):
        self.c.run_pc_outputs();self.step();self.step();self.step()
        apply(self.c._state,1066,'0X2000');self.drain()
        self.assertEqual(self.status(),'failed')
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 ON'),(2019,'1 OFF'),(2019,'2 OFF')])
    def test_watch_deadline_aborts_without_next_on(self):
        self.c.run_pc_outputs();self.step()
        with self.c._condition:
            self.c._expire_watches(float('inf'));self.c._advance_pc_output_locked()
        self.drain();self.assertNotIn((2019,'1 ON'),self.writes())
        self.assertEqual(self.status(),'failed')
    def test_disconnect_does_not_claim_off_or_resume_run(self):
        self.c.run_pc_outputs();self.step();self.c.stop()
        self.assertEqual(self.status(),'unverified')
        self.assertEqual(self.writes(),[(2019,'2 ON')])
    def test_invalid_channel_readback_aborts_run(self):
        self.model.profile.overrides[1046]='';self.c.run_pc_outputs();self.drain()
        self.assertNotIn((2019,'1 ON'),self.writes());self.assertEqual(self.status(),'unverified')
    def test_reset_hv_transition_never_runs_pc_and_records_before_after(self):
        self.model._shared.values.update({1021:0,1042:0,1043:0})
        for cid in OUTPUT_MONITOR_QUERY_IDS:self.query(cid)
        self.model.key_reset_hv=True
        tokens=self.c.clear_faults();self.drain()
        # Advance only the test's observation barrier; production uses 6 seconds.
        self.c._watch[tokens[-1]].not_before=0
        for cid in tuple(self.c._watch[tokens[-1]].pending):self.query(cid)
        self.assertEqual([cid for cid,arg in self.writes()],[2044,2049,2052,2050])
        self.assertTrue(self.c.state.high_voltage)
        self.assertEqual([self.c.state.pc_output(ch) for ch in (1,2)],['OFF','OFF'])
        with self.c._audit.path.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
        self.assertEqual(len([r for r in rows if r['direction']=='RESET_BEFORE']),1)
        self.assertEqual(len([r for r in rows if r['direction']=='RESET_AFTER']),1)
        self.assertIn('"raw": "0"',next(r['text'] for r in rows if r['direction']=='RESET_BEFORE'))
    def test_finished_status_does_not_mask_later_stale_readbacks(self):
        self.c.run_pc_outputs();self.drain()
        self.c._state.updated_at[1045]-=timedelta(seconds=20)
        self.assertIsNone(self.c.state.pc_output(1))
        self.assertEqual(self.status(),'confirmed') # historical command result, separate from live state

if __name__=='__main__':unittest.main()

"""Independent Twin Verifier over real localhost UDP. No instrument routes."""
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'verification'/'verifier'/'src'))
from spitfire_twin_verifier.model import VirtualSpitfire, ResponseProfile
from spitfire_twin_verifier.records import CaptureStore
from spitfire_twin_verifier.server import VirtualDeviceServer
from spitfire_control.commands import engineering_argument
from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.protocol import Reply
from spitfire_control.transport import UdpTransport, UdpSettings
from test_external_profile import healthy


class CapturedResetTwin(VirtualSpitfire):
    """Replay the observed delayed MAIN transition; not a firmware model."""
    def __init__(self):
        super().__init__(isolated_clients=False)
        self.reset_at = None
        self.profile = ResponseProfile(overrides={cid:'' for cid in (2044,2049,2052,2050)})
        self._shared.values[1089]=5
        self._shared.values[1066]=0x4000  # KEY fault source persists.
    def _write(self,state,command):
        value = super()._write(state,command)
        if command.command_id == 2050:self.reset_at=time.monotonic()
        state.values[1066]=0x4000
        return value
    def _query_value(self,state,cid):
        if cid == 1089:
            return '4' if self.reset_at and time.monotonic()-self.reset_at>=3.26 else '5'
        return super()._query_value(state,cid)


class Verifier140Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.model=VirtualSpitfire(isolated_clients=False)
        self.capture=CaptureStore()
        self.server=VirtualDeviceServer('127.0.0.1',0,self.model,self.capture)
        self.server.start();self.addCleanup(self.server.stop)
        self.transport=UdpTransport(UdpSettings('127.0.0.1',self.server.local_address[1],'127.0.0.1',0))
        self.transport.connect()
        self.c=LaserController(self.transport,timeout=.18,auto_poll=False,log_directory=self.temp.name)
        healthy(self.c._state);self.addCleanup(self.c.stop)
    def tearDown(self):
        destination=os.environ.get('SPITFIRE_EVIDENCE_DIR')
        if destination:self.capture.snapshot().save_jsonl(Path(destination)/(self.id().split('.')[-1]+'.jsonl'))
    def drain(self):
        for _ in range(250):
            if not self.c._commands and not self.c._urgent:return
            self.c._execute((self.c._urgent or self.c._commands).popleft())
        self.fail('queue did not drain')
    def result(self, token):return next(r for r in self.c.command_results if r.token==token)
    def writes(self):return [t.command_id for t in self.capture.snapshot().transactions if t.command_id>=2000]
    def test_all_recovered_queries_are_exchanged(self):
        from spitfire_control.commands import COMMANDS
        for cid in COMMANDS:
            if cid<2000:
                with self.subTest(cid=cid):
                    self.c._execute(PendingCommand(cid,None,'query matrix'))
                    self.assertIn(cid,self.c.state.raw_values)
        self.assertEqual(len([t for t in self.capture.snapshot().transactions if t.command_id<2000]),90)
    def test_setters_confirmed_only_by_target_readbacks(self):
        cases=((2003,'17'),(2004,'1100'),(2007,'120'),(2008,'1'),(2014,'100'),
               (2020,'2'),(2021,'26'),(2024,'0'),(2025,'3300'),(2026,'3100'),
               (2029,'0'),(2030,'EXT'),(2031,'EXT'),(2032,'10'),(2035,'0'),
               (2036,'1'),(2047,'0'),(2048,'COUNT 1'),(2051,'1'),(2053,'0'))
        self.model.profile.overrides.update({cid:'' for cid,arg in cases})
        for cid,arg in cases:
            with self.subTest(cid=cid):
                token=self.c.submit(cid,engineering_argument(cid,arg));self.drain()
                self.assertEqual(self.result(token).status,'confirmed',self.result(token))
        self.assertEqual(self.c.state.value(1009),17)
        self.assertEqual(self.c.state.value(1040),3300)
    def test_service_numeric_formatting_does_not_cancel_commit(self):
        self.model.profile.overrides[2038]=''
        setter=self.c.submit(2038,'45.00');commit=self.c.submit(2045);self.drain()
        self.assertEqual(self.result(setter).status,'confirmed')
        self.assertEqual(self.writes(),[2038,2045])
        self.assertEqual(self.result(commit).status,'unverified')
    def test_service_malformed_readback_does_not_confirm(self):
        for raw in ('4_5','45 units','NaN','Infinity','45 unexpected'):
            with self.subTest(raw=raw):
                self.model.profile.overrides[1071]=raw
                setter=self.c.submit(2038,'45.00');commit=self.c.submit(2045);self.drain()
                self.assertEqual(self.result(setter).status,'mismatch')
                self.assertEqual(self.result(commit).status,'cancelled')
    def test_every_delay_channel_value_and_flags_then_restore(self):
        for ch in range(1,6):
            for setting in ('85.82','ON','NBWD','NENA','OFF','BWD','ENA','0'):
                with self.subTest(channel=ch,setting=setting):
                    self.model.profile.overrides[2019]=''
                    token=self.c.submit(2019,f'{ch} {setting}');self.drain()
                    self.assertEqual(self.result(token).status,'confirmed',self.result(token))
            delay=self.c.state.delays[ch]
            self.assertEqual((delay.value,delay.switch,delay.bwd,delay.enable),(0,'OFF','BWD','ENA'))
        raw=next(t.response_hex for t in self.capture.snapshot().transactions if t.command_id==1045)
        self.assertIn(b'<1045> DELAY 1',bytes.fromhex(raw))
    def test_ack_does_not_hide_mismatched_or_missing_readback(self):
        for response in ('INT','','ERROR:UNAVAILABLE'):
            with self.subTest(response=response):
                self.model.profile.overrides[1050]=response
                token=self.c.submit(2030,'EXT');later=self.c.submit(2031,'EXT');self.drain()
                self.assertIn(self.result(token).status,('mismatch','unverified'))
                self.assertEqual(self.result(later).status,'cancelled')
    def test_request_loss_and_reply_loss_never_replay_writes(self):
        for attr in ('drop_ids','request_drop_ids'):
            with self.subTest(kind=attr):
                self.model.profile=ResponseProfile(**{attr:{2030}})
                healthy(self.c._state)
                before=len(self.writes());a=self.c.submit(2030,'EXT');b=self.c.submit(2031,'EXT');self.drain()
                self.assertEqual(self.writes()[before:],[2030])
                self.assertEqual(self.result(a).status,'timeout')
                self.assertEqual(self.result(b).status,'cancelled')
                self.c._execute(PendingCommand(1000,None,'recovery'))
                self.assertEqual(self.writes()[before:],[2030])
    def test_paced_mixed_settings_repeat_without_queue_or_watch_growth(self):
        cases=((2030,'EXT'),(2031,'EXT'),(2025,'3.3'),(2026,'3.1'),(2021,'26'),(2020,'2'))
        self.model.profile.overrides.update({cid:'' for cid,arg in cases})
        from spitfire_control.commands import readback_ids
        for cid,arg in cases:
            for query in (cid,)+readback_ids(cid,arg):self.model.profile.delay_ms[query]=40
        for cycle in range(20):
            for cid,arg in cases:
                token=self.c.submit(cid,arg);self.drain()
                self.assertEqual(self.result(token).status,'confirmed')
                self.assertFalse(self.c._watch)
        self.assertEqual(len(self.writes()),120)
        self.assertFalse(self.c._commands)

    def test_external_full_reset_order_with_persistent_faults(self):
        self.c._pump_mode='external';self.c._state.pump_mode='external'
        self.model.profile.overrides.update({cid:'' for cid in (2044,2049,2052,2050)})
        self.model.profile.overrides.update({1089:'5',1066:'0X00004000'})
        self.c.clear_faults();self.drain()
        self.assertEqual(self.writes(),[2044,2049,2052,2050])
        self.assertEqual(self.c.state.value(1089),5)
        self.assertTrue(self.c.state.fault_state(10))
        self.assertEqual(self.c.state.value(1066),0x4000)
        self.assertFalse(any(r.status=='confirmed' for r in self.c.command_results))
    def test_off_cancels_queued_reset_and_stays_urgent(self):
        tokens=self.c.clear_faults();off=self.c.submit(2016);self.drain()
        self.assertEqual(self.writes(),[2016])
        self.assertTrue(all(self.result(t).status=='cancelled' for t in tokens))
        self.assertEqual(self.result(off).status,'confirmed')
    def test_delayed_main_transition_is_rechecked_with_autopoll_off(self):
        self.c.stop();self.server.stop()
        model=CapturedResetTwin();self.server=VirtualDeviceServer('127.0.0.1',0,model,self.capture)
        self.server.start();self.addCleanup(self.server.stop)
        t=UdpTransport(UdpSettings('127.0.0.1',self.server.local_address[1],'127.0.0.1',0))
        self.c=LaserController(t,timeout=.2,auto_poll=False,log_directory=self.temp.name)
        self.addCleanup(self.c.stop);self.c.start()
        deadline=time.monotonic()+2
        while not self.c.state.connected and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(self.c.state.connected)
        tokens=self.c.clear_faults()
        deadline=time.monotonic()+9
        while time.monotonic()<deadline:
            if self.result(tokens[-1]).status=='observed':break
            time.sleep(.02)
        self.assertEqual(self.result(tokens[-1]).status,'observed',self.result(tokens[-1]))
        self.assertEqual(self.c.state.value(1089),4)
        self.assertEqual(self.c.state.value(1066),0x4000)
        self.assertEqual(self.writes(),[2044,2049,2052,2050])
        samples=[t.response_value for t in self.capture.snapshot().transactions if t.command_id==1089]
        self.assertIn('5',samples);self.assertIn('4',samples)


if __name__=='__main__':unittest.main()

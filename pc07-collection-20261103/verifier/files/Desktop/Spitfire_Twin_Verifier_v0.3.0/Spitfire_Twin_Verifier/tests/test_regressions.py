"""Regression cases reproduced during the 0.1.0 code review."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from spitfire_twin_verifier.compare import compare_transactions
from spitfire_twin_verifier.model import VirtualSpitfire, ResponseProfile
from spitfire_twin_verifier.protocol import COMMAND_HEADER, ProtocolError, decode_commands, decode_replies, encode_commands, encode_replies
from spitfire_twin_verifier.records import CaptureStore
from spitfire_twin_verifier.report import write_report
from spitfire_twin_verifier.server import VirtualDeviceServer
from test_compare import tx

def cmd(line):
    return decode_commands(encode_commands([line]))[0]

def add(store, item):
    fields = asdict(item)
    fields.pop('sequence')
    fields.pop('session_id')
    return store.add_transaction(**fields)

def wait_for(predicate, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('condition did not become true')

class ComparisonRegressions(unittest.TestCase):
    def compare(self, left, right):
        return compare_transactions([left, right], 'XP', 'PY')

    def test_poll_values_are_compared(self):
        result = self.compare(tx(1,'XP',1031,'ECU:HUM?',response='34'), tx(2,'PY',1031,'ECU:HUM?',response='99'))
        self.assertEqual(result.verdict, 'DIFFERENT')
        self.assertEqual(result.rows[0].status, 'RESPONSE_DIFF')

    def test_poll_response_loss_is_not_hidden(self):
        result = self.compare(tx(1,'XP',1031,'ECU:HUM?',response='34'),
                              replace(tx(2,'PY',1031,'ECU:HUM?'), response_value=None, response_hex='', status='DROPPED'))
        self.assertNotEqual(result.verdict, 'MATCH')
        self.assertEqual(result.transport_health, 'FAULT_OBSERVED')

    def test_poll_state_transitions_survive_compression(self):
        items = [tx(i,'XP',1013,'EMP:STB?',response=v) for i,v in enumerate(['0','0','1','1','0'],1)]
        items += [tx(i,'PY',1013,'EMP:STB?',response=v) for i,v in enumerate(['0','1','0'],6)]
        r=compare_transactions(items,'XP','PY')
        self.assertEqual(r.verdict,'MATCH')
        self.assertEqual(len(r.rows),3)

    def test_poll_bad_command_is_not_hidden(self):
        result=self.compare(tx(1,'XP',1031,'ECU:HUM?',response='34'),tx(2,'PY',1031,'WRONG?',response='34'))
        self.assertEqual(result.verdict,'DIFFERENT')

    def test_reply_header_difference_is_detected(self):
        a=tx(1,'XP',1000,'*idn?',response='ID')
        b=replace(tx(2,'PY',1000,'*idn?',response='ID'),response_hex=b'Spectra-Physics:BROKEN_ECLIPSE:<1000>ID\n'.hex())
        self.assertEqual(self.compare(a,b).framing_verdict,'DIFFERENT')

    def test_line_endings_are_compared_separately(self):
        a=tx(1,'XP',1000,'*idn?',response='ID')
        b=replace(tx(2,'PY',1000,'*idn?',response='ID'),response_hex=encode_replies([(1000,'ID')],line_ending='\r\n').hex())
        r=self.compare(a,b)
        self.assertEqual(r.content_verdict,'MATCH')
        self.assertEqual(r.framing_verdict,'DIFFERENT')
        self.assertEqual(r.verdict,'DIFFERENT')

    def test_identical_send_errors_do_not_pass(self):
        r=self.compare(replace(tx(1,'XP',1000,'*idn?'),status='SEND_ERROR'),replace(tx(2,'PY',1000,'*idn?'),status='SEND_ERROR'))
        self.assertEqual(r.verdict,'ERROR')

    def test_identical_injected_fault_needs_observation(self):
        r=self.compare(tx(1,'XP',1000,'*idn?',response='ERROR:INJECTED'),tx(2,'PY',1000,'*idn?',response='ERROR:INJECTED'))
        self.assertEqual(r.verdict,'OBSERVATION_REQUIRED')
        self.assertEqual(r.content_verdict,'MATCH')

    def test_missing_raw_evidence_is_unverified(self):
        r=self.compare(replace(tx(1,'XP',1000,'*idn?'),request_hex='',response_hex=''),replace(tx(2,'PY',1000,'*idn?'),request_hex='',response_hex=''))
        self.assertEqual(r.verdict,'UNVERIFIED')

    def test_numeric_meaning_does_not_hide_raw_difference(self):
        r=self.compare(tx(1,'XP',2004,'EMP:QSW:PRF 125.00','125.00'),tx(2,'PY',2004,'EMP:QSW:PRF 125','125'))
        self.assertEqual(r.verdict,'DIFFERENT')
        self.assertEqual(r.semantic_verdict,'MATCH')

    def test_unknown_client_prevents_full_match(self):
        items=[tx(1,'XP',1000,'*idn?'),tx(2,'PY',1000,'*idn?'),tx(3,'OTHER',1000,'*idn?')]
        self.assertEqual(compare_transactions(items,'XP','PY').verdict,'INCOMPLETE')

    def test_same_label_cannot_compare_to_itself(self):
        self.assertEqual(compare_transactions([tx(1,'XP',1000,'*idn?')],'XP','XP').verdict,'ERROR')

    def test_different_scenarios_do_not_match(self):
        r=self.compare(replace(tx(1,'XP',1000,'*idn?'),scenario='A'),replace(tx(2,'PY',1000,'*idn?'),scenario='B'))
        self.assertEqual(r.verdict,'DIFFERENT')

    def test_test_condition_mismatch_is_not_a_match(self):
        r=self.compare(tx(1,'XP',1000,'*idn?'),replace(tx(2,'PY',1000,'*idn?'),profile_json='{"delay_ms":{"1000":10}}'))
        self.assertEqual(r.rows[0].status,'TEST_CONDITION_DIFF')

    def test_pending_response_makes_snapshot_incomplete(self):
        store=CaptureStore()
        add(store,tx(1,'XP',1000,'*idn?'));add(store,tx(2,'PY',1000,'*idn?'))
        store.begin_pending(3,command_ids=[2005])
        r=compare_transactions(store.snapshot(),'XP','PY')
        self.assertEqual(r.verdict,'INCOMPLETE')
        self.assertEqual(r.pending_datagrams,1)

    def test_protocol_diagnostic_affects_verdict(self):
        store=CaptureStore()
        add(store,tx(1,'XP',1000,'*idn?'));add(store,tx(2,'PY',1000,'*idn?'))
        store.message('PROTOCOL','bad header',client_label='PY')
        self.assertEqual(compare_transactions(store.snapshot(),'XP','PY').verdict,'ERROR')

    def test_unmodelled_writes_are_not_certified(self):
        r=self.compare(replace(tx(1,'XP',2013,'HED:MOTOR:STOP'),modelled=False),replace(tx(2,'PY',2013,'HED:MOTOR:STOP'),modelled=False))
        self.assertEqual(r.verdict,'UNVERIFIED')

class ModelRegressions(unittest.TestCase):
    def setUp(self): self.model=VirtualSpitfire()
    def ask(self,line): return self.model.answer('XP',cmd(line))

    def test_id_text_mismatch_cannot_switch_on(self):
        a=self.ask('[2005]EMP:OFF')
        self.assertEqual(a.validation,'ID_TEXT_MISMATCH')
        self.assertEqual(self.ask('[1013]EMP:STB?').value,'0')

    def test_unknown_query_text_is_rejected(self):
        self.assertEqual(self.ask('[1010]WRONG').validation,'ID_TEXT_MISMATCH')

    def test_numeric_argument_is_required_and_finite(self):
        for value in ['', ' NaN', ' inf', ' abc']:
            self.assertEqual(self.ask('[2004]EMP:QSW:PRF'+value).validation,'INVALID_ARGUMENT')
        self.assertEqual(self.ask('[1010]EMP:QSW:PRF?').value,'100')

    def test_no_argument_command_rejects_extra_argument(self):
        self.assertEqual(self.ask('[2005]EMP:ON unexpected').validation,'INVALID_ARGUMENT')

    def test_motor_speed_aliases_share_state(self):
        self.ask('[2014]HED:MOTOR:SPEED 222')
        self.assertEqual(self.ask('[1018]HED:MOTOR:SPEED?').value,'222')
        self.assertEqual(self.ask('[1060]HED:MOTOR:SPEED?').value,'222')

    def test_bwd_aliases_share_state(self):
        self.ask('[2033]TDG:BWD ON')
        self.assertEqual(self.ask('[1027]TDG:BWD?').value,'1')
        self.assertEqual(self.ask('[1054]TDG:BWD?').value,'1')

    def test_reply_loss_still_executes_write(self):
        self.model.profile.drop_ids.add(2004)
        self.assertTrue(self.ask('[2004]EMP:QSW:PRF 125').dropped)
        self.assertEqual(self.ask('[1010]EMP:QSW:PRF?').value,'125')

    def test_request_loss_does_not_execute_write(self):
        self.model.profile.request_drop_ids.add(2004)
        self.assertTrue(self.ask('[2004]EMP:QSW:PRF 125').dropped)
        self.assertEqual(self.ask('[1010]EMP:QSW:PRF?').value,'100')

    def test_response_override_does_not_skip_write(self):
        self.model.profile.overrides[2004]='CUSTOM_ACK'
        self.assertEqual(self.ask('[2004]EMP:QSW:PRF 125').value,'CUSTOM_ACK')
        self.assertEqual(self.ask('[1010]EMP:QSW:PRF?').value,'125')

    def test_delay_snapshot_matches_actual_readback(self):
        self.ask('[2019]TDG:DEL 1 12.5')
        self.ask('[2019]TDG:DEL 1 ON')
        snapshot=self.model.snapshot('XP')
        self.assertEqual(snapshot[1045],self.ask('[1045]TDG:DEL1?').value)
        self.assertEqual(snapshot[1058],snapshot[1045])

    def test_unmodelled_command_is_explicit(self):
        result=self.ask('[2013]HED:MOTOR:STOP')
        self.assertFalse(result.modelled)
        self.assertEqual(result.effect,'unmodelled')

class CaptureReportRegressions(unittest.TestCase):
    def setUp(self):
        self.store=CaptureStore()
        add(self.store,tx(1,'XP',1000,'*idn?'))
        add(self.store,tx(2,'PY',1000,'*idn?'))

    def test_report_recomputes_a_stale_comparison(self):
        stale=compare_transactions(self.store.snapshot(),'XP','PY')
        add(self.store,tx(3,'PY',2005,'EMP:ON'))
        with tempfile.TemporaryDirectory() as root:
            path=write_report(Path(root),stale,self.store)
            report=json.loads((path/'report.json').read_text())
            records=[json.loads(line) for line in (path/'capture.jsonl').read_text().splitlines()]
            self.assertEqual(report['comparison']['verdict'],'DIFFERENT')
            self.assertEqual(report['comparison']['python_total'],2)
            self.assertEqual(sum(x['type']=='transaction' for x in records),3)

    def test_report_uses_one_snapshot_after_capture_changes(self):
        frozen=self.store.snapshot()
        result=compare_transactions(frozen,'XP','PY')
        add(self.store,tx(3,'PY',2005,'EMP:ON'))
        with tempfile.TemporaryDirectory() as root:
            path=write_report(Path(root),result,frozen)
            report=json.loads((path/'report.json').read_text())
            records=[json.loads(line) for line in (path/'capture.jsonl').read_text().splitlines()]
            self.assertEqual(report['comparison']['verdict'],'MATCH')
            self.assertEqual(sum(x['type']=='transaction' for x in records),2)

    def test_old_session_transaction_is_rejected(self):
        old=self.store.session_id
        self.store.clear()
        fields=asdict(tx(3,'PY',2005,'EMP:ON'));fields.pop('sequence');fields['session_id']=old
        self.assertIsNone(self.store.add_transaction(**fields))
        self.assertEqual(self.store.transactions(),[])

    def test_profile_snapshot_is_not_a_live_reference(self):
        data={'drop_ids':[1000]}
        self.store.set_metadata(response_profile=data)
        snap=self.store.snapshot()
        data['drop_ids'].append(1001)
        self.assertEqual(snap.metadata['response_profile']['drop_ids'],[1000])

    def test_gui_observations_remain_separate(self):
        self.store.set_metadata(ui_observations=[{'original':'1250 Hz','python':'125 Hz','expected':'1250 Hz'}])
        r=compare_transactions(self.store.snapshot(),'XP','PY')
        self.assertEqual(r.content_verdict,'MATCH')
        self.assertEqual(r.gui_verdict,'MANUAL_DIFFERENT')

    def test_shared_state_comparison_is_unverified(self):
        self.store.set_metadata(isolated_client_state=False)
        self.assertEqual(compare_transactions(self.store.snapshot(),'XP','PY').verdict,'UNVERIFIED')

class UdpRegressions(unittest.TestCase):
    def setUp(self):
        self.capture=CaptureStore();self.device=VirtualSpitfire()
        self.clients=[]
        for _ in range(2):
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(2)
            self.clients.append(sock)
        labels={f'127.0.0.1:{s.getsockname()[1]}':label for s,label in zip(self.clients,['XP','PY'])}
        self.server=VirtualDeviceServer('127.0.0.1',0,self.device,self.capture,labels)
        self.server.start()
    def tearDown(self):
        self.server.stop()
        for sock in self.clients:sock.close()
    def send(self,index,line):
        self.clients[index].sendto(encode_commands([line]),self.server.local_address)
    def recv(self,index):
        return decode_replies(self.clients[index].recvfrom(65535)[0])

    def test_delayed_client_does_not_block_other_and_latency_is_honest(self):
        self.device.profile.delay_ms[1010]=700
        self.send(0,'[1010]EMP:QSW:PRF?')
        wait_for(lambda:len(self.capture.snapshot().pending)==1)
        start=time.perf_counter();self.send(1,'[1000]*idn?');self.recv(1)
        self.assertLess(time.perf_counter()-start,.4)
        self.recv(0)
        wait_for(lambda:len(self.capture.transactions())==2)
        query=next(x for x in self.capture.transactions() if x.command_id==1010)
        self.assertGreaterEqual(query.latency_ms,690)
        self.assertLess(query.processing_ms,400)

    def test_same_client_response_order_and_wait_are_recorded(self):
        self.device.profile.delay_ms[1010]=200
        self.send(0,'[1010]EMP:QSW:PRF?');self.send(0,'[1000]*idn?')
        self.assertEqual(self.recv(0)[0].command_id,1010)
        self.assertEqual(self.recv(0)[0].command_id,1000)
        wait_for(lambda:len(self.capture.transactions())==2)
        query=next(x for x in self.capture.transactions() if x.command_id==1000)
        self.assertGreater(query.latency_ms,120)

    def test_reset_cancels_old_delayed_evidence(self):
        self.device.profile.delay_ms[1010]=200
        self.send(0,'[1010]EMP:QSW:PRF?')
        wait_for(lambda:bool(self.capture.snapshot().pending))
        old=self.capture.session_id;self.server.reset_session()
        self.assertNotEqual(old,self.capture.session_id)
        self.clients[0].settimeout(.3)
        with self.assertRaises(socket.timeout):self.clients[0].recvfrom(4096)
        self.assertEqual(self.capture.transactions(),[])
        self.send(0,'[1000]*idn?');self.recv(0)
        wait_for(lambda:len(self.capture.transactions())==1)
        self.assertEqual(self.capture.transactions()[0].command_id,1000)

    def test_stop_does_not_wait_for_sixty_second_injection(self):
        self.device.profile.delay_ms[1010]=60000
        self.send(0,'[1010]EMP:QSW:PRF?')
        wait_for(lambda:bool(self.capture.snapshot().pending))
        start=time.perf_counter();self.server.stop()
        self.assertLess(time.perf_counter()-start,.5)
        self.assertEqual(self.capture.transactions()[0].status,'STOPPED')

    def test_profile_is_frozen_until_delayed_reply(self):
        profile=self.device.get_profile();profile.delay_ms[1010]=200;profile.overrides[1010]='125'
        self.server.set_profile(profile)
        self.send(0,'[1010]EMP:QSW:PRF?');wait_for(lambda:bool(self.capture.snapshot().pending))
        later=ResponseProfile(malformed_reply_header=True)
        self.server.set_profile(later)
        self.assertEqual(self.recv(0)[0].value,'125')
        wait_for(lambda:bool(self.capture.transactions()))
        item=self.capture.transactions()[0]
        self.assertFalse(json.loads(item.profile_json)['malformed_reply_header'])
        self.assertEqual(json.loads(item.profile_json)['overrides']['1010'],'125')

    def test_real_malformed_packet_invalidates_comparison(self):
        for i in range(2):self.send(i,'[1000]*idn?');self.recv(i)
        self.clients[1].sendto(b'INVALID HEADER',self.server.local_address)
        wait_for(lambda:any(x.level=='PROTOCOL' for x in self.capture.messages()))
        self.assertEqual(compare_transactions(self.capture.snapshot(),'XP','PY').verdict,'ERROR')

    def test_reconnect_keeps_logical_client_state(self):
        self.send(0,'[2004]EMP:QSW:PRF 125');self.recv(0)
        new=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);new.bind(('127.0.0.1',0));new.settimeout(1)
        self.clients.append(new)
        self.server.client_labels[f'127.0.0.1:{new.getsockname()[1]}']='XP'
        self.send(2,'[1010]EMP:QSW:PRF?')
        self.assertEqual(self.recv(2)[0].value,'125')

    def test_reply_loss_roundtrip_readback_has_changed(self):
        self.device.profile.drop_ids.add(2004)
        self.send(0,'[2004]EMP:QSW:PRF 125')
        wait_for(lambda:bool(self.capture.transactions()))
        self.send(0,'[1010]EMP:QSW:PRF?')
        self.assertEqual(self.recv(0)[0].value,'125')

class ProtocolRegressions(unittest.TestCase):
    def test_reply_header_must_be_exact(self):
        for data in [b'Wrong:REPLY_ECLIPSE:<1000>ID\n',b'Spectra-Physics:REPLY_ECLIPSE_EXTRA:<1000>ID\n']:
            with self.assertRaises(ProtocolError):decode_replies(data)
    def test_control_characters_cannot_split_fake_commands(self):
        with self.assertRaises(ProtocolError):decode_commands(COMMAND_HEADER+b'[1000]*idn?\v[2005]EMP:ON\n')

if __name__=='__main__':unittest.main()

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from spitfire_twin_verifier.evidence import EvidenceError, assess_reactions, load_capture
from spitfire_twin_verifier.protocol import encode_commands, encode_replies
from spitfire_twin_verifier.records import CaptureSnapshot, Transaction


def item(sequence=1, cid=1010, time_ms=0, **changes):
    base = 'EMP:QSW:PRF?' if cid == 1010 else 'TDG:HV:OFF'
    command = f'[{cid}]{base}'
    result = Transaction(sequence=sequence, datagram_sequence=sequence,
        timestamp_utc='2026-10-27T00:00:00+00:00', client_key='left', client_label='left',
        source_ip='127.0.0.1', source_port=12345, command_index=1, command_id=cid,
        command=base, base=base, argument='', request_hex=encode_commands([command]).hex(),
        response_value='0', response_hex=encode_replies([(cid, '0')]).hex(), latency_ms=0,
        status='REPLIED', session_id='test', scenario='fault', scenario_time_ms=time_ms,
        effect='query' if cid < 2000 else 'write_applied')
    return replace(result, **changes)


def snapshot(*items, **kwargs):
    return CaptureSnapshot('test', '2026-10-27T00:00:01+00:00', items, (), **kwargs)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'capture.jsonl'
        self.addCleanup(self.tmp.cleanup)

    def test_roundtrip(self):
        original = snapshot(item(), item(2, 2016, 20))
        original.save_jsonl(self.path)
        self.assertEqual(load_capture(self.path), original)

    def test_truncated_file_rejected(self):
        snapshot(item()).save_jsonl(self.path)
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaises(EvidenceError):
            load_capture(self.path)

    def test_duplicate_and_unknown_fields_rejected(self):
        snapshot(item()).save_jsonl(self.path)
        data = self.path.read_text()
        self.path.write_text(data.replace('"type": "session"', '"type": "session", "type": "session"'))
        with self.assertRaises(EvidenceError):
            load_capture(self.path)
        self.path.write_text(data.replace('"type": "transaction"', '"type": "transaction", "evil": 1'))
        with self.assertRaises(EvidenceError):
            load_capture(self.path)

    def test_nan_and_bad_hex_rejected(self):
        snapshot(item(latency_ms=float('nan'))).save_jsonl(self.path)
        with self.assertRaises(EvidenceError):
            load_capture(self.path)
        snapshot(item(request_hex='xyz')).save_jsonl(self.path)
        with self.assertRaises(EvidenceError):
            load_capture(self.path)

    def test_missing_sequence_rejected(self):
        snapshot(item(2)).save_jsonl(self.path)
        with self.assertRaises(EvidenceError):
            load_capture(self.path)

    def test_wrong_types_and_session_rejected(self):
        for changes in ({'command_id':True}, {'modelled':'yes'}, {'session_id':'other'}, {'scenario_time_ms':-1}):
            snapshot(item(**changes)).save_jsonl(self.path)
            with self.assertRaises(EvidenceError):
                load_capture(self.path)

    @staticmethod
    def rules(kind='require'):
        return [{'kind':kind, 'command_id':2016, 'after_ms':0, 'before_ms':100}]

    def test_missing_client_and_missing_time_never_pass(self):
        result = assess_reactions(snapshot(item()), self.rules('forbid'), 'absent')
        self.assertEqual(result['verdict'], 'UNVERIFIED')
        result = assess_reactions(snapshot(item(scenario_time_ms=None)), self.rules('forbid'), 'left')
        self.assertEqual(result['verdict'], 'UNVERIFIED')

    def test_full_window_required_even_when_command_observed(self):
        result = assess_reactions(snapshot(item(1,2016,20)), self.rules(), 'left')
        self.assertEqual(result['verdict'], 'INCOMPLETE')

    def test_mixed_missing_or_reversed_time_never_passes(self):
        mixed=snapshot(item(),item(2,2016,None),item(3,time_ms=100))
        self.assertEqual(assess_reactions(mixed,self.rules('forbid'),'left')['verdict'],'UNVERIFIED')
        reversed_times=snapshot(item(),item(2,time_ms=100),item(3,time_ms=20))
        self.assertEqual(assess_reactions(reversed_times,self.rules('forbid'),'left')['verdict'],'UNVERIFIED')
        with self.assertRaises(EvidenceError):
            assess_reactions(snapshot(item(time_ms=float('nan'))),self.rules('forbid'),'left')

    def test_require_and_forbid(self):
        captured = snapshot(item(), item(2,2016,20), item(3,time_ms=100))
        self.assertEqual(assess_reactions(captured,self.rules(),'left')['verdict'],'PASS')
        self.assertEqual(assess_reactions(captured,self.rules('forbid'),'left')['verdict'],'FAIL')

    def test_request_loss_excluded_reply_loss_counted(self):
        captured = snapshot(item(),item(2,2016,20,status='DROPPED',effect='not_executed'),item(3,time_ms=100))
        self.assertEqual(assess_reactions(captured,self.rules(),'left')['verdict'],'FAIL')
        captured = snapshot(item(),item(2,2016,20,status='DROPPED'),item(3,time_ms=100))
        self.assertEqual(assess_reactions(captured,self.rules(),'left')['verdict'],'PASS')

    def test_unmodelled_and_pending_do_not_pass(self):
        captured=snapshot(item(),item(2,2016,20,modelled=False),item(3,time_ms=100))
        self.assertEqual(assess_reactions(captured,self.rules(),'left')['verdict'],'UNVERIFIED')
        captured=snapshot(item(),item(2,2016,20),item(3,time_ms=100),pending=({'command_ids':[1010]},))
        self.assertEqual(assess_reactions(captured,self.rules(),'left')['verdict'],'INCOMPLETE')

    def test_rule_validation(self):
        for rules in ([],[{'kind':'forbid'}],[dict(self.rules()[0],before_ms=float('inf'))],
                      [dict(self.rules()[0],command_id=True)],[dict(self.rules()[0],unknown=1)]):
            with self.assertRaises(EvidenceError):
                assess_reactions(snapshot(item()),rules,'left')

"""Independent 0.3.0 review: prevent successful exits and semantic false passes."""
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from spitfire_twin_verifier.cli import main
from spitfire_twin_verifier.compare import compare_transactions
from spitfire_twin_verifier.model import VirtualSpitfire
from spitfire_twin_verifier.protocol import decode_commands, encode_commands
from spitfire_twin_verifier.records import CaptureStore
from spitfire_twin_verifier.server import VirtualDeviceServer
from test_compare import tx


def command(line):
    return decode_commands(encode_commands([line]))[0]


class IndependentReview030Tests(unittest.TestCase):
    def test_reset_and_clear_noops_are_not_reported_as_modelled(self):
        model = VirtualSpitfire()
        for line in ('[2050]RESET', '[2055]CLEAR'):
            with self.subTest(line=line):
                answer = model.answer('XP', command(line))
                self.assertFalse(answer.modelled)
                self.assertEqual(answer.effect, 'unmodelled')

    def test_hex_register_semantics_do_not_use_decimal_exponent_rules(self):
        for cid, name in ((1023, 'TDG:STBH?'), (1039, 'TDG:STBH?'), (1066, 'TDG:STBHFLT?')):
            with self.subTest(cid=cid):
                # Both are valid unsigned hex strings, but different register values.
                # Decimal('1000') == Decimal('1e3') would hide that difference.
                result = compare_transactions([
                    tx(1, 'XP', cid, name, response='1000'),
                    tx(2, 'PY', cid, name, response='1e3'),
                ], 'XP', 'PY')
                self.assertEqual(result.verdict, 'DIFFERENT')
                self.assertEqual(result.semantic_verdict, 'DIFFERENT')

    def test_same_scenario_different_event_phases_do_not_match(self):
        left = replace(tx(1, 'XP', 1000, '*idn?', response='ID'), scenario='fixture', scenario_phase=1)
        right = replace(tx(2, 'PY', 1000, '*idn?', response='ID'), scenario='fixture', scenario_phase=2)
        result = compare_transactions([left, right], 'XP', 'PY')
        self.assertEqual(result.verdict, 'DIFFERENT')
        self.assertEqual(result.semantic_verdict, 'DIFFERENT')
        self.assertEqual(result.rows[0].status, 'SCENARIO_PHASE_DIFF')

    def test_manual_global_advance_is_atomic_on_backwards_client(self):
        spec = {'schema_version': 1, 'id': 'review', 'name': 'Review fixture',
                'description': 'Explicitly synthetic empty timeline',
                'duration_ms': 100, 'events': [], 'assertions': []}
        server = VirtualDeviceServer('127.0.0.1', 0, VirtualSpitfire(), CaptureStore())
        server.set_scenario(spec, clock='manual')
        server.advance_scenario(20, 'left')
        server.advance_scenario(80, 'right')
        with self.assertRaises(ValueError):
            server.advance_scenario(50)
        self.assertEqual(server._scenario_clients['left'][0].snapshot()['time_ms'], 20)
        self.assertEqual(server._scenario_clients['right'][0].snapshot()['time_ms'], 80)

    def _compare_cli(self, verdict, reaction_verdict=None):
        result = SimpleNamespace(to_dict=lambda: {'verdict': verdict})
        argv = ['--compare-capture', 'dummy.jsonl', '--original-label', 'XP', '--python-label', 'PY']
        if reaction_verdict is not None:
            argv += ['--reaction-rules', 'rules.json']
        with patch('spitfire_twin_verifier.evidence.load_capture', return_value=object()), \
             patch('spitfire_twin_verifier.cli.compare_transactions', return_value=result), \
             patch('spitfire_twin_verifier.cli.write_report', return_value=Path('report')), \
             patch('spitfire_twin_verifier.evidence_report.write_workbench_report', return_value=Path('report.html')), \
             patch('spitfire_twin_verifier.evidence.assess_reactions', return_value={'verdict': reaction_verdict}), \
             patch('pathlib.Path.read_text', return_value='[]'), redirect_stdout(StringIO()):
            return main(argv)

    def test_capture_difference_or_incomplete_is_nonzero_exit(self):
        for verdict in ('DIFFERENT', 'ERROR', 'INCOMPLETE', 'UNVERIFIED', 'OBSERVATION_REQUIRED'):
            with self.subTest(verdict=verdict):
                self.assertNotEqual(self._compare_cli(verdict), 0)

    def test_capture_match_without_reaction_fail_is_zero_exit(self):
        self.assertEqual(self._compare_cli('MATCH'), 0)

    def test_reaction_fail_or_incomplete_overrides_capture_match_exit(self):
        for verdict in ('FAIL', 'INCOMPLETE', 'UNVERIFIED'):
            with self.subTest(verdict=verdict):
                self.assertNotEqual(self._compare_cli('MATCH', verdict), 0)

    def test_matrix_cli_passes_explicit_trust_flag(self):
        with patch('spitfire_twin_verifier.client_matrix.run_matrix', return_value={'status': 'PASS'}) as run, \
             patch('spitfire_twin_verifier.evidence_report.write_workbench_report', return_value=Path('report.html')), \
             redirect_stdout(StringIO()):
            self.assertEqual(main(['--matrix', 'trusted.zip', '--trust-client-code']), 0)
        self.assertTrue(run.call_args.kwargs.get('trusted'))


if __name__ == '__main__':
    unittest.main()

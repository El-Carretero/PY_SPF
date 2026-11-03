"""Reproducible local-only validation with machine-readable test evidence."""
from pathlib import Path
import argparse
import contextlib
import io
import json
import platform
import sys
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'validation_output'))
    parser.add_argument('--clients', nargs='*', default=[])
    parser.add_argument('--trust-client-code', action='store_true')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (output / 'unit_tests.txt').write_text(stream.getvalue(), encoding='utf-8')
    evidence = {'created_utc': datetime.now(timezone.utc).isoformat(),
                'python': sys.version, 'platform': platform.platform(),
                'tests_run': result.testsRun, 'passed': result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
                'failures': [(str(t), e) for t, e in result.failures],
                'errors': [(str(t), e) for t, e in result.errors],
                'skipped': [(str(t), why) for t, why in result.skipped],
                'unit_status': 'PASS' if result.wasSuccessful() else 'FAIL',
                'xp_execution': 'NOT_PERFORMED', 'hardware_validation': 'NOT_PERFORMED'}
    from spitfire_twin_verifier.scenarios import list_scenarios, run_scenario
    from spitfire_twin_verifier.evidence_report import write_workbench_report
    from spitfire_twin_verifier.cli import self_test
    scenarios = [run_scenario(s['id']) for s in list_scenarios()]
    write_workbench_report(output / 'scenarios', {'results': scenarios, 'scope': 'synthetic model assertions only'})
    evidence['scenarios'] = [{'id': s['scenario_id'], 'verdict': s['model_verdict']} for s in scenarios]
    evidence['loopback_self_test_exit'] = self_test(output / 'loopback')
    if args.clients:
        from spitfire_twin_verifier.client_matrix import run_matrix
        matrix = run_matrix(args.clients, output_dir=output / 'clients', trusted=args.trust_client_code)
        evidence['client_matrix'] = [{'version': c.get('inspection', {}).get('version'),
                                     'status': c['status'],
                                     'cases': [{'id': x['id'], 'status': x['status']} for x in c['cases']]} for c in matrix['clients']]
        evidence['client_matrix_status'] = matrix['status']
    (output / 'validation.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    # Product regressions and differences in tested clients are separate outcomes.
    return 0 if result.wasSuccessful() and all(s['model_verdict'] == 'PASS' for s in scenarios) and evidence['loopback_self_test_exit'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())

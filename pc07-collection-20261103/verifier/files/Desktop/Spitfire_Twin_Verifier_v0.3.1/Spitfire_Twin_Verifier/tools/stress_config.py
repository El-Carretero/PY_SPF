"""Repeat the isolated concurrent-save regression without touching user settings."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from spitfire_twin_verifier import __version__
from test_config import ConfigTests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=100)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 1000:
        parser.error('--rounds must be in 1..1000')
    suite = unittest.TestSuite(ConfigTests('test_concurrent_saves_produce_complete_valid_json')
                               for _ in range(args.rounds))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    evidence = {'version': __version__, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'python': sys.version, 'platform': platform.platform(),
                'scope': 'same-process concurrent config saves in fresh temporary folders',
                'rounds': result.testsRun, 'attempted_saves_per_round': 16, 'workers': 4,
                'failures': [(str(t), e) for t, e in result.failures],
                'errors': [(str(t), e) for t, e in result.errors],
                'skipped': [(str(t), e) for t, e in result.skipped],
                'status': 'PASS' if result.wasSuccessful() and not result.skipped else 'FAIL'}
    target = Path(args.output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    target.with_suffix('.log').write_text(stream.getvalue(), encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

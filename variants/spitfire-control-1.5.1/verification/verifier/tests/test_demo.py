import tempfile
import unittest
from pathlib import Path

from spitfire_twin_verifier.cli import self_test
from spitfire_twin_verifier.compare import compare_transactions
from spitfire_twin_verifier.demo import run_loopback_demo
from spitfire_twin_verifier.records import CaptureStore


class DemoTests(unittest.TestCase):
    def test_loopback_demo_matches(self):
        capture = CaptureStore()
        run_loopback_demo(capture, "XP", "PY")
        result = compare_transactions(capture.transactions(), "XP", "PY")
        self.assertEqual(len(capture.transactions()), 18)
        self.assertEqual(result.verdict, "MATCH")

    def test_self_test_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self_test(Path(directory)), 0)
            self.assertTrue(list(Path(directory).glob("comparison_*/report.html")))


if __name__ == "__main__":
    unittest.main()

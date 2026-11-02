"""Regression checks against independent synthetic protocol examples; no physical capture."""
import unittest
from unittest.mock import patch

from analysis.verify_optout_capture import (
    load_capture, verify_command_bytes, verify_poll, verify_responses,
)


class SyntheticOptoutProtocolTests(unittest.TestCase):
    def setUp(self):
        self.capture = load_capture()
        # Fixture replay must not contact hardware, even after future refactors.
        self.no_socket = patch("socket.socket", side_effect=AssertionError("No network during replay"))
        self.no_socket.start()
        self.addCleanup(self.no_socket.stop)

    def test_public_fixture_has_synthetic_provenance(self):
        self.assertEqual(self.capture["fixture_kind"], "synthetic")
        self.assertNotIn("source_run", self.capture)
        self.assertNotIn("pcap_sha256", self.capture["provenance"])

    def test_synthetic_optout_poll_order_and_generated_counts(self):
        result = verify_poll(self.capture)
        self.assertEqual(result["example_cycles"], 37)
        self.assertEqual(result["generated_queries"], 1073)
        self.assertEqual(result["cycle_queries"], 29)

    def test_controller_datagrams_match_synthetic_wire_examples(self):
        self.assertEqual(verify_command_bytes(self.capture)["exact_command_datagrams"], 15)

    def test_synthetic_hv_on_and_unsupported_empower_examples(self):
        result = verify_responses(self.capture)
        self.assertEqual(result["example_reply_samples_decoded"], 15)
        self.assertEqual(result["example_hv_on"], 1)
        self.assertTrue(result["empower_sentinels_retained"])


if __name__ == "__main__":
    unittest.main()

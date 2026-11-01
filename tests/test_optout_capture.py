"""Regression checks against independently captured original UDP traffic."""
import unittest
from unittest.mock import patch

from analysis.verify_optout_capture import (
    load_capture, verify_command_bytes, verify_poll, verify_responses,
)


class OriginalOptoutCaptureTests(unittest.TestCase):
    def setUp(self):
        self.capture = load_capture()
        # Fixture replay must not contact hardware, even after future refactors.
        self.no_socket = patch("socket.socket", side_effect=AssertionError("No network during replay"))
        self.no_socket.start()
        self.addCleanup(self.no_socket.stop)

    def test_original_optout_poll_order_and_entire_capture_counts(self):
        result = verify_poll(self.capture)
        self.assertEqual(result["captured_cycles"], 37)
        self.assertEqual(result["captured_queries"], 1073)
        self.assertEqual(result["cycle_queries"], 29)

    def test_actual_controller_datagrams_match_original_capture(self):
        self.assertEqual(verify_command_bytes(self.capture)["exact_command_datagrams"], 15)

    def test_original_optout_hv_on_and_missing_empower_replies(self):
        result = verify_responses(self.capture)
        self.assertEqual(result["actual_reply_samples_decoded"], 15)
        self.assertEqual(result["observed_hv_on"], 1)
        self.assertTrue(result["empower_sentinels_retained"])


if __name__ == "__main__":
    unittest.main()

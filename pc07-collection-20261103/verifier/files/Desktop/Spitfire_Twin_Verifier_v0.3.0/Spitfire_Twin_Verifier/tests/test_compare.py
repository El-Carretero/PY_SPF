import unittest

from spitfire_twin_verifier.compare import compare_transactions
from spitfire_twin_verifier.records import Transaction
from spitfire_twin_verifier.protocol import encode_commands, encode_replies


def tx(seq, label, cid, command, argument="", response="OK"):
    base = command[:-len(argument)].strip() if argument else command
    return Transaction(seq, seq, "2026-01-01T00:00:00Z", label, label, "127.0.0.1", seq,
                       1, cid, command, base, argument, encode_commands([f"[{cid}]{command}"]).hex(),
                       response, encode_replies([(cid, response)]).hex(), 0.1, "REPLIED")


class CompareTests(unittest.TestCase):
    def test_equal_sequences_match(self):
        items = [tx(1, "XP", 1000, "*idn?", response="ID"), tx(2, "PY", 1000, "*idn?", response="ID")]
        result = compare_transactions(items, "XP", "PY")
        self.assertEqual(result.verdict, "MATCH")
        self.assertEqual(result.matched, 1)

    def test_argument_difference_detected(self):
        items = [tx(1, "XP", 2004, "EMP:QSW:PRF 125.00", "125.00"),
                 tx(2, "PY", 2004, "EMP:QSW:PRF 1250", "1250")]
        result = compare_transactions(items, "XP", "PY")
        self.assertEqual(result.verdict, "DIFFERENT")
        self.assertEqual(result.rows[0].status, "ARGUMENT_DIFF")

    def test_polling_can_be_ignored_but_counts_remain(self):
        items = [tx(1, "XP", 1031, "ECU:HUM?", response="34"),
                 tx(2, "XP", 1031, "ECU:HUM?", response="34"),
                 tx(3, "PY", 1031, "ECU:HUM?", response="34")]
        result = compare_transactions(items, "XP", "PY", ignore_polling=True)
        self.assertEqual(result.verdict, "MATCH")
        self.assertTrue(result.count_differences)

    def test_missing_client_is_incomplete(self):
        result = compare_transactions([tx(1, "XP", 1000, "*idn?")], "XP", "PY")
        self.assertEqual(result.verdict, "INCOMPLETE")

    def test_different_poll_coverage_is_not_hidden(self):
        items = [tx(1, "XP", 1031, "ECU:HUM?", response="34"),
                 tx(2, "PY", 1030, "ECU:READTEMP?", response="25")]
        result = compare_transactions(items, "XP", "PY", ignore_polling=True)
        self.assertEqual(result.verdict, "DIFFERENT")
        self.assertEqual(result.poll_coverage_differences, [1030, 1031])


if __name__ == "__main__":
    unittest.main()

import unittest

from spitfire_twin_verifier.protocol import (
    MAX_DATAGRAM, ProtocolError, decode_commands, decode_replies,
    encode_commands, encode_replies,
)


class ProtocolTests(unittest.TestCase):
    def test_multi_command_round_trip(self):
        packet = encode_commands(["[1000]*idn?", "[1031]ECU:HUM?"])
        commands = decode_commands(packet)
        self.assertEqual([item.command_id for item in commands], [1000, 1031])
        self.assertEqual(commands[0].base, "*idn?")

    def test_argument_is_preserved(self):
        command = decode_commands(encode_commands(["[2004]EMP:QSW:PRF 125.00"]))[0]
        self.assertEqual(command.argument, "125.00")

    def test_reply_round_trip_lf_and_crlf(self):
        for ending in ("\n", "\r\n"):
            replies = decode_replies(encode_replies([(1000, "Spitfire"), (1031, "34.0")], line_ending=ending))
            self.assertEqual([(item.command_id, item.value) for item in replies], [(1000, "Spitfire"), (1031, "34.0")])

    def test_bad_header_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_commands(b"bad[1000]*idn?\n")

    def test_non_ascii_rejected(self):
        with self.assertRaises(ProtocolError):
            encode_commands(["[1000]한글"])

    def test_maximum_enforced(self):
        with self.assertRaises(ProtocolError):
            decode_commands(b"Spectra-Physics:CMD_ECLIPSE," + b"x" * MAX_DATAGRAM)


if __name__ == "__main__":
    unittest.main()


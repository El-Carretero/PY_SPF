import unittest

from spitfire_control.protocol import (
    COMMAND_HEADER,
    MAX_DATAGRAM,
    ProtocolError,
    decode_command_datagram,
    decode_reply_datagram,
    encode_datagram,
    encode_reply,
    split_datagrams,
)


class ProtocolTests(unittest.TestCase):
    def test_encode_matches_legacy_framing(self):
        packet = encode_datagram(["[1000]*idn?", "[1031]ECU:HUM?"])
        self.assertEqual(packet, COMMAND_HEADER + b"[1000]*idn?\n[1031]ECU:HUM?\n")

    def test_command_roundtrip(self):
        commands = decode_command_datagram(encode_datagram(["[1000]*idn?"]))
        self.assertEqual(commands[0].command_id, 1000)
        self.assertEqual(commands[0].command, "*idn?")

    def test_reply_roundtrip(self):
        replies = decode_reply_datagram(encode_reply([(1007, "18.125"), (1031, 34)]))
        self.assertEqual([(r.command_id, r.value) for r in replies], [(1007, "18.125"), (1031, "34")])

    def test_receiver_retains_legacy_permissive_vendor_prefix(self):
        reply = decode_reply_datagram("anything:REPLY_ECLIPSE:<1000>hello\r\n")
        self.assertEqual(reply[0].value, "hello")

    def test_bad_packet_is_rejected(self):
        with self.assertRaises(ProtocolError):
            decode_reply_datagram("Spectra-Physics:NOT_A_REPLY:<1000>x")
        with self.assertRaises(ProtocolError):
            encode_datagram(["not tagged"])
        with self.assertRaisesRegex(ProtocolError, "ASCII"):
            encode_datagram(["[1000]한글"])

    def test_split_respects_maximum(self):
        lines = [f"[{1000 + i % 80}]" + ("X" * 100) for i in range(40)]
        packets = split_datagrams(lines)
        self.assertGreater(len(packets), 1)
        self.assertTrue(all(len(packet) <= MAX_DATAGRAM for packet in packets))


if __name__ == "__main__":
    unittest.main()

"""Behavior tests derived from independent static wire-format evidence."""
import socket
import unittest

from spitfire.protocol import (
    COMMANDS, QUERIES, PACKET_PREFIX, PacketBuffer, UDPTransport,
    calc_crc16_c_string, crc16, crc32, format_message, parse_datagram,
)


class ProtocolRecoveryTests(unittest.TestCase):
    def test_exact_tag_tables_preserve_original_case(self):
        self.assertEqual(len(QUERIES), 90)
        self.assertEqual(len(COMMANDS), 56)
        self.assertEqual(QUERIES[1000], '*idn?')
        self.assertEqual(QUERIES[1038], '*IDN?')
        self.assertEqual(QUERIES[1082], '*IdN?')
        self.assertEqual(COMMANDS[2034], '')

    def test_query_command_and_special_parameter_format(self):
        self.assertEqual(format_message(1000), '[1000]*idn?')
        self.assertEqual(format_message(1000, ' ignored'), '[1000]*idn?')
        self.assertEqual(format_message(1026, ' 2'), '[1026]TDG:DEL 2')
        self.assertEqual(format_message(2003, ' 10.00'), '[2003]EMP:DIODE:CURR 10.00')

    def test_packet_batches_and_refresh(self):
        pending = PacketBuffer()
        self.assertEqual(pending.append('[1000]*idn?'), [])
        self.assertEqual(pending.append('[1013]EMP:STB?'), [])
        self.assertEqual(pending.flush(), PACKET_PREFIX + b'[1000]*idn?\n[1013]EMP:STB?\n')
        self.assertIsNone(pending.flush())

    def test_packet_limit_preserves_original_check(self):
        pending = PacketBuffer()
        self.assertEqual(pending.append('x' * 1401), [])
        self.assertIsNone(pending.flush())
        # The original checks new message length before adding header/newline.
        self.assertEqual(pending.append('x' * 1400), [])
        self.assertEqual(pending.flush(), PACKET_PREFIX + b'x' * 1400 + b'\n')

    def test_reply_header_lines_and_local_prefix(self):
        response = b'Spectra-Physics:REPLY_ECLIPSE:<1000>Spitfire\r\n\n<1013>1\r\n'
        lines = parse_datagram(response, 2)
        self.assertEqual([x.body for x in lines], ['<1000>Spitfire', '<1013>1'])
        self.assertEqual([x.decorated for x in lines], ['(2,1)<1000>Spitfire', '(2,2)<1013>1'])
        self.assertEqual(parse_datagram(b'Spectra-Physics:OTHER:<1000>x'), [])

    def test_reply_matches_prefix_and_stops_at_nul(self):
        # The binary accepts arbitrary vendor text and suffix after REPLY_ECLIPSE.
        lines = parse_datagram(b'Other:REPLY_ECLIPSE_suffix:<1013>1\x00<1013>2')
        self.assertEqual([x.body for x in lines], ['<1013>1'])
        # Missing second ':' is handled by passing the matched header as a line.
        self.assertEqual(parse_datagram(b'Other:REPLY_ECLIPSE')[0].body, 'REPLY_ECLIPSE')

    def test_response_native_buffer_limit(self):
        lines = parse_datagram(b'Other:REPLY_ECLIPSE:' + b'x' * 250, 12)
        self.assertEqual(len(lines[0].decorated), 198)
        self.assertEqual(lines[0].decorated[:6], '(12,1)')

    def test_crc_vectors_and_c_string_return(self):
        self.assertEqual(crc16(b'123456789'), 0x31c3)
        self.assertEqual(crc16(b'123456789', 0xffff), 0x29b1)
        self.assertEqual(crc32(b'123456789', 0xffffffff) ^ 0xffffffff, 0xcbf43926)
        self.assertEqual(calc_crc16_c_string(b'123456789\0ignored'), 0x31c3)
        unsigned = crc16(b'x')
        self.assertEqual(calc_crc16_c_string(b'x'), unsigned if unsigned < 0x8000 else unsigned - 0x10000)

    def test_loopback_wire_round_trip(self):
        # Always 127.0.0.1 and ephemeral ports; no physical device is contacted.
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('127.0.0.1', 0))
        server.settimeout(1)
        transport = UDPTransport('127.0.0.1', server.getsockname()[1], bind_port=0, timeout=1)
        try:
            transport.open()
            packet = PACKET_PREFIX + b'[1000]*idn?\n'
            transport.send_packet(packet)
            received, sender = server.recvfrom(2000)
            self.assertEqual(received, packet)
            server.sendto(b'Spectra-Physics:REPLY_ECLIPSE:<1000>Spitfire\n', sender)
            self.assertEqual(transport.receive()[0].body, '<1000>Spitfire')
        finally:
            transport.close()
            server.close()


if __name__ == '__main__':
    unittest.main()

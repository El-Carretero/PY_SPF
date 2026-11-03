import socket
import unittest
from unittest.mock import patch

from spitfire_control.transport import UdpSettings, UdpTransport, TransportError


class FakeSocket:
    def __init__(self, replies):
        self.replies = list(replies)
        self.bound = None
        self.sent = []
        self.closed = False

    def bind(self, address):
        self.bound = address

    def setsockopt(self, *args):
        self.socket_option = args

    def sendto(self, data, address):
        self.sent.append((data, address))

    def settimeout(self, timeout):
        self.timeout = timeout

    def recvfrom(self, size):
        if not self.replies:
            raise socket.timeout()
        return self.replies.pop(0), ("10.19.70.13", 1024)

    def close(self):
        self.closed = True


class UdpTransportTests(unittest.TestCase):
    def test_windows_exclusive_bind_option(self):
        fake = FakeSocket([])
        with patch("spitfire_control.transport.socket.SO_EXCLUSIVEADDRUSE", 0xFFFF, create=True), \
             patch("spitfire_control.transport.socket.gethostbyname", return_value="127.0.0.1"), \
             patch("spitfire_control.transport.socket.socket", return_value=fake):
            transport = UdpTransport(UdpSettings())
            transport.connect()
            transport.close()
        self.assertEqual(fake.socket_option, (socket.SOL_SOCKET, 0xFFFF, 1))

    def test_exact_hardware_packet_and_reply(self):
        fake = FakeSocket([
            b"unrelated discovery packet",
            b"Spectra-Physics:REPLY_ECLIPSE:<1000>controller-id\n",
        ])
        settings = UdpSettings(remote_host="10.19.70.13", remote_port=1024, local_host="0.0.0.0", local_port=1024)
        with patch("spitfire_control.transport.socket.gethostbyname", return_value="10.19.70.13"), patch("spitfire_control.transport.socket.socket", return_value=fake):
            transport = UdpTransport(settings)
            transport.connect()
            replies = transport.exchange("[1000]*idn?", 0.2)
            transport.close()
        self.assertEqual(fake.bound, ("0.0.0.0", 1024))
        self.assertEqual(fake.sent[0], (b"Spectra-Physics:CMD_ECLIPSE,[1000]*idn?\n", ("10.19.70.13", 1024)))
        self.assertEqual(replies[0].value, "controller-id")
        self.assertTrue(fake.closed)

    def test_timeout_is_reported(self):
        fake = FakeSocket([])
        with patch("spitfire_control.transport.socket.gethostbyname", return_value="10.19.70.13"), patch("spitfire_control.transport.socket.socket", return_value=fake):
            transport = UdpTransport(UdpSettings())
            transport.connect()
            with self.assertRaisesRegex(TransportError, "Timed out"):
                transport.exchange("[1000]*idn?", 0.01)


if __name__ == "__main__":
    unittest.main()

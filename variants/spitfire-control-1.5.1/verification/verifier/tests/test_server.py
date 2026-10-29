import socket
import time
import unittest

from spitfire_twin_verifier.model import VirtualSpitfire
from spitfire_twin_verifier.protocol import decode_replies, encode_commands
from spitfire_twin_verifier.records import CaptureStore
from spitfire_twin_verifier.server import VirtualDeviceServer


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.capture = CaptureStore()
        self.device = VirtualSpitfire()
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.bind(("127.0.0.1", 0))
        self.client.settimeout(1.0)
        endpoint = f"127.0.0.1:{self.client.getsockname()[1]}"
        self.server = VirtualDeviceServer("127.0.0.1", 0, self.device, self.capture, {endpoint: "Test Client"})
        self.server.start()

    def tearDown(self):
        self.server.stop()
        self.client.close()

    def exchange(self, lines):
        self.client.sendto(encode_commands(lines), self.server.local_address)
        data, _ = self.client.recvfrom(4096)
        return decode_replies(data)

    def test_batch_reply_and_capture(self):
        replies = self.exchange(["[1000]*idn?", "[1031]ECU:HUM?"])
        self.assertEqual(len(replies), 2)
        deadline = time.monotonic() + 1
        while len(self.capture.transactions()) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        items = self.capture.transactions()
        self.assertEqual([item.command_id for item in items], [1000, 1031])
        self.assertTrue(all(item.client_label == "Test Client" for item in items))

    def test_stateful_write(self):
        self.exchange(["[2004]EMP:QSW:PRF 125.00"])
        reply = self.exchange(["[1010]EMP:QSW:PRF?"])[0]
        self.assertEqual(reply.value, "125")

    def test_malformed_packet_is_logged_without_reply(self):
        self.client.sendto(b"bad packet", self.server.local_address)
        with self.assertRaises(socket.timeout):
            self.client.recvfrom(4096)
        self.assertTrue(any(item.level == "PROTOCOL" for item in self.capture.messages()))


if __name__ == "__main__":
    unittest.main()


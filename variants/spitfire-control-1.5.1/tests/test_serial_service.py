import queue
import threading
import time
import unittest

from spitfire_control.serial_service import (
    RawSerialSession,
    SerialServiceError,
    SerialSettings,
    encode_transmission,
    parse_hex_bytes,
)


class FakeSerial:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.is_open = False
        self.dtr = False
        self.rts = False
        self.written = bytearray()
        self._incoming = bytearray()
        self._lock = threading.Lock()

    @property
    def in_waiting(self):
        with self._lock:
            return len(self._incoming)

    def feed(self, data: bytes):
        with self._lock:
            self._incoming.extend(data)

    def read(self, count: int) -> bytes:
        deadline = time.monotonic() + 0.01
        while self.is_open and time.monotonic() < deadline:
            with self._lock:
                if self._incoming:
                    result = bytes(self._incoming[:count])
                    del self._incoming[:count]
                    return result
            time.sleep(0.001)
        return b""

    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise OSError("closed")
        self.written.extend(data)
        return len(data)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False


class SerialCodecTests(unittest.TestCase):
    def test_hex_formats(self):
        self.assertEqual(parse_hex_bytes("53 54 4f 50"), b"STOP")
        self.assertEqual(parse_hex_bytes("0x53,0x54,0x4F,0x50"), b"STOP")
        self.assertEqual(parse_hex_bytes("53544F50"), b"STOP")

    def test_hex_rejects_invalid_or_odd_input(self):
        for value in ("ABC", "AA GG", "0011222"):
            with self.subTest(value=value), self.assertRaises(SerialServiceError):
                parse_hex_bytes(value)

    def test_ascii_and_terminators_are_explicit(self):
        self.assertEqual(encode_transmission("*IDN?", "ASCII", "CRLF"), b"*IDN?\r\n")
        self.assertEqual(encode_transmission("00 FF", "HEX", "NONE"), b"\x00\xff")
        with self.assertRaises(SerialServiceError):
            encode_transmission("온", "ASCII", "NONE")


class RawSerialSessionTests(unittest.TestCase):
    def setUp(self):
        self.handles = []

        def factory(**kwargs):
            handle = FakeSerial(**kwargs)
            self.handles.append(handle)
            return handle

        self.session = RawSerialSession(serial_factory=factory, port_provider=lambda: ("COM9", "COM2"))

    def tearDown(self):
        self.session.close()

    def test_settings_validation(self):
        with self.assertRaises(SerialServiceError):
            SerialSettings(port="", baudrate=19_200).validate()
        with self.assertRaises(SerialServiceError):
            SerialSettings(port="COM1", bytesize=9).validate()

    def test_connect_send_receive_and_control_lines(self):
        settings = SerialSettings(port="COM9", baudrate=19_200, dtr=True)
        self.session.connect(settings)
        handle = self.handles[0]
        self.assertTrue(self.session.connected)
        self.assertEqual(handle.kwargs["baudrate"], 19_200)
        self.assertTrue(handle.dtr)

        self.assertEqual(self.session.send(b"PING\r"), 5)
        self.assertEqual(bytes(handle.written), b"PING\r")
        self.session.set_control_lines(dtr=False, rts=True)
        self.assertFalse(handle.dtr)
        self.assertTrue(handle.rts)

        handle.feed(b"PONG\r")
        events = []
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            try:
                events.append(self.session.events.get(timeout=0.02))
            except queue.Empty:
                pass
            if b"".join(event.data for event in events if event.kind == "rx") == b"PONG\r":
                break
        self.assertEqual(b"".join(event.data for event in events if event.kind == "rx"), b"PONG\r")
        self.assertIn("tx", [event.kind for event in events])

        self.session.close()
        self.assertFalse(self.session.connected)
        self.assertFalse(handle.is_open)

    def test_port_provider(self):
        self.assertEqual(self.session.list_ports(), ["COM9", "COM2"])


if __name__ == "__main__":
    unittest.main()

"""Raw terminal connection integrity; all ports are mocked in memory."""
import unittest
from unittest.mock import patch

from spitfire_control.serial_service import RawSerialSession, SerialServiceError, SerialSettings


class OrderedPort:
    def __init__(self, fail=None):
        self.is_open = False
        self.closed = False
        self.events = []
        self.fail = fail
    @property
    def dtr(self):
        return self._dtr
    @dtr.setter
    def dtr(self, value):
        self.events.append(("dtr", value))
        if self.fail == "dtr":
            raise OSError("dtr failure")
        self._dtr = value
    @property
    def rts(self):
        return self._rts
    @rts.setter
    def rts(self, value):
        self.events.append(("rts", value))
        if self.fail == "rts":
            raise OSError("rts failure")
        self._rts = value
    def open(self):
        self.events.append(("open", self.dtr, self.rts))
        if self.fail == "open":
            self.is_open = True  # Simulate a partial driver open before failure.
            raise OSError("open failure")
        self.is_open = True
    def close(self):
        self.closed = True
        self.is_open = False
        self.events.append(("close",))


class SerialIntegrityTests(unittest.TestCase):
    def test_desired_lines_applied_before_open_for_real_factory_route(self):
        for port_name in ("COM99", "loop://"):
            with self.subTest(port=port_name):
                handle = OrderedPort()
                session = RawSerialSession()
                with patch("spitfire_control.serial_service.serial.serial_for_url", return_value=handle) as factory, patch.object(session, "_reader_loop"):
                    session.connect(SerialSettings(port_name, dtr=False, rts=True))
                    self.assertTrue(factory.call_args.kwargs["do_not_open"])
                    self.assertEqual(factory.call_args.args[0], port_name)
                    self.assertEqual(handle.events[:3], [("dtr", False), ("rts", True), ("open", False, True)])
                    self.assertTrue(session.connected)
                    session.close()

    def test_line_or_open_failures_close_the_unowned_handle(self):
        for failure in ("dtr", "rts", "open"):
            with self.subTest(failure=failure):
                handle = OrderedPort(fail=failure)
                session = RawSerialSession(serial_factory=lambda **kwargs: handle)
                with self.assertRaises(SerialServiceError):
                    session.connect(SerialSettings("FAKE"))
                self.assertTrue(handle.closed)
                self.assertFalse(session.connected)
                self.assertIsNone(session._reader)

    def test_already_open_injected_handle_is_closed_and_rejected(self):
        handle = OrderedPort()
        handle.is_open = True
        session = RawSerialSession(serial_factory=lambda **kwargs: handle)
        with self.assertRaisesRegex(SerialServiceError, "unopened"):
            session.connect(SerialSettings("FAKE"))
        self.assertTrue(handle.closed)
        self.assertFalse(session.connected)


if __name__ == "__main__":
    unittest.main()

"""Offline audit diagnostics distinguish received invalid replies from timeouts."""
from collections import deque
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.protocol import Reply
from spitfire_control.transport import BaseTransport, TransportError


class ScriptedTransport(BaseTransport):
    """No sockets or serial handles; replies are injected by the test."""
    name = "Simulator"

    def __init__(self, outcomes):
        self.outcomes = deque(outcomes)
        self.sent = []

    def connect(self):
        pass

    def close(self):
        pass

    def exchange(self, command_line, timeout, *, send_guard=None):
        send = lambda: self.sent.append(command_line)
        if send_guard is None:
            send()
        else:
            send_guard(send)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return [outcome]


class AuditValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def make_controller(self, outcomes, **kwargs):
        transport = ScriptedTransport(outcomes)
        controller = LaserController(transport, auto_poll=False,
                                     log_directory=self.temp.name, **kwargs)
        return controller, transport

    def rows(self, controller):
        with controller._audit.path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames,
                             ["utc_time", "direction", "command_id", "text", "result"])
            return list(reader)

    def test_received_malformed_value_retains_raw_rx_and_parse_diagnostic(self):
        raw = '<1065>not a frequency, "bad"'
        controller, transport = self.make_controller([Reply(1065, 'not a frequency, "bad"', raw)], pump_mode="external")
        controller._execute(PendingCommand(1065, None, "test"))
        rows = self.rows(controller)
        self.assertEqual([r["direction"] for r in rows], ["TX", "RX", "PARSE_ERROR"])
        self.assertEqual(rows[-1]["text"], raw)
        self.assertEqual(rows[-1]["command_id"], "1065")
        self.assertIn("state decoder", rows[-1]["result"])
        self.assertIn(1065, controller.state.invalid_ids)
        self.assertTrue(controller.state.external_enable_reason())
        self.assertEqual(len(transport.sent), 1)

    def test_empty_reply_is_received_but_invalid_not_timeout(self):
        controller, _ = self.make_controller([Reply(1044, "", "<1044>")])
        controller._execute(PendingCommand(1044, None, "test"))
        rows = self.rows(controller)
        self.assertEqual([r["direction"] for r in rows], ["TX", "RX", "INVALID_REPLY"])
        self.assertEqual(rows[-1]["text"], "<1044>")
        self.assertIn("Empty response payload", rows[-1]["result"])

    def test_device_error_is_not_a_parse_or_transport_error(self):
        controller, _ = self.make_controller([Reply(1019, "NACK: unsupported", "<1019>NACK: unsupported")])
        controller._execute(PendingCommand(1019, None, "test"))
        rows = self.rows(controller)
        self.assertEqual([r["direction"] for r in rows], ["TX", "RX", "DEVICE_ERROR"])
        self.assertIn("NACK", rows[-1]["result"])

    def test_valid_reply_has_only_existing_tx_rx_rows(self):
        controller, _ = self.make_controller([Reply(1021, "0", "<1021>0")])
        controller._execute(PendingCommand(1021, None, "test"))
        rows = self.rows(controller)
        self.assertEqual([r["direction"] for r in rows], ["TX", "RX"])
        self.assertEqual(rows[-1]["result"], "")
        self.assertIs(controller.state.high_voltage, False)

    def test_timeout_remains_transport_error_without_rx(self):
        controller, _ = self.make_controller([TransportError("Timed out waiting for reply to command 1021")])
        controller._execute(PendingCommand(1021, None, "test"))
        rows = self.rows(controller)
        self.assertEqual([r["direction"] for r in rows], ["TX", "ERROR"])
        self.assertIn("Timed out", rows[-1]["result"])

    def test_unknown_write_ack_has_specific_reason_and_keeps_readback_queued(self):
        controller, transport = self.make_controller([Reply(2016, "BUSY", "<2016>BUSY")])
        controller._execute(PendingCommand(2016, None, "test"))
        rows = self.rows(controller)
        self.assertEqual([r["direction"] for r in rows], ["TX", "RX", "PARSE_ERROR"])
        self.assertIn("expected OK or ACK", rows[-1]["result"])
        self.assertIn(1021, [request.command_id for request in controller._commands])
        self.assertEqual(transport.sent, ["[2016]TDG:HV:OFF"])

    def test_audit_io_failure_does_not_block_off_or_later_read(self):
        controller, transport = self.make_controller([
            Reply(2016, "BUSY", "<2016>BUSY"), Reply(1021, "0", "<1021>0")])
        with patch.object(Path, "open", side_effect=OSError("audit disk unavailable")):
            controller._execute(PendingCommand(2016, None, "test"))
            controller._execute(PendingCommand(1021, None, "test"))
        self.assertEqual(transport.sent, ["[2016]TDG:HV:OFF", "[1021]TDG:HV:ON?"])
        self.assertIs(controller.state.high_voltage, False)

    def test_invalid_read_does_not_end_subsequent_exchange(self):
        controller, transport = self.make_controller([
            Reply(1065, "invalid", "<1065>invalid"), Reply(1021, "0", "<1021>0")])
        controller._execute(PendingCommand(1065, None, "test"))
        controller._execute(PendingCommand(1021, None, "test"))
        rows = self.rows(controller)
        self.assertEqual([r["direction"] for r in rows],
                         ["TX", "RX", "PARSE_ERROR", "TX", "RX"])
        self.assertEqual(len(transport.sent), 2)
        self.assertTrue(controller.state.connected)


if __name__ == "__main__":
    unittest.main()

"""Readback-integrity regressions; no network, COM port, or GUI is used."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState
from spitfire_control.transport import SimulatorTransport, TransportError


def apply(state, command_id, value):
    value = str(value)
    return state.apply(Reply(command_id, value, f"<{command_id}>{value}"))


def connected_state():
    return DeviceState(connected=True, transport_open=True, pump_mode="external")


class ReadbackIntegrityTests(unittest.TestCase):
    def test_hv_error_in_either_alias_invalidates_cached_off(self):
        for old_id, error_id in ((1021, 1061), (1061, 1021)):
            for reply in ("ERR unsupported", "", "not-a-number"):
                with self.subTest(old_id=old_id, error_id=error_id, reply=reply):
                    state = connected_state()
                    self.assertTrue(apply(state, old_id, 0))
                    self.assertIs(state.high_voltage, False)
                    self.assertFalse(apply(state, error_id, reply))
                    self.assertIsNone(state.high_voltage)
                    self.assertIsNone(state.value(1021))
                    self.assertFalse(state.is_fresh(1021))
                    self.assertFalse(state.is_fresh(1061))

    def test_oscillator_error_invalidates_both_readback_names(self):
        for old_id, error_id in ((1050, 1067), (1067, 1050)):
            with self.subTest(old_id=old_id, error_id=error_id):
                state = connected_state()
                self.assertTrue(apply(state, old_id, "EXT"))
                self.assertEqual(state.field("oscillator_mode"), 1)
                self.assertFalse(apply(state, error_id, "ERR unavailable"))
                self.assertIsNone(state.field("oscillator_mode"))
                self.assertFalse(state.is_fresh(1050))
                self.assertFalse(state.is_fresh(1067))

    def test_channel_alias_error_invalidates_canonical_and_sibling(self):
        for family in ((1045, 1058, 1063), (1046, 1059, 1064)):
            for error_id in family:
                for invalid in ("ERR unavailable", "", "OFF BWD ENA DELAY VALUE = invalid"):
                    with self.subTest(family=family, error_id=error_id, invalid=invalid):
                        state = connected_state()
                        for command_id in family:
                            self.assertTrue(apply(state, command_id, "OFF BWD ENA DELAY VALUE = 12.5"))
                        self.assertFalse(apply(state, error_id, invalid))
                        for command_id in family:
                            self.assertFalse(state.is_fresh(command_id))
                            self.assertIsNone(state.value(command_id))

    def test_unrelated_channel_survives_one_channel_alias_error(self):
        state = connected_state()
        apply(state, 1045, "OFF BWD ENA DELAY VALUE = 12.5")
        apply(state, 1046, "OFF BWD ENA DELAY VALUE = 37.5")
        apply(state, 1058, "ERR unavailable")
        self.assertFalse(state.is_fresh(1045))
        self.assertTrue(state.is_fresh(1046))
        self.assertEqual(state.value(1046), 37.5)

    def test_valid_canonical_read_recovers_after_alias_error(self):
        for canonical, alias, good in ((1021, 1061, "0"), (1050, 1067, "EXT"),
                                     (1045, 1058, "OFF BWD ENA DELAY VALUE = 12.5")):
            with self.subTest(canonical=canonical):
                state = connected_state()
                apply(state, canonical, good)
                apply(state, alias, "ERR unavailable")
                self.assertFalse(state.is_fresh(canonical))
                self.assertTrue(apply(state, canonical, good))
                self.assertTrue(state.is_fresh(canonical))
                # Recovery does not fabricate an independent successful alias reply.
                self.assertFalse(state.is_fresh(alias))

    def test_text_oscillator_alias_refreshes_canonical_and_pending_readback(self):
        state = connected_state()
        state.pending_readbacks.update((1050, 1067))
        self.assertTrue(apply(state, 1067, "EXT"))
        self.assertEqual(state.field("oscillator_mode"), 1)
        self.assertTrue(state.is_fresh(1050))
        self.assertTrue(state.is_fresh(1067))
        self.assertFalse({1050, 1067} & state.pending_readbacks)

    def test_future_link_timestamp_is_not_fresh(self):
        state = connected_state()
        apply(state, 1021, 0)
        now = datetime.now(timezone.utc)
        state.last_reply_at = now + timedelta(seconds=1)
        self.assertFalse(state.link_fresh(now))
        self.assertFalse(state.is_fresh(1021, now))

    def test_future_individual_timestamp_is_not_fresh(self):
        state = connected_state()
        apply(state, 1021, 0)
        now = datetime.now(timezone.utc)
        state.last_reply_at = now
        state.updated_at[1021] = now + timedelta(seconds=1)
        self.assertTrue(state.link_fresh(now))
        self.assertFalse(state.is_fresh(1021, now))


class ResetReadbackIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.audit_patch = patch("spitfire_control.controller.AuditLog.write")
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.transport = SimulatorTransport(empower_present=False)
        self.transport.connect()
        self.addCleanup(self.transport.close)
        self.controller = LaserController(self.transport, auto_poll=False, pump_mode="external")
        self.controller._state.connected = self.controller._state.transport_open = True
        apply(self.controller._state, 1021, 0)

    def test_alias_error_blocks_bwd_reset_and_optout_submission(self):
        apply(self.controller._state, 1061, "ERR unavailable")
        for command_id, argument in ((2018, None), (2036, 1)):
            with self.subTest(command_id=command_id):
                with self.assertRaises(PermissionError):
                    self.controller.submit(command_id, argument)
        self.assertFalse(self.transport.command_history)

    def test_alias_error_does_not_add_hv_off_requirement_to_fault_resets(self):
        apply(self.controller._state, 1061, "ERR unavailable")
        for command_id in (2049, 2052):
            self.controller.submit(command_id)
        self.assertEqual([r.command_id for r in self.controller._commands], [2049, 2052])
        self.assertFalse(self.transport.command_history)

    def test_alias_error_cancels_already_queued_bwd_reset_at_send_time(self):
        for command_id, argument in ((2018, None), (2036, 1)):
            with self.subTest(command_id=command_id):
                apply(self.controller._state, 1021, 0)
                self.controller.submit(command_id, argument)
                queued = self.controller._commands.popleft()
                apply(self.controller._state, 1061, "ERR unavailable")
                self.controller._execute(queued)
        self.assertFalse(self.transport.command_history)

    def test_alias_transport_timeout_invalidates_canonical_hv(self):
        with patch.object(self.transport, "exchange", side_effect=TransportError("test timeout")):
            self.controller._execute(PendingCommand(1061, None, "test"))
        state = self.controller.state
        self.assertIn(1021, state.invalid_ids)
        # Even if a later identity read reconnects the link, HV remains unknown.
        apply(self.controller._state, 1000, "controller")
        self.controller._state.connected = True
        self.assertIsNone(self.controller.state.high_voltage)
        with self.assertRaises(PermissionError):
            self.controller.submit(2018)
        self.assertFalse(self.transport.command_history)


class LegacyStatusParsingTests(unittest.TestCase):
    def test_tdg_stbh_fields_use_unsigned_hex_even_without_prefix(self):
        cases = (("8000", 0x8000), ("A000", 0xA000), ("a000", 0xA000),
                 ("0x8000", 0x8000), ("0XA000", 0xA000),
                 ("FFFFFFFF", 0xFFFFFFFF), ("0xFFFFFFFF", 0xFFFFFFFF), ("0", 0))
        for command_id in (1023, 1039, 1066):
            for raw, expected in cases:
                with self.subTest(command_id=command_id, raw=raw):
                    state = connected_state()
                    self.assertTrue(apply(state, command_id, raw))
                    self.assertEqual(state.value(command_id), expected)
                    self.assertEqual(state.raw_values[command_id], raw)
                    self.assertTrue(state.is_fresh(command_id))

    def test_tdg_stbh_rejects_signed_malformed_and_oversized_hex(self):
        bad_values = ("-1", "-0x1", "+1", "1.0", "0x", "GG", "NaN", "Inf",
                      "8000 extra", "0x 8000", "100000000", "0x1FFFFFFFF", "9" * 400)
        for command_id in (1023, 1039, 1066):
            for raw in bad_values:
                with self.subTest(command_id=command_id, raw=raw):
                    state = connected_state()
                    self.assertTrue(apply(state, command_id, "0"))
                    prior_stamp = state.updated_at[command_id]
                    self.assertFalse(apply(state, command_id, raw))
                    self.assertEqual(state.raw_values[command_id], raw)
                    self.assertEqual(state.updated_at[command_id], prior_stamp)
                    self.assertIn(command_id, state.invalid_ids)
                    self.assertIsNone(state.value(command_id))
                    self.assertFalse(state.is_fresh(command_id))

    def test_decimal_status_query_is_not_reinterpreted_as_hex(self):
        state = connected_state()
        self.assertTrue(apply(state, 1019, "8000"))
        self.assertTrue(apply(state, 1039, "8000"))
        self.assertEqual(state.value(1019), 8000)
        self.assertEqual(state.value(1039), 32768)
        self.assertFalse(apply(state, 1019, "A000"))
        self.assertIsNone(state.value(1019))

    def test_module_status_fields_reject_fractional_negative_and_overflow_values(self):
        for command_id in (1013, 1015, 1019, 1028, 1029, 1057, 1088, 1089):
            for raw in ("0.5", "-1", "4294967296", "nan", "inf"):
                with self.subTest(command_id=command_id, raw=raw):
                    state = connected_state()
                    self.assertTrue(apply(state, command_id, "0"))
                    self.assertFalse(apply(state, command_id, raw))
                    self.assertEqual(state.raw_values[command_id], raw)
                    self.assertIsNone(state.value(command_id))
                    self.assertFalse(state.is_fresh(command_id))

    def test_status_aliases_refresh_and_invalidate_their_canonical_fact(self):
        for alias, canonical, raw, expected in ((1023, 1039, "100000", 0x100000),
                                                (1029, 1088, "16", 16),
                                                (1057, 1088, "4", 4)):
            with self.subTest(alias=alias, canonical=canonical):
                state = connected_state()
                self.assertTrue(apply(state, alias, raw))
                self.assertEqual(state.value(canonical), expected)
                self.assertTrue(state.is_fresh(canonical))
                self.assertFalse(apply(state, canonical, "ERR unavailable"))
                self.assertFalse(state.is_fresh(alias))
                self.assertIsNone(state.value(canonical))
                self.assertTrue(apply(state, alias, raw))
                self.assertEqual(state.value(canonical), expected)
                self.assertTrue(state.is_fresh(canonical))

    def test_large_decimal_reply_invalidates_without_overflow_exception(self):
        raw = "9" * 400  # Fits a legacy UDP datagram but not a finite float.
        for command_id in (1010, 1021, 1061, 1065):
            with self.subTest(command_id=command_id):
                state = connected_state()
                self.assertTrue(apply(state, command_id, "0"))
                self.assertFalse(apply(state, command_id, raw))
                self.assertEqual(state.raw_values[command_id], raw)
                self.assertIsNone(state.value(command_id))
                self.assertFalse(state.is_fresh(command_id))


if __name__ == "__main__":
    unittest.main()

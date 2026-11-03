"""Regression vectors recovered from the supplied XP 1.6.0 EXE/UIR.

Runtime SetCtrlVal IDs equal UIR stored IDs + 1. Values below are independent
fixtures from binary decoder destinations, not copied from Python's maps.
No original executable, socket, COM port or hardware is used by these tests.
"""
from datetime import datetime, timedelta, timezone
import unittest

from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState, FAULT_LABELS


def reply(cid, value):
    return Reply(cid, str(value), f"<{cid}>{value}")


class OriginalFaultMappingTests(unittest.TestCase):
    def healthy(self, mode="empower"):
        state = DeviceState(connected=True, transport_open=True, pump_mode=mode)
        for cid, value in ((1014, "0 0 0 0"), (1039, "0"), (1066, "0"),
                           (1088, "0"), (1089, "0"), (1068, "1")):
            self.assertTrue(state.apply(reply(cid, value)))
        return state

    def test_empower_vectors_follow_runtime_ids_not_stored_uir_ids(self):
        # _decode_faults 0x40a881..0x40aa71, exact SetCtrlVal destinations.
        vectors = (
            (0, 0x40, 12, "Empower: VSWR"),
            (0, 0x20, 19, "Empower: Q-switch under-temperature"),
            (0, 0x10, 14, "Empower: protection"),
            (0, 0x08, 6, "Empower: overpower"),
            (0, 0x02, 5, "Empower: driver overtemperature"),
            (0, 0x01, 2, "Empower: array overtemperature"),
            (1, 0x80, 23, "Empower: water flow"),
            (1, 0x40, 22, "Empower: cover"),
            (1, 0x20, 17, "Empower: keyswitch"),
            (1, 0x10, 1, "Empower: kill switch"),
            (1, 0x08, 4, "Empower: overvoltage"),
            (1, 0x04, 18, "Empower: overcurrent"),
            (1, 0x02, 13, "Empower: underfrequency"),
            (2, 0x10, 15, "Empower communication"),
            (2, 0x02, 26, "Empower: LBO under-temperature"),
            (2, 0x01, 0, "Empower: array open"),
            (3, 1, 27, "Empower: LBO stability"),
        )
        for word, mask, expected, label in vectors:
            with self.subTest(word=word, mask=hex(mask), label=label):
                state = self.healthy()
                words = [0, 0, 0, 0]
                words[word] = mask
                raw = " ".join(map(str, words))
                self.assertTrue(state.apply(reply(1014, raw)))
                self.assertEqual(FAULT_LABELS[expected], label)
                self.assertEqual([i for i in range(len(FAULT_LABELS)) if state.fault_state(i) is True], [expected])
                self.assertEqual(state.raw_values[1014], raw)
                self.assertTrue(state.fault_active)

    def test_tdg_fault_vectors_come_from_hex_register(self):
        for raw, expected, label in (("0800", 9, "TDG: system"),
                                     ("1000", 16, "TDG: head interlock"),
                                     ("2000", 11, "TDG: user interlock"),
                                     ("4000", 7, "TDG: key interlock"),
                                     ("8000", 8, "TDG: relay")):
            with self.subTest(raw=raw):
                state = self.healthy()
                self.assertTrue(state.apply(reply(1066, raw)))
                self.assertEqual(state.value(1066), int(raw, 16))
                self.assertEqual(FAULT_LABELS[expected], label)
                self.assertEqual([i for i in range(len(FAULT_LABELS)) if state.fault_state(i) is True], [expected])

    def test_tcu_faults_use_decimal_low_byte_bits(self):
        for raw, expected in (("4", 21), ("16", 20)):
            with self.subTest(raw=raw):
                state = self.healthy()
                state.apply(reply(1088, raw))
                self.assertEqual([i for i in range(len(FAULT_LABELS)) if state.fault_state(i) is True], [expected])
                self.assertTrue(state.fault_active)
        state = self.healthy()
        state.apply(reply(1088, "2"))  # status bit, not a proved humidity/TEC fault
        self.assertFalse(state.fault_active)
        self.assertFalse(state.fault_state(20))
        self.assertFalse(state.fault_state(21))

    def test_communication_vectors_are_independent_of_emp_fault_words(self):
        for raw, expected in (("1", 10), ("2", 24), ("4", 15), ("8", 25)):
            with self.subTest(raw=raw):
                state = self.healthy()
                state.apply(reply(1089, raw))
                self.assertEqual([i for i in range(len(FAULT_LABELS)) if state.fault_state(i) is True], [expected])

    def test_empower_communication_combines_both_sources_without_erasing_fault(self):
        for emp, comm in (("0 0 16 0", "0"), ("0 0 0 0", "4"), ("0 0 16 0", "4")):
            with self.subTest(emp=emp, comm=comm):
                state = self.healthy()
                state.apply(reply(1014, emp))
                state.apply(reply(1089, comm))
                self.assertTrue(state.fault_state(15))
        state = self.healthy()
        state.invalid_ids.add(1089)
        self.assertIsNone(state.fault_state(15))
        state.apply(reply(1014, "0 0 16 0"))
        self.assertTrue(state.fault_state(15))

    def test_unknown_indicator_is_not_invented_as_healthy(self):
        self.assertIsNone(self.healthy().fault_state(3))  # LEDCKSUM not mapped by recovered decoder

    def test_lbo_stability_is_entire_scalar_not_byte_mask_or_under_temperature(self):
        state = self.healthy()
        state.apply(reply(1014, "0 0 0 256"))
        self.assertTrue(state.fault_state(27))
        self.assertFalse(state.fault_state(26))
        self.assertEqual(state.fault_words, (0, 0, 0, 256))

    def test_external_profile_excludes_empower_without_excluding_tdg_or_tcu(self):
        state = self.healthy("external")
        state.apply(reply(1014, "127 255 255 256"))
        state.apply(reply(1089, "4"))
        self.assertFalse(state.fault_active)
        self.assertIsNone(state.fault_state(12))
        self.assertIsNone(state.fault_state(15))
        state.apply(reply(1066, "2000"))
        self.assertTrue(state.fault_state(11))
        self.assertTrue(state.fault_active)
        state.apply(reply(1066, "0"))
        state.apply(reply(1088, "16"))
        self.assertTrue(state.fault_state(20))
        self.assertTrue(state.fault_active)

    def test_unknown_tdg_and_communication_bits_remain_faults(self):
        for cid, raw in ((1066, "40000000"), (1089, "16")):
            with self.subTest(cid=cid):
                state = self.healthy("external")
                state.apply(reply(cid, raw))
                self.assertTrue(state.fault_active)

    def test_bwd_detector_and_latch_bits_are_not_phase_lock(self):
        for raw in ("10000", "20000", "100000", "200000"):
            with self.subTest(raw=raw):
                state = self.healthy("external")
                state.apply(reply(1039, raw))
                self.assertTrue(state.fault_active)
        state = self.healthy("external")
        state.apply(reply(1039, "1"))  # HV indication is not a BWD fault
        self.assertFalse(state.fault_active)

    def test_hexadecimal_status_accepts_bare_letters_and_prefix(self):
        for cid in (1039, 1066):
            for raw in ("8000", "a000", "0xA000", "FFFFFFFF"):
                with self.subTest(cid=cid, raw=raw):
                    state = self.healthy()
                    self.assertTrue(state.apply(reply(cid, raw)))
                    self.assertEqual(state.value(cid), int(raw, 16))
                    self.assertEqual(state.raw_values[cid], raw)

    def test_malformed_or_out_of_range_status_is_unavailable(self):
        cases = {1039: ("-1", "+1", "100000000", "a 0", "NaN"),
                 1066: ("-1", "+1", "100000000", "GG"),
                 1088: ("-1", "1.5", "4294967296", "NaN"),
                 1089: ("-1", "1.5", "4294967296", "NaN"),
                 1014: ("0 0 -1 0", "0 0 4294967296 0", "0 0 0", "0 0 1.5 0")}
        for cid, values in cases.items():
            for raw in values:
                with self.subTest(cid=cid, raw=raw):
                    state = self.healthy()
                    self.assertFalse(state.apply(reply(cid, raw)))
                    self.assertFalse(state.is_fresh(cid))
                    self.assertIsNone(state.value(cid))

    def test_stale_or_invalid_fault_source_is_not_shown_as_healthy(self):
        for cid, index in ((1014, 12), (1066, 11), (1088, 20), (1089, 24)):
            with self.subTest(cid=cid):
                state = self.healthy()
                state.updated_at[cid] = datetime.now(timezone.utc) - timedelta(seconds=10)
                self.assertIsNone(state.fault_state(index))
                self.assertFalse(state.faults_known)
                state.apply(reply(cid, "ERR unsupported"))
                self.assertIsNone(state.fault_state(index))


if __name__ == "__main__":
    unittest.main()

"""Offline regressions using actual SASC 1.5.0 replies captured 2026-10-27.

No transport is created and no hardware commands are sent. These tests prove
response decoding, not firmware write semantics or optical operation.
"""
import unittest

from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState, decode_delay


# Distinct values from the read-only audit snapshot through 20:19:44 KST.
OBSERVED_REPLIES = (
    (1000, 'Spectra Physics,SASC,1.5.0'),
    (1015, '0.000000'),
    (1019, '0.000000'),
    (1021, '0'),
    (1021, '1'),
    (1024, '1000.0'),
    (1025, '1'),
    (1028, '0.000000'),
    (1029, '3089.000000'),
    (1030, '18.770000'),
    (1030, '18.790000'),
    (1030, '18.820000'),
    (1030, '18.840000'),
    (1030, '18.860000'),
    (1030, '18.890000'),
    (1030, '18.910000'),
    (1030, '18.930000'),
    (1030, '18.960000'),
    (1030, '18.980000'),
    (1030, '19.000000'),
    (1030, '19.020000'),
    (1030, '19.050000'),
    (1030, '19.070000'),
    (1030, '19.090000'),
    (1030, '19.120000'),
    (1030, '19.140000'),
    (1030, '19.160000'),
    (1031, '3.890000'),
    (1031, '3.920000'),
    (1031, '3.960000'),
    (1031, '4.000000'),
    (1031, '4.040000'),
    (1031, '4.080000'),
    (1031, '4.120000'),
    (1031, '4.150000'),
    (1031, '4.190000'),
    (1031, '4.230000'),
    (1031, '4.500000'),
    (1031, '4.540000'),
    (1031, '4.570000'),
    (1031, '4.610000'),
    (1031, '4.650000'),
    (1031, '4.690000'),
    (1031, '4.730000'),
    (1031, '4.760000'),
    (1031, '4.800000'),
    (1031, '4.840000'),
    (1031, '4.880000'),
    (1031, '4.920000'),
    (1031, '4.950000'),
    (1031, '4.990000'),
    (1031, '5.030000'),
    (1031, '5.070000'),
    (1031, '5.110000'),
    (1031, '5.150000'),
    (1031, '5.180000'),
    (1031, '5.220000'),
    (1031, '5.260000'),
    (1031, '5.340000'),
    (1031, '5.370000'),
    (1031, '5.410000'),
    (1031, '5.450000'),
    (1031, '5.490000'),
    (1031, '5.530000'),
    (1031, '5.570000'),
    (1031, '5.600000'),
    (1031, '5.640000'),
    (1032, '1.000000'),
    (1033, '0'),
    (1034, 'Spectra Physics,HED,����������������,04.001.002'),
    (1036, 'Spectra Physics,TDG-S,sn1021,04.001.003/01.003.092'),
    (1037, 'Spectra-Physics, TCU, 1.5.0'),
    (1038, 'Spectra Physics,SASC,1.5.0'),
    (1039, '0X00330408'),
    (1039, '0X00330409'),
    (1039, '0X00330429'),
    (1039, '0X00334408'),
    (1039, '0X00334428'),
    (1040, '3.399 KV'),
    (1041, '3.139 KV'),
    (1044, ''),
    (1045, 'DELAY 1 ON BWD NENA 85.82'),
    (1046, 'DELAY 2 ON BWD NENA 990.25'),
    (1047, 'DELAY 3 ON NBWD NENA 0.0'),
    (1048, 'DELAY 4 ON NBWD NENA 0.0'),
    (1049, 'DELAY 5 ON NBWD NENA 0.0'),
    (1050, 'EXT'),
    (1051, 'EXT CONT 1000.0'),
    (1052, 'DELAY 0 3100.0'),
    (1053, '1000.0'),
    (1054, 'NEG DUAL ON'),
    (1057, '3089.000000'),
    (1060, '90'),
    (1062, 'Spectra Physics,SASC,1.5.0'),
    (1065, '0.0 MHz'),
    (1066, '0X00334408'),
    (1067, 'EXT'),
    (1068, '0'),
    (1069, ''),
    (1080, 'EXT CONT 1000.0'),
    (1084, '18.910000'),
    (1084, '18.930000'),
    (1084, '18.960000'),
    (1084, '18.980000'),
    (1084, '19.000000'),
    (1084, '19.020000'),
    (1084, '19.050000'),
    (1084, '19.070000'),
    (1085, '3'),
    (1086, '0'),
    (1087, '0'),
    (1088, '3089.000000'),
    (1089, '5'),
    (2016, ''),
)


# Complete read-only capability sweep, including firmware-empty replies and MA.
CAPABILITY_SWEEP_REPLIES = (
    (1000, 'Spectra Physics,SASC,1.5.0'),
    (1021, '0'),
    (1015, '0.000000'),
    (1017, ''),
    (1018, '90'),
    (1019, '0.000000'),
    (1020, ''),
    (1022, ''),
    (1023, '0X00334428'),
    (1024, '1000.0'),
    (1025, '1'),
    (1027, 'NEG DUAL ON'),
    (1028, '0.000000'),
    (1029, '3089.000000'),
    (1030, '18.820000'),
    (1031, '4.040000'),
    (1032, '1.000000'),
    (1033, '0'),
    (1034, 'Spectra Physics,HED,����������������,04.001.002'),
    (1036, 'Spectra Physics,TDG-S,sn1021,04.001.003/01.003.092'),
    (1037, 'Spectra-Physics, TCU, 1.5.0'),
    (1039, '0X00334428'),
    (1040, '3.399 KV'),
    (1041, '3.139 KV'),
    (1042, '0.008 KV'),
    (1043, '0.007 KV'),
    (1044, ''),
    (1045, 'DELAY 1 ON BWD NENA 85.82'),
    (1046, 'DELAY 2 ON BWD NENA 990.25'),
    (1047, 'DELAY 3 ON NBWD NENA 0.0'),
    (1048, 'DELAY 4 ON NBWD NENA 0.0'),
    (1049, 'DELAY 5 ON NBWD NENA 0.0'),
    (1050, 'EXT'),
    (1051, 'EXT CONT 1000.0'),
    (1052, 'DELAY 0 3100.0'),
    (1053, '1000.0'),
    (1054, 'NEG DUAL ON'),
    (1055, '0.008 MA'),
    (1056, '0.009 MA'),
    (1057, '3089.000000'),
    (1058, 'DELAY 1 ON BWD NENA 85.82'),
    (1059, 'DELAY 2 ON BWD NENA 990.25'),
    (1060, '90'),
    (1061, '0'),
    (1063, 'DELAY 1 ON BWD NENA 85.82'),
    (1064, 'DELAY 2 ON BWD NENA 990.25'),
    (1065, '0.0 MHz'),
    (1066, '0X00334408'),
    (1067, 'EXT'),
    (1068, '0'),
    (1069, ''),
    (1079, ''),
    (1080, 'EXT CONT 1000.0'),
    (1083, ''),
    (1084, '18.980000'),
    (1085, '3'),
    (1086, '0'),
    (1087, '0'),
    (1088, '3089.000000'),
    (1089, '5'),
)

def apply(state, cid, value):
    return state.apply(Reply(cid, value, f"<{cid}>{value}"))


def healthy_external_state():
    state = DeviceState(pump_mode="external", connected=True, transport_open=True)
    values = {
        1068: "1", 1019: "0", 1066: "0", 1021: "0", 1087: "0",
        1045: "DELAY 1 OFF BWD ENA 12.5", 1046: "DELAY 2 OFF BWD ENA 37.5",
        1039: "0", 1050: "EXT", 1051: "EXT CONT 1000.0", 1065: "80.0 MHz",
        1088: "0", 1089: "0", 1033: "0", 1044: "0", 1028: "0", 1015: "0", 1069: "0",
    }
    for cid, value in values.items():
        assert apply(state, cid, value), (cid, value)
    return state


class RealFirmwareReplyTests(unittest.TestCase):
    def test_complete_observed_reply_set(self):
        for cid, value in OBSERVED_REPLIES:
            with self.subTest(command_id=cid, value=value):
                state = DeviceState(pump_mode="external")
                # Blank override/opt-out and write ACK values remain unconfirmed.
                self.assertEqual(apply(state, cid, value), bool(value))
                self.assertEqual(state.raw_values[cid], value)

    def test_complete_actual_capability_sweep(self):
        self.assertEqual(len(CAPABILITY_SWEEP_REPLIES), 60)
        empty_ids = set()
        for cid, value in CAPABILITY_SWEEP_REPLIES:
            with self.subTest(command_id=cid, value=value):
                state = DeviceState(pump_mode="external")
                self.assertEqual(apply(state, cid, value), bool(value))
                self.assertEqual(state.raw_values[cid], value)
                if not value:
                    empty_ids.add(cid)
                    self.assertIsNone(state.value(cid))
        self.assertEqual(empty_ids, {1017, 1020, 1022, 1044, 1069, 1079, 1083})

    def test_current_ma_suffix_does_not_invent_ampere_conversion(self):
        for cid, raw, expected in ((1055, "0.008 MA", 0.008), (1056, "0.009 MA", 0.009),
                                   (1055, "0.008", 0.008), (1056, "0.009", 0.009)):
            with self.subTest(cid=cid, raw=raw):
                state = DeviceState()
                self.assertTrue(apply(state, cid, raw))
                self.assertEqual(state.value(cid), expected)
                self.assertEqual(state.raw_values[cid], raw)

    def test_current_wrong_units_nonfinite_and_garbage_are_rejected(self):
        for cid in (1055, 1056):
            for raw in ("0.008 A", "8 uA", "0.008 MA extra", "0.008 MA MA", "nan MA", "inf MA", "1e999 MA"):
                with self.subTest(cid=cid, raw=raw):
                    self.assertFalse(apply(DeviceState(), cid, raw))

    def test_measured_seed_suffix_keeps_mhz_units(self):
        for value, expected in (("80.0 MHz", 80.0), ("0.0 MHz", 0.0), ("79.999mhz", 79.999), ("8.0e1 MHz", 80.0)):
            with self.subTest(value=value):
                state = DeviceState()
                self.assertTrue(apply(state, 1065, value))
                self.assertEqual(state.value(1065), expected)

    def test_voltage_suffix_normalizes_to_existing_gui_volts(self):
        for cid in (1040, 1041, 1042, 1043):
            for value, expected in (("3.399 KV", 3399.0), ("3.139 kV", 3139.0), ("3399 V", 3399.0), ("0.0 KV", 0.0)):
                with self.subTest(cid=cid, value=value):
                    state = DeviceState()
                    self.assertTrue(apply(state, cid, value))
                    self.assertAlmostEqual(state.value(cid), expected)

    def test_bare_voltages_use_firmware_kv_and_seed_keeps_mhz(self):
        for cid, value, expected in ((1065, "80.0", 80.0), (1040, "3.5", 3500.0),
                                     (1041, "3.399", 3399.0), (1042, "0.008", 8.0), (1043, "0.007", 7.0)):
            state = DeviceState()
            self.assertTrue(apply(state, cid, value))
            self.assertAlmostEqual(state.value(cid), expected)

    def test_wrong_units_and_trailing_text_are_rejected(self):
        bad = {1065: ("80 Hz", "80 kHz", "80 MHz extra", "MHz 80", "80 MHz MHz", "1_0 MHz"),
               1040: ("3.399 A", "3.399 MV", "3.399 KV extra", "3.399 KV KV", "KV 3.399")}
        for cid, values in bad.items():
            for value in values:
                with self.subTest(cid=cid, value=value):
                    state = DeviceState()
                    apply(state, cid, "80" if cid == 1065 else "3399")
                    self.assertFalse(apply(state, cid, value))
                    self.assertIsNone(state.value(cid))

    def test_nonfinite_quantities_and_scale_overflow_are_rejected(self):
        for cid, unit in ((1065, "MHz"), (1040, "KV")):
            for number in ("nan", "inf", "-inf", "1e9999"):
                with self.subTest(cid=cid, number=number):
                    self.assertFalse(apply(DeviceState(), cid, number + " " + unit))
        self.assertFalse(apply(DeviceState(), 1040, "1e308 KV"))
        self.assertFalse(apply(DeviceState(), 1040, "1e308"))
        self.assertFalse(apply(DeviceState(), 1040, "9" * 4000))

    def test_compound_trigger_and_operation_update_only_requested_id(self):
        for cid, expected in ((1051, 1), (1080, 0)):
            state = DeviceState()
            self.assertTrue(apply(state, cid, "EXT CONT 1000.0"))
            self.assertEqual(state.value(cid), expected)
            self.assertEqual(set(state.values), {cid})
            self.assertEqual(state.raw_values[cid], "EXT CONT 1000.0")

    def test_compound_mode_variants_are_fully_validated(self):
        for value, source, operation in (("INT CONT 0.0", 0, 0), ("EXT COUNT 10", 1, 1), ("INT COUNT 1 10.0", 0, 2)):
            for cid, expected in ((1051, source), (1080, operation)):
                with self.subTest(cid=cid, value=value):
                    state = DeviceState()
                    self.assertTrue(apply(state, cid, value))
                    self.assertEqual(state.value(cid), expected)

    def test_existing_mode_tokens_and_numeric_enums_remain_valid(self):
        for cid, values in ((1050, {"INT": 0, "EXT": 1, "0": 0, "1.0": 1}),
                            (1051, {"INT": 0, "EXT": 1, "0": 0, "1": 1}),
                            (1067, {"INT": 0, "EXT": 1}),
                            (1080, {"CONT": 0, "COUNT": 1, "COUNT 1": 2, "2": 2})):
            for value, expected in values.items():
                with self.subTest(cid=cid, value=value):
                    state = DeviceState()
                    self.assertTrue(apply(state, cid, value))
                    self.assertEqual(state.value(cid), expected)

    def test_malformed_or_conflicting_mode_fields_are_rejected(self):
        invalid = ("EXT CONT", "EXT INT CONT 1000", "EXT CONT COUNT 1000", "EXT CONT nan",
                   "EXT CONT inf", "EXT CONT 1e999", "EXT CONT -1", "EXT CONT 1000 extra",
                   "EXT SOMETHING 1000", "EXT COUNT 1 10 extra", "3", "0.5")
        for cid in (1051, 1080):
            for value in invalid:
                with self.subTest(cid=cid, value=value):
                    state = DeviceState()
                    self.assertFalse(apply(state, cid, value))
                    self.assertIsNone(state.value(cid))
        self.assertFalse(apply(DeviceState(), 1050, "EXT CONT 1000.0"))

    def test_real_channel_reply_preserves_all_flags_and_delay(self):
        for channel in range(1, 6):
            value = f"DELAY {channel} ON BWD NENA 85.82"
            state = DeviceState()
            self.assertTrue(apply(state, 1044 + channel, value))
            delay = state.delays[channel]
            self.assertEqual((delay.value, delay.switch, delay.bwd, delay.enable), (85.82, "ON", "BWD", "NENA"))

    def test_channel_flag_combinations(self):
        for switch in ("ON", "OFF"):
            for bwd in ("BWD", "NBWD"):
                for enable in ("ENA", "NENA"):
                    delay = decode_delay(f"DELAY 1 {switch} {bwd} {enable} 1e2", expected_channel=1)
                    self.assertEqual((delay.value, delay.switch, delay.bwd, delay.enable), (100.0, switch, bwd, enable))

    def test_legacy_compound_and_bare_delay_conventions_remain_valid(self):
        legacy = decode_delay("OFF BWD ENA DELAY VALUE = 12.5", expected_channel=1)
        self.assertEqual((legacy.value, legacy.switch, legacy.bwd, legacy.enable), (12.5, "OFF", "BWD", "ENA"))
        bare = decode_delay("12.5", expected_channel=2)
        self.assertEqual((bare.value, bare.switch, bare.bwd, bare.enable), (12.5, None, None, None))

    def test_channel_number_must_match_query_including_aliases(self):
        for cid, channel in ((1045, 1), (1046, 2), (1058, 1), (1059, 2), (1063, 1), (1064, 2)):
            with self.subTest(cid=cid):
                state = healthy_external_state()
                self.assertTrue(apply(state, cid, f"DELAY {channel} OFF BWD ENA 12.5"))
                self.assertFalse(apply(state, cid, f"DELAY {3 - channel} OFF BWD ENA 12.5"))
                self.assertIsNone(state.value(1044 + channel))

    def test_malformed_channel_reply_does_not_keep_prior_flags_valid(self):
        values = ("DELAY 1 ON OFF BWD ENA 1", "DELAY 1 ON BWD NBWD ENA 1", "DELAY 1 ON BWD ENA NENA 1",
                  "DELAY 1 ON BWD 1", "DELAY 1 ON BWD ENA", "DELAY 1 ON BWD ENA nan",
                  "DELAY 1 ON BWD ENA inf", "DELAY 1 ON BWD ENA 1e999", "DELAY 1 ON BWD ENA 1 extra",
                  "DELAY 0 ON BWD ENA 1", "DELAY 6 ON BWD ENA 1", "OFF BWD ENA DELAY VALUE = 1 extra")
        for value in values:
            with self.subTest(value=value):
                state = healthy_external_state()
                self.assertFalse(apply(state, 1045, value))
                self.assertIsNone(state.value(1045))
                self.assertIsNone(state.delays[1].value)

    def test_delay_zero_reply_and_bare_value(self):
        for value in ("DELAY 0 3100.0", "3100.0"):
            state = DeviceState()
            self.assertTrue(apply(state, 1052, value))
            self.assertEqual(state.value(1052), 3100.0)
        for value in ("DELAY 1 3100.0", "DELAY 0 nan", "DELAY 0 1e999", "DELAY 0 3100.0 extra"):
            self.assertFalse(apply(DeviceState(), 1052, value))

    def test_empty_override_and_head_optout_are_still_unknown(self):
        for cid in (1044, 1069):
            state = healthy_external_state()
            self.assertTrue(state.is_fresh(cid))
            self.assertFalse(apply(state, cid, ""))
            self.assertIsNone(state.value(cid))
            self.assertFalse(state.is_fresh(cid))
            self.assertTrue(state.external_enable_reason())

    def test_zero_seed_parses_but_never_passes_timing_condition(self):
        state = healthy_external_state()
        self.assertEqual(state.external_timing_reason(), "")
        self.assertTrue(apply(state, 1065, "0.0 MHz"))
        self.assertEqual(state.value(1065), 0.0)
        self.assertIn("positive", state.external_timing_reason())

    def test_nena_is_not_rewritten_to_ena(self):
        state = healthy_external_state()
        self.assertEqual(state.external_enable_reason(), "")
        self.assertTrue(apply(state, 1045, "DELAY 1 ON BWD NENA 85.82"))
        self.assertEqual(state.delays[1].enable, "NENA")
        self.assertIn("PC1", state.external_enable_reason())

    def test_original_fault_register_interpretation_is_preserved(self):
        state = healthy_external_state()
        for cid, raw, expected in ((1039, "0X00330429", 0x00330429), (1066, "0X00334408", 0x00334408),
                                   (1088, "3089.000000", 3089), (1089, "5", 5)):
            self.assertTrue(apply(state, cid, raw))
            self.assertEqual(state.value(cid), expected)
        self.assertTrue(state.fault_active)
        self.assertTrue(state.external_enable_reason())

    def test_bwd_configuration_stays_text_instead_of_invented_fault_mask(self):
        state = DeviceState()
        self.assertTrue(apply(state, 1054, "NEG DUAL ON"))
        self.assertEqual(state.value(1054), "NEG DUAL ON")
        self.assertNotIn(1039, state.values)
        self.assertNotIn(1066, state.values)
        self.assertTrue(apply(state, 1054, "0"))
        self.assertEqual(state.value(1054), 0)
        for raw in ("NEG POS DUAL ON", "NEG DUAL ON OFF", "NEG DUAL ON extra", "UNKNOWN DUAL ON"):
            self.assertFalse(apply(state, 1054, raw))

    def test_blank_write_ack_does_not_confirm_hv_state(self):
        state = DeviceState()
        self.assertFalse(apply(state, 2016, ""))
        self.assertIsNone(state.high_voltage)
        self.assertNotIn(1021, state.values)


if __name__ == "__main__":
    unittest.main()

"""HV integration checks across GUI units, wire replies and simulator dynamics."""

import unittest

from spitfire_control.commands import engineering_argument, format_command
from spitfire_control.state import DeviceState
from spitfire_control.transport import SimulatorTransport


class SimulatorHVUnitsTests(unittest.TestCase):
    def setUp(self):
        self.sim = SimulatorTransport()
        self.sim.connect()
        self.state = DeviceState()

    def tearDown(self):
        self.sim.close()

    def exchange(self, command_id, argument=None):
        reply = self.sim.exchange(format_command(command_id, argument), 1.0)[0]
        self.assertTrue(self.state.apply(reply))
        return reply

    def test_default_setpoints_preserve_650_volts_with_kv_wire_values(self):
        for query_id in (1040, 1041):
            with self.subTest(query_id=query_id):
                reply = self.exchange(query_id)
                self.assertEqual(float(reply.value), 0.65)
                self.assertEqual(self.state.value(query_id), 650.0)
        for query_id in (1042, 1043):
            self.assertEqual(float(self.exchange(query_id).value), 0.0)
            self.assertEqual(self.state.value(query_id), 0.0)
        self.assertEqual(self.exchange(1021).value, "0")

    def test_gui_volts_roundtrip_via_raw_kv_for_both_channels(self):
        for write_id, query_id, volts, wire in (
            (2025, 1040, 3390, "3.39"),
            (2026, 1041, 3400, "3.40"),
        ):
            with self.subTest(write_id=write_id):
                argument = engineering_argument(write_id, volts)
                self.assertEqual(argument, wire)
                self.assertEqual(self.exchange(write_id, argument).value, "OK")
                reply = self.exchange(query_id)
                self.assertEqual(float(reply.value), float(wire))
                self.assertEqual(self.state.value(query_id), volts)
                self.assertEqual(self.state.raw_values[query_id], reply.value)
        self.assertEqual(self.exchange(1021).value, "0")

    def test_programmer_raw_kv_is_not_divided_again(self):
        for write_id, query_id in ((2025, 1040), (2026, 1041)):
            with self.subTest(write_id=write_id):
                self.exchange(write_id, "3.39")
                self.assertIn((write_id, format_command(write_id, "3.39").split("]", 1)[1]),
                              self.sim.command_history)
                self.assertEqual(float(self.exchange(query_id).value), 3.39)
                self.assertEqual(self.state.value(query_id), 3390.0)

    def test_measured_hv_ramps_in_kv_and_state_reports_volts(self):
        self.exchange(2025, engineering_argument(2025, 3390))
        self.exchange(2026, engineering_argument(2026, 3400))
        self.exchange(2017)
        first = float(self.exchange(1042).value)
        self.assertAlmostEqual(first, 3.39 * 0.3)
        self.assertAlmostEqual(self.state.value(1042), 3390 * 0.3)
        for _ in range(50):
            self.exchange(1042)
            self.exchange(1043)
        self.assertAlmostEqual(float(self.state.raw_values[1042]), 3.39, places=6)
        self.assertAlmostEqual(float(self.state.raw_values[1043]), 3.40, places=6)
        self.assertAlmostEqual(self.state.value(1042), 3390.0, places=3)
        self.assertAlmostEqual(self.state.value(1043), 3400.0, places=3)

    def test_synthetic_current_keeps_previous_scale_after_unit_correction(self):
        self.exchange(2017)
        for _ in range(50):
            self.exchange(1042)
        for query_id in (1055, 1056):
            with self.subTest(query_id=query_id):
                self.assertAlmostEqual(float(self.exchange(query_id).value), 0.650, places=6)
                self.assertAlmostEqual(self.state.value(query_id), 0.650, places=6)

    def test_hv_off_ramps_down_without_changing_kv_setpoints(self):
        self.exchange(2025, "3.39")
        self.exchange(2017)
        for _ in range(30):
            self.exchange(1042)
        self.exchange(2016)
        after_off = float(self.exchange(1042).value)
        self.assertGreater(after_off, 0.0)
        self.assertLess(after_off, 3.39)
        for _ in range(50):
            self.exchange(1042)
        self.assertAlmostEqual(self.state.value(1042), 0.0, places=3)
        self.assertEqual(float(self.exchange(1040).value), 3.39)
        self.assertEqual(self.state.value(1040), 3390.0)
        self.assertEqual(float(self.exchange(1055).value), 0.0)
        self.assertEqual(self.exchange(1021).value, "0")


if __name__ == "__main__":
    unittest.main()

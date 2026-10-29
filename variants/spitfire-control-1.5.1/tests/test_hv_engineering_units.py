import unittest
from spitfire_control.commands import engineering_argument, format_command

class HvEngineeringUnitsTests(unittest.TestCase):
    def test_gui_volts_to_legacy_kilovolts(self):
        for cid in (2025, 2026):
            with self.subTest(cid=cid):
                self.assertEqual(engineering_argument(cid, 3390), "3.39")
                self.assertEqual(engineering_argument(cid, 0), "0.00")
    def test_original_two_decimal_precision(self):
        self.assertEqual(engineering_argument(2025, 3399), "3.40")
    def test_raw_programmer_keeps_wire_kilovolts(self):
        self.assertEqual(format_command(2025, "3.399"), "[2025]TDG:HV1:VOLT 3.399")
    def test_invalid_gui_voltage_is_rejected(self):
        for value in ("nan", "inf", "-1", "junk", 1000001):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): engineering_argument(2025, value)
    def test_other_commands_are_not_rescaled(self):
        self.assertEqual(engineering_argument(2046, 80), 80)
        self.assertEqual(engineering_argument(2004, 1000), "100.00")

if __name__ == "__main__": unittest.main()

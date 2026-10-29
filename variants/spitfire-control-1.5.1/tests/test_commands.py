import unittest

from spitfire_control.commands import COMMANDS, Risk, format_command, get_command


class CommandCatalogueTests(unittest.TestCase):
    def test_catalogue_contains_recovered_ranges(self):
        self.assertEqual(len([i for i in COMMANDS if 1000 <= i <= 1089]), 90)
        self.assertEqual(len([i for i in COMMANDS if 2000 <= i <= 2055]), 56)

    def test_exact_known_commands(self):
        self.assertEqual(format_command(1000), "[1000]*idn?")
        self.assertEqual(format_command(1014), "[1014]EMP:FAULT?")
        self.assertEqual(format_command(2017), "[2017]TDG:HV:ON")
        self.assertEqual(format_command(2003, 18.5), "[2003]EMP:DIODE:CURR 18.5")

    def test_newline_in_argument_is_rejected(self):
        with self.assertRaises(ValueError):
            format_command(2003, "1\n[2017]TDG:HV:ON")

    def test_risk_metadata(self):
        self.assertEqual(get_command(1008).risk, Risk.READ)
        self.assertTrue(get_command(2017).dangerous)
        self.assertTrue(get_command(2017).writable)


if __name__ == "__main__":
    unittest.main()


import unittest

from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState


class StateTests(unittest.TestCase):
    def test_numeric_and_text_values(self):
        state = DeviceState(connected=True)
        state.apply(Reply(1007, "18.25", "<1007>18.25"))
        state.apply(Reply(1038, "Controller v1", "<1038>Controller v1"))
        self.assertEqual(state.value(1007), 1.825)
        self.assertEqual(state.value(1038), "Controller v1")
        state.apply(Reply(1039, "0x200000", "<1039>0x200000"))
        self.assertEqual(state.value(1039), 0x200000)

    def test_fault_words(self):
        state = DeviceState(connected=True)
        state.apply(Reply(1014, " 0 4 0 0", "<1014> 0 4 0 0"))
        self.assertEqual(state.fault_words, (0, 4, 0, 0))
        self.assertTrue(state.fault_active)

    def test_write_acknowledgement_does_not_replace_readback(self):
        state = DeviceState(connected=True)
        state.apply(Reply(2017, "OK", "<2017>OK"))
        self.assertIsNone(state.high_voltage)
        state.apply(Reply(1021, "1", "<1021>1"))
        self.assertTrue(state.high_voltage)
        state.apply(Reply(2016, "OK", "<2016>OK"))
        self.assertTrue(state.high_voltage)
        state.apply(Reply(1021, "0", "<1021>0"))
        self.assertFalse(state.high_voltage)

    def test_duplicate_hv_query_updates_dashboard_alias(self):
        state = DeviceState(connected=True)
        state.apply(Reply(1061, "1", "<1061>1"))
        self.assertTrue(state.high_voltage)


if __name__ == "__main__":
    unittest.main()

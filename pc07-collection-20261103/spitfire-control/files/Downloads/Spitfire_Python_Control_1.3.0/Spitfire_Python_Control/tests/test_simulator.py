import unittest

from spitfire_control.commands import format_command
from spitfire_control.transport import SimulatorTransport, TransportError
from spitfire_control.state import decode_delay


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.sim = SimulatorTransport()
        self.sim.connect()

    def tearDown(self):
        self.sim.close()

    def exchange(self, command_id, argument=None):
        return self.sim.exchange(format_command(command_id, argument), 1.0)[0].value

    def test_identity(self):
        self.assertIn("Spitfire", self.exchange(1000))

    def test_setpoint_roundtrip(self):
        self.assertEqual(self.exchange(2003, 22.5), "OK")
        self.assertEqual(float(self.exchange(1009)), 22.5)

    def test_hv_on_off(self):
        self.exchange(2017)
        self.assertEqual(self.exchange(1021), "1")
        self.exchange(2016)
        self.assertEqual(self.exchange(1021), "0")

    def test_output_ramps_after_run(self):
        self.exchange(2003, 20)
        self.exchange(2027)
        values = [float(self.exchange(1008)) for _ in range(8)]
        self.assertGreater(values[-1], values[0])
        self.exchange(2028)

    def test_delay_and_service_settings(self):
        self.exchange(2019, "3 12.5")
        result = decode_delay(self.exchange(1047))
        self.assertEqual(result.value, 12.5)
        self.assertEqual((result.switch, result.bwd, result.enable), ("OFF", "BWD", "ENA"))
        self.exchange(2040, "4.25")
        self.exchange(2045)
        self.assertEqual(float(self.exchange(1073)), 4.25)

    def test_measured_oscillator_copy(self):
        self.sim.set_seed_frequency(80.0)
        original = self.exchange(1024)
        self.exchange(2046, "79.95")
        self.assertEqual(self.exchange(1024), original)
        self.assertEqual(float(self.exchange(1065)), 80.0)

    def test_requires_connection(self):
        self.sim.close()
        with self.assertRaises(TransportError):
            self.exchange(1000)

    def test_invalid_write_does_not_leak_value_error(self):
        with self.assertRaisesRegex(TransportError, "Simulator rejected"):
            self.exchange(2029, "not-a-number")


if __name__ == "__main__":
    unittest.main()

import time
import unittest

from spitfire_control.controller import LaserController
from spitfire_control.transport import SimulatorTransport
from spitfire_control.protocol import Reply


class NamedHardwareSimulator(SimulatorTransport):
    name = "UDP hardware"


class ControllerTests(unittest.TestCase):
    def test_async_query_updates_state(self):
        controller = LaserController(SimulatorTransport(), auto_poll=False, timeout=0.5)
        controller.start()
        deadline = time.monotonic() + 2.0
        while controller.running and 1000 not in controller.state.values and time.monotonic() < deadline:
            time.sleep(0.01)
        controller.stop()
        self.assertIn(1000, controller.state.values)

    def test_hardware_writes_require_arm(self):
        controller = LaserController(NamedHardwareSimulator(), auto_poll=False)
        with self.assertRaises(PermissionError):
            controller.submit(2017)
        controller._state.apply(Reply(1000, "controller", "<1000>controller"))
        controller._state.connected = True
        controller.arm(True)
        controller.submit(2017)
        controller.stop()

    def test_safe_off_allowed_while_disarmed(self):
        controller = LaserController(NamedHardwareSimulator(), auto_poll=False)
        controller.submit(2016)
        controller.submit(2028)
        controller.stop()

    def test_malformed_argument_is_rejected_before_worker(self):
        controller = LaserController(SimulatorTransport(), auto_poll=False)
        with self.assertRaises(ValueError):
            controller.submit(2003, "1\n[2017]TDG:HV:ON")
        self.assertFalse(controller.running)


if __name__ == "__main__":
    unittest.main()

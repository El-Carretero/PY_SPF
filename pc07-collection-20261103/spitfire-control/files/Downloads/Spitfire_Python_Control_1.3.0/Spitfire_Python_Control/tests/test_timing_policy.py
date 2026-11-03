"""External timing policy tests: in-process fixtures, no instrument I/O."""
from dataclasses import asdict
from datetime import timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from spitfire_control.config import AppConfig
from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.profiles import EXTERNAL_REQUIRED_READS
from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState
from spitfire_control.transport import SimulatorTransport


def apply(state, command_id, value):
    value = str(value)
    return state.apply(Reply(command_id, value, f"<{command_id}>{value}"))


def healthy(state):
    state.connected = state.transport_open = True
    for command_id, value in ((1000, "controller"), (1068, "1"),
                              (1019, "0"), (1066, "0"), (1021, "0"), (1087, "0"),
                              (1045, "OFF BWD ENA DELAY VALUE = 0.0"),
                              (1046, "OFF BWD ENA DELAY VALUE = 0.0"),
                              (1039, "0"), (1050, "EXT"), (1051, "EXT"), (1065, "80"),
                              (1088, "0"), (1089, "0"), (1033, "0"), (1044, "0"), (1028, "0"), (1015, "0"), (1069, "0")):
        apply(state, command_id, value)
    return state


class ExternalTimingStateTests(unittest.TestCase):
    def test_external_sources_and_seed_frequency_are_required_monitor_reads(self):
        self.assertTrue({1033, 1044, 1069, 1028, 1015, 1039, 1050, 1051, 1065}.issubset(EXTERNAL_REQUIRED_READS))
        self.assertEqual(len(EXTERNAL_REQUIRED_READS), len(set(EXTERNAL_REQUIRED_READS)))
        state = healthy(DeviceState(pump_mode="external"))
        self.assertEqual(state.external_enable_reason(), "")
        for command_id in EXTERNAL_REQUIRED_READS:
            with self.subTest(command_id=command_id):
                copy = state.copy()
                copy.updated_at[command_id] -= timedelta(seconds=10)
                self.assertTrue(copy.external_enable_reason())

    def test_seed_tolerance_boundaries_accept_and_outside_rejects(self):
        state = healthy(DeviceState(pump_mode="external", external_seed_mhz=80,
                                    external_seed_tolerance_mhz=1))
        for measured in (79, 80, 81):
            apply(state, 1065, measured)
            self.assertEqual(state.external_timing_reason(), "")
        for measured in (78.999, 81.001, 0, -80, "nan", "ERR no oscillator"):
            with self.subTest(measured=measured):
                apply(state, 1065, measured)
                self.assertTrue(state.external_timing_reason())

    def test_invalid_mutated_expectations_fail_closed(self):
        for name, value in (("external_seed_mhz", 0), ("external_seed_tolerance_mhz", 80),
                            ("external_pump_hz", -10), ("external_pump_hz", float("nan"))):
            with self.subTest(name=name, value=value):
                state = healthy(DeviceState(pump_mode="external"))
                setattr(state, name, value)
                self.assertTrue(state.external_enable_reason())

    def test_latched_bwd_status_cannot_be_hidden_by_clear_fault_word(self):
        for raw_status in ("10000", "20000", "100000", "200000", "330000"):
            with self.subTest(raw_status=raw_status):
                state = healthy(DeviceState(pump_mode="external"))
                apply(state, 1039, raw_status)
                self.assertIn("BWD", state.external_enable_reason())

    def test_legacy_profile_does_not_acquire_external_expectations_gate(self):
        state = DeviceState(pump_mode="empower")
        self.assertEqual(state.external_timing_reason(), "")
        self.assertEqual(state.external_enable_reason(), "")


class ExternalTimingControllerTests(unittest.TestCase):
    def setUp(self):
        self.audit_patch = patch("spitfire_control.controller.AuditLog.write")
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.controllers = []
        self.addCleanup(lambda: [controller.stop() for controller in self.controllers])

    def controller(self, **settings):
        simulator = SimulatorTransport(empower_present=False)
        simulator.connect()
        controller = LaserController(simulator, pump_mode="external", auto_poll=False, **settings)
        healthy(controller._state)
        self.controllers.append(controller)
        return controller, simulator

    @staticmethod
    def change(state, command_id, value):
        if value == "stale":
            state.updated_at[command_id] -= timedelta(seconds=10)
        elif value == "missing":
            state.updated_at.pop(command_id, None)
        else:
            apply(state, command_id, value)

    def test_timing_failures_block_enable_submission(self):
        changes = ((1050, "INT"), (1051, "INT"), (1050, 2), (1051, "ERR unsupported"),
                   (1065, 0), (1065, -80), (1065, 70), (1065, "nan"),
                   (1050, "stale"), (1051, "missing"), (1065, "stale"))
        for changed_id, value in changes:
            for command_id, argument in ((2017, None), (2019, "1 ON"), (2019, "2 ON"), (2048, "CONT")):
                with self.subTest(changed_id=changed_id, value=value, command_id=command_id):
                    controller, simulator = self.controller()
                    self.change(controller._state, changed_id, value)
                    with self.assertRaises(PermissionError):
                        controller.submit(command_id, argument)
                    self.assertFalse(simulator.command_history)

    def test_timing_is_rechecked_when_queued_enable_reaches_transport(self):
        for changed_id, value in ((1050, "INT"), (1051, "INT"), (1065, 0), (1065, 82),
                                  (1050, "stale"), (1051, "missing"), (1065, "ERR no signal")):
            for command_id, argument in ((2017, None), (2019, "1 ON"), (2019, "2 ON"), (2048, "CONT")):
                with self.subTest(changed_id=changed_id, value=value, command_id=command_id):
                    controller, simulator = self.controller()
                    controller.submit(command_id, argument)
                    pending = controller._commands.popleft()
                    self.change(controller._state, changed_id, value)
                    controller._execute(pending)
                    self.assertFalse(simulator.command_history)

    def test_retained_module_optouts_and_humidity_override_block_enable_submission(self):
        for changed_id in (1033, 1044, 1069):
            for value in (1, 0.5, "missing", "stale", "ERR unavailable"):
                for command_id, argument in ((2017, None), (2019, "1 ON"), (2048, "CONT")):
                    with self.subTest(changed_id=changed_id, value=value, command_id=command_id):
                        controller, simulator = self.controller()
                        self.change(controller._state, changed_id, value)
                        with self.assertRaises(PermissionError):
                            controller.submit(command_id, argument)
                        self.assertFalse(simulator.command_history)

    def test_retained_module_optouts_and_humidity_override_are_rechecked_at_send_time(self):
        for changed_id in (1033, 1044, 1069):
            for value in (1, 0.5, "missing", "stale", "ERR unavailable"):
                for command_id, argument in ((2017, None), (2019, "2 ON"), (2048, "CONT")):
                    with self.subTest(changed_id=changed_id, value=value, command_id=command_id):
                        controller, simulator = self.controller()
                        controller.submit(command_id, argument)
                        pending = controller._commands.popleft()
                        self.change(controller._state, changed_id, value)
                        controller._execute(pending)
                        self.assertFalse(simulator.command_history)

    def test_source_communication_fault_cannot_be_hidden_by_clear_summary_at_submission(self):
        for changed_id in (1019, 1028, 1015):
            for value in (0x800, "missing", "stale", "ERR unavailable"):
                for command_id, argument in ((2017, None), (2019, "1 ON"), (2048, "CONT")):
                    with self.subTest(changed_id=changed_id, value=value, command_id=command_id):
                        controller, simulator = self.controller()
                        self.assertEqual(controller.state.value(1089), 0)
                        self.change(controller._state, changed_id, value)
                        with self.assertRaises(PermissionError):
                            controller.submit(command_id, argument)
                        self.assertFalse(simulator.command_history)

    def test_source_communication_fault_cannot_be_hidden_by_clear_summary_at_send(self):
        for changed_id in (1019, 1028, 1015):
            for value in (0x800, "missing", "stale", "ERR unavailable"):
                for command_id, argument in ((2017, None), (2019, "2 ON"), (2048, "CONT")):
                    with self.subTest(changed_id=changed_id, value=value, command_id=command_id):
                        controller, simulator = self.controller()
                        controller.submit(command_id, argument)
                        pending = controller._commands.popleft()
                        self.change(controller._state, changed_id, value)
                        self.assertEqual(controller.state.value(1089), 0)
                        controller._execute(pending)
                        self.assertFalse(simulator.command_history)

    def test_timing_source_and_divisor_changes_require_fresh_hv_off(self):
        settings = ((2030, "EXT"), (2031, "EXT"), (2032, 10), (2046, 80), (2020, 1))
        for command_id, argument in settings:
            for condition in ("on", "stale", "unknown"):
                with self.subTest(command_id=command_id, condition=condition):
                    controller, simulator = self.controller()
                    if condition == "on":
                        apply(controller._state, 1021, 1)
                    elif condition == "stale":
                        controller._state.updated_at[1021] -= timedelta(seconds=10)
                    else:
                        apply(controller._state, 1021, "ERR no state")
                    with self.assertRaises(PermissionError):
                        controller.submit(command_id, argument)
                    self.assertFalse(simulator.command_history)
            controller, simulator = self.controller()
            controller.submit(command_id, argument)
            controller._execute(controller._commands.popleft())
            self.assertEqual(simulator.command_history[-1][0], command_id)

    def test_timing_configuration_hv_off_condition_is_rechecked_at_send_time(self):
        for command_id, argument in ((2030, "EXT"), (2031, "EXT"), (2032, 10), (2046, 80), (2020, 1)):
            for condition in ("on", "stale"):
                with self.subTest(command_id=command_id, condition=condition):
                    controller, simulator = self.controller()
                    controller.submit(command_id, argument)
                    pending = controller._commands.popleft()
                    if condition == "on":
                        apply(controller._state, 1021, 1)
                    else:
                        controller._state.updated_at[1021] -= timedelta(seconds=10)
                    controller._execute(pending)
                    self.assertFalse(simulator.command_history)

    def test_ten_hz_expectation_is_metadata_and_not_a_measurement_or_clock_write(self):
        config = AppConfig(pump_mode="external", external_pump_hz=10)
        with patch.object(Path, "read_text", return_value=json.dumps(asdict(config))):
            restored = AppConfig.load(Path("unused.json"))
        self.assertEqual(restored.external_pump_hz, 10)
        controller, simulator = self.controller(external_pump_hz=restored.external_pump_hz)
        self.assertEqual(controller.state.external_pump_hz, 10)
        self.assertIsNone(controller.state.value(1079))
        self.assertFalse(simulator.command_history)
        controller._execute(PendingCommand(1053, None, "test"))
        self.assertEqual(controller.state.value(1053), 1000)  # Independent simulator internal clock.
        self.assertEqual([cid for cid, _ in simulator.command_history], [1053])

    def test_reference_command_cannot_manufacture_measured_seed_frequency(self):
        controller, simulator = self.controller()
        simulator.set_seed_frequency(0.0)
        controller.submit(2046, 80)
        controller._execute(controller._commands.popleft())
        controller._execute(PendingCommand(1065, None, "test"))
        self.assertEqual(controller.state.value(1065), 0)
        self.assertTrue(controller.state.external_timing_reason())
        with self.assertRaises(PermissionError):
            controller.submit(2017)
        self.assertNotIn(2017, [cid for cid, _ in simulator.command_history])


class TimingExpectationValidationTests(unittest.TestCase):
    def test_invalid_timing_targets_rejected_by_config_and_controller(self):
        cases = (("external_seed_mhz", 0), ("external_seed_mhz", float("nan")),
                 ("external_seed_mhz", "80"), ("external_seed_mhz", True),
                 ("external_seed_tolerance_mhz", 0), ("external_seed_tolerance_mhz", 80),
                 ("external_seed_tolerance_mhz", 81), ("external_seed_tolerance_mhz", float("inf")),
                 ("external_pump_hz", 0), ("external_pump_hz", -10),
                 ("external_pump_hz", float("inf")), ("external_pump_hz", "10"),
                 ("external_pump_hz", True), ("external_pump_hz", 10 ** 400))
        for name, value in cases:
            with self.subTest(name=name, value=str(value)[:30]):
                with self.assertRaises(ValueError):
                    AppConfig(**{name: value})
                with self.assertRaises(ValueError):
                    LaserController(SimulatorTransport(), **{name: value})


if __name__ == "__main__":
    unittest.main()

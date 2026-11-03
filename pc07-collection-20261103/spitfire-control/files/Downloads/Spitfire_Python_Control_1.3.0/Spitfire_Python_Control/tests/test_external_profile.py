"""External-pump policy and worker tests. All transports are in-process fixtures."""
from datetime import timedelta
import time
import unittest
from unittest.mock import patch

from spitfire_control.controller import LaserController, PendingCommand
from spitfire_control.profiles import (
    EMPOWER_QUERY_IDS, EXTERNAL_REQUIRED_READS, filter_queries,
    validate_profile_command,
)
from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState
from spitfire_control.transport import SimulatorTransport


class HardwareNamedSimulator(SimulatorTransport):
    """Exercises ARM checks without opening any network/serial transport."""
    name = "Hardware test fixture"


def apply(state, cid, value):
    value = str(value)
    return state.apply(Reply(cid, value, f"<{cid}>{value}"))


def healthy(state, *, optout=1):
    state.connected = state.transport_open = True
    for cid, value in ((1000, "controller"), (1068, optout),
                       (1019, 0), (1066, 0), (1021, 0), (1087, 0),
                       (1039, "0"), (1050, "EXT"), (1051, "EXT"), (1065, "80"),
                       (1088, "0"), (1089, "0"), (1033, "0"), (1044, "0"), (1028, "0"), (1015, "0"), (1069, "0"),
                       (1045, "OFF BWD ENA DELAY VALUE = 0.0"),
                       (1046, "OFF BWD ENA DELAY VALUE = 0.0")):
        apply(state, cid, value)
    return state


class ExternalProfileStateTests(unittest.TestCase):
    def state(self, *, optout=1):
        return healthy(DeviceState(pump_mode="external"), optout=optout)

    def test_empower_fault_words_are_not_external_fault_measurements(self):
        state = self.state()
        apply(state, 1014, "255 255 255 123")
        self.assertEqual(state.effective_fault_words, ())
        self.assertEqual(state.fault_words, (255, 255, 255, 123))
        self.assertEqual(state.raw_values[1014], "255 255 255 123")
        self.assertFalse(state.fault_active)
        self.assertTrue(state.faults_known)
        self.assertEqual(state.external_enable_reason(), "")

    def test_dedicated_tdg_tcu_and_communication_faults_block(self):
        for cid, value in ((1066, "2000"), (1066, "1"), (1088, "4"),
                           (1088, "16"), (1089, "1"), (1089, "2"),
                           (1089, "8"), (1089, "16")):
            with self.subTest(cid=cid, value=value):
                state = self.state()
                apply(state, cid, value)
                self.assertTrue(state.fault_active)
                self.assertTrue(state.external_enable_reason())

    def test_empower_raw_fault_never_hides_a_separate_tdg_fault(self):
        state = self.state()
        apply(state, 1014, "255 255 255 123")
        apply(state, 1066, "2000")
        self.assertEqual(state.effective_fault_words, ())
        self.assertEqual(state.value(1066), 0x2000)
        self.assertTrue(state.fault_active)
        self.assertTrue(state.external_enable_reason())

    def test_stale_optout_blocks_even_with_healthy_dedicated_faults(self):
        state = self.state()
        state.updated_at[1068] -= timedelta(seconds=10)
        self.assertFalse(state.external_opt_out_confirmed)
        self.assertEqual(state.effective_fault_words, ())
        self.assertTrue(state.external_enable_reason())

    def test_only_empower_communication_bit_is_excluded_after_optout(self):
        state = self.state()
        apply(state, 1089, "4")
        self.assertFalse(state.fault_active)
        self.assertEqual(state.external_enable_reason(), "")
        apply(state, 1089, "6")
        self.assertTrue(state.fault_active)
        self.assertTrue(state.external_enable_reason())
        apply(state, 1089, "4")
        apply(state, 1068, "0")
        self.assertTrue(state.fault_active)
        self.assertTrue(state.external_enable_reason())

    def test_external_emission_is_never_inferred_from_empower_status(self):
        state = self.state()
        apply(state, 1013, 1)
        self.assertIsNone(state.laser_on)
        self.assertEqual(state.communication_state("EMPOWER"), "off")

    def test_invalid_or_missing_optout_never_enables(self):
        for value in (0, 2, -1, 1.5, "ERR unsupported", "not supported"):
            with self.subTest(value=value):
                state = self.state()
                apply(state, 1068, value)
                self.assertFalse(state.external_opt_out_confirmed)
                self.assertTrue(state.external_enable_reason())

    def test_missing_or_bad_dedicated_fault_data_is_not_healthy(self):
        for cid in (1039, 1066, 1088, 1089):
            for value in ("ERR unavailable", "invalid", ""):
                with self.subTest(cid=cid, value=value):
                    state = self.state()
                    apply(state, cid, value)
                    self.assertFalse(state.faults_known)
                    self.assertTrue(state.external_enable_reason())

    def test_each_required_read_must_be_recent_for_enabling(self):
        for cid in EXTERNAL_REQUIRED_READS:
            with self.subTest(cid=cid):
                state = self.state()
                self.assertEqual(state.external_enable_reason(), "")
                state.updated_at[cid] -= timedelta(seconds=10)
                self.assertTrue(state.external_enable_reason())

    def test_tdg_communication_fault_and_unrecognized_hv_block(self):
        for cid, value in ((1019, 0x800), (1066, 1), (1021, 2)):
            state = self.state()
            apply(state, cid, value)
            self.assertTrue(state.external_enable_reason())

    def test_retained_tdg_fault_override_blocks_enabling(self):
        for value in (1, 2, "ERR unavailable"):
            with self.subTest(value=value):
                state = self.state()
                apply(state, 1087, value)
                self.assertTrue(state.external_enable_reason())
        apply(state, 1087, 0)
        self.assertEqual(state.external_enable_reason(), "")

    def test_retained_channel_protection_bypass_blocks_enabling(self):
        for cid in (1045, 1046):
            for modes in ("NBWD ENA", "BWD NENA", "NBWD NENA"):
                with self.subTest(cid=cid, modes=modes):
                    state = self.state()
                    apply(state, cid, f"OFF {modes} DELAY VALUE = 0.0")
                    # An unrelated global BWD value is no substitute for each channel.
                    apply(state, 1054, 1)
                    self.assertTrue(state.external_enable_reason())
                    apply(state, cid, "OFF BWD ENA DELAY VALUE = 0.0")
                    self.assertEqual(state.external_enable_reason(), "")

    def test_stale_or_unavailable_channel_mode_readback_blocks_enabling(self):
        for cid in (1045, 1046):
            with self.subTest(cid=cid):
                state = self.state()
                state.updated_at[cid] -= timedelta(seconds=10)
                self.assertTrue(state.external_enable_reason())
                apply(state, cid, "ERR unsupported")
                self.assertTrue(state.external_enable_reason())

    def test_legacy_state_retains_empower_faults_and_emission(self):
        state = healthy(DeviceState())
        apply(state, 1014, "32 0 0 0")
        apply(state, 1013, 1)
        self.assertEqual(state.effective_fault_words, (32, 0, 0, 0))
        self.assertTrue(state.laser_on)


class ExternalControllerTests(unittest.TestCase):
    def setUp(self):
        self.audit_patch = patch("spitfire_control.controller.AuditLog.write")
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.controllers = []

    def tearDown(self):
        for controller in self.controllers:
            controller.stop()

    def controller(self, *, hardware=False, mode="external", **scenario):
        cls = HardwareNamedSimulator if hardware else SimulatorTransport
        sim = cls(empower_present=False, **scenario)
        c = LaserController(sim, pump_mode=mode, auto_poll=False, timeout=.2,
                            log_directory="")
        self.controllers.append(c)
        return c, sim

    def execute(self, c, cid, arg=None):
        c._execute(PendingCommand(cid, arg, "offline test", c._generation))

    def wait_for(self, condition, seconds=3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.01)
        self.fail("Offline fixture did not reach the expected state before the deadline")

    def test_external_initial_poll_and_refresh_exclude_only_empower_queries(self):
        c, _ = self.controller()
        for ids in (c._initial_ids(), c._poll_ids()):
            self.assertFalse(EMPOWER_QUERY_IDS.intersection(ids))
            self.assertNotIn(1014, ids)
        self.assertIn(1068, c._initial_ids())
        c.query_now((1007, 1008, 1014, 1019, 1068, 1077))
        self.assertEqual(tuple(r.command_id for r in c._commands), (1019, 1068))
        c._queue_readbacks((1013, 1021, 1085))
        self.assertNotIn(1013, tuple(r.command_id for r in c._commands))

    def test_connection_is_read_only_and_keeps_required_monitor_without_auto_poll(self):
        c, sim = self.controller()
        c.start()
        self.wait_for(lambda: all(sum(x[0] == cid for x in sim.command_history) >= 2
                                 for cid in EXTERNAL_REQUIRED_READS), seconds=5)
        history = list(sim.command_history)
        self.assertTrue(history)
        self.assertTrue(all(cid < 2000 for cid, _ in history))
        self.assertFalse(EMPOWER_QUERY_IDS.intersection(cid for cid, _ in history))
        self.assertFalse(c.state.external_opt_out_confirmed)
        self.assertIs(c.state.high_voltage, False)

    def test_startup_rechecks_a_queued_enable_before_initial_optout_read(self):
        c, sim = self.controller(hardware=True)
        # Model a request made with previous readbacks just before connection.
        healthy(c._state)
        c.arm(True)
        c.submit(2017)
        c.start()  # The simulator actually boots with opt-out = 0.
        self.wait_for(lambda: any(cid == 1068 for cid, _ in sim.command_history))
        self.assertNotIn(2017, [cid for cid, _ in sim.command_history])
        self.assertFalse(c.state.external_opt_out_confirmed)
        self.assertTrue(all(cid < 2000 for cid, _ in sim.command_history))

    def test_programmer_commands_cannot_bypass_exclusion(self):
        c, sim = self.controller()
        for cid, arg in ((1007, None), (1014, None), (2003, 10), (2005, None), (2006, None),
                         (2027, None), (2028, None), (2034, "EMP:ON"),
                         (2044, None), (2047, 0), (2050, None), (2055, None)):
            with self.subTest(cid=cid), self.assertRaises(PermissionError):
                c.submit(cid, arg, origin="Programmer")
        self.assertEqual(sim.command_history, [])
        self.assertEqual(len(c._commands) + len(c._urgent), 0)

    def test_protection_bypass_and_compound_arguments_are_rejected(self):
        for cid, arg in ((2019, "1 NBWD"), (2019, "1 NENA"), (2033, "0"),
                         (2053, "1"), (2029, "1"), (2024, "1")):
            with self.subTest(cid=cid, arg=arg), self.assertRaises(PermissionError):
                validate_profile_command(cid, arg, "external")
        for cid, arg in ((2036, "1;EMP:ON"), (2017, "1"), (2019, "1 ON EXTRA"),
                         (2019, "1 1001"), (2020, "0"), (2032, "nan")):
            with self.subTest(cid=cid, arg=arg), self.assertRaises(ValueError):
                validate_profile_command(cid, arg, "external")

    def test_send_time_guard_blocks_a_forbidden_request_already_in_queue(self):
        c, sim = self.controller()
        sim.connect()
        self.execute(c, 2005)
        self.execute(c, 2034, "EMP:ON")
        self.assertEqual(sim.command_history, [])

    def test_optout_requires_fresh_hv_off_readback(self):
        c, _ = self.controller()
        with self.assertRaises(PermissionError):
            c.submit(2036, 1)
        healthy(c._state, optout=0)
        apply(c._state, 1021, 1)
        with self.assertRaises(PermissionError):
            c.submit(2036, 1)
        apply(c._state, 1021, 0)
        c._state.updated_at[1021] -= timedelta(seconds=10)
        with self.assertRaises(PermissionError):
            c.submit(2036, 1)
        apply(c._state, 1021, 0)
        c.submit(2036, 1)
        self.assertEqual(c._commands[-1].command_id, 2036)

    def test_optout_hv_condition_is_rechecked_at_send_time(self):
        c, sim = self.controller()
        sim.connect()
        healthy(c._state, optout=0)
        c.submit(2036, 1)
        pending = c._commands.popleft()
        apply(c._state, 1021, 1)
        c._execute(pending)
        self.assertEqual(sim.command_history, [])

    def test_fault_latch_reset_requires_a_recent_hv_off_readback(self):
        for cid in (2018, 2049, 2052):
            with self.subTest(cid=cid):
                c, sim = self.controller()
                with self.assertRaises(PermissionError):
                    c.submit(cid)
                healthy(c._state, optout=0)
                apply(c._state, 1021, 1)
                with self.assertRaises(PermissionError):
                    c.submit(cid)
                apply(c._state, 1021, 0)
                c._state.updated_at[1021] -= timedelta(seconds=10)
                with self.assertRaises(PermissionError):
                    c.submit(cid)
                apply(c._state, 1021, 0)
                c.submit(cid)
                self.assertEqual(c._commands[-1].command_id, cid)
                self.assertEqual(sim.command_history, [])

    def test_fault_latch_reset_rechecks_hv_off_before_transmission(self):
        for cid in (2018, 2049, 2052):
            for changed in ("on", "stale"):
                with self.subTest(cid=cid, changed=changed):
                    c, sim = self.controller()
                    sim.connect()
                    healthy(c._state, optout=0)
                    c.submit(cid)
                    pending = c._commands.popleft()
                    if changed == "on":
                        apply(c._state, 1021, 1)
                    else:
                        c._state.updated_at[1021] -= timedelta(seconds=10)
                    c._execute(pending)
                    self.assertEqual(sim.command_history, [])

    def test_optout_ack_is_not_confirmation_and_never_starts_hv(self):
        c, sim = self.controller()
        sim.connect()
        healthy(c._state, optout=0)
        self.execute(c, 2036, 1)
        self.assertEqual(c.state.value(2036), "OK")
        self.assertFalse(c.state.external_opt_out_confirmed)
        self.assertIn(1068, c.state.pending_readbacks)
        with self.assertRaises(PermissionError):
            c.submit(2017)
        self.execute(c, 1068)
        self.assertTrue(c.state.external_opt_out_confirmed)
        self.assertEqual(c.state.external_enable_reason(), "")
        self.assertIs(c.state.high_voltage, False)
        self.assertNotIn(2017, [x[0] for x in sim.command_history])

    def test_external_hardware_requires_arm_and_explicit_enable(self):
        c, sim = self.controller(hardware=True)
        sim.connect()
        healthy(c._state)
        with self.assertRaises(PermissionError):
            c.submit(2017)
        c.arm(True)
        self.assertEqual(sim.command_history, [])
        c.submit(2017)
        c._execute(c._commands.popleft())
        self.assertEqual(sim.command_history[-1][0], 2017)
        self.execute(c, 1021)
        self.assertIs(c.state.high_voltage, True)
        self.assertIsNone(c.state.laser_on)

    def test_stale_optout_after_enqueue_cancels_hv_before_transmission(self):
        c, sim = self.controller(hardware=True)
        sim.connect()
        healthy(c._state)
        c.arm(True)
        c.submit(2017)
        pending = c._commands.popleft()
        c._state.updated_at[1068] -= timedelta(seconds=10)
        c._execute(pending)
        self.assertEqual(sim.command_history, [])
        self.assertIs(c.state.high_voltage, False)

    def test_channel_enable_also_requires_external_eligibility(self):
        c, sim = self.controller()
        with self.assertRaises(PermissionError):
            c.submit(2019, "1 ON")
        healthy(c._state)
        c.submit(2019, "1 ON")
        sim.connect()
        pending = c._commands.popleft()
        apply(c._state, 1066, "2000")
        c._execute(pending)
        self.assertEqual(sim.command_history, [])

    def test_retained_protection_bypass_is_rechecked_before_hv_transmission(self):
        for cid, value in ((1087, 1),
                           (1045, "OFF NBWD ENA DELAY VALUE = 0.0"),
                           (1046, "OFF BWD NENA DELAY VALUE = 0.0")):
            with self.subTest(cid=cid):
                c, sim = self.controller()
                sim.connect()
                healthy(c._state)
                c.submit(2017)
                pending = c._commands.popleft()
                apply(c._state, cid, value)
                c._execute(pending)
                with self.assertRaises(PermissionError):
                    c.submit(2017)
                self.assertEqual(sim.command_history, [])

    def test_unavailable_empower_fault_query_is_excluded_from_external_profile(self):
        c, sim = self.controller(mixed_faults_supported=False)
        healthy(c._state)
        self.assertNotIn(1014, c._initial_ids())
        c.query_now((1014,))
        self.assertEqual(len(c._commands), 0)
        self.assertEqual(c.state.external_enable_reason(), "")
        self.assertFalse(sim.command_history)

    def test_unsupported_tdg_fault_query_blocks_enable_without_faking_success(self):
        c, sim = self.controller()
        sim.connect()
        healthy(c._state)
        error = Reply(1066, "ERR unsupported", "<1066>ERR unsupported")
        with patch.object(sim, "exchange", return_value=[error]):
            self.execute(c, 1066)
        self.assertIn(1066, c.state.invalid_ids)
        self.assertIn("ERR", c.state.raw_values[1066])
        self.assertFalse(c.state.faults_known)
        with self.assertRaises(PermissionError):
            c.submit(2017)
        self.assertNotIn(2017, [x[0] for x in sim.command_history])

    def test_unsupported_optout_is_visible_and_cannot_enable(self):
        c, sim = self.controller(opt_out_supported=False)
        sim.connect()
        healthy(c._state, optout=0)
        self.execute(c, 2036, 1)
        self.execute(c, 1068)
        self.assertIn("ERR", c.state.raw_values[2036])
        self.assertIn("ERR", c.state.raw_values[1068])
        self.assertFalse(c.state.external_opt_out_confirmed)
        with self.assertRaises(PermissionError):
            c.submit(2017)

    def test_hv_and_channel_off_remain_usable_disarmed_without_optout(self):
        c, sim = self.controller(hardware=True)
        sim.connect()
        c.submit(2016)
        c.submit(2019, "1 OFF")
        c.submit(2019, "2   OFF")
        self.assertEqual(len(c._urgent), 3)
        self.assertEqual(len(c._commands), 0)
        while c._urgent:
            c._execute(c._urgent.popleft())
        self.assertEqual([x[0] for x in sim.command_history], [2016, 2019, 2019])
        self.assertFalse(c.state.armed)

    def test_stop_cancels_queued_enable_and_no_restart_is_replayed(self):
        c, sim = self.controller(hardware=True)
        sim.connect()
        healthy(c._state)
        c.arm(True)
        c.submit(2017)
        stale_request = c._commands.popleft()
        c.submit(2016)
        c._execute(stale_request)
        c._execute(c._urgent.popleft())
        self.assertEqual([x[0] for x in sim.command_history], [2016])
        self.assertFalse(c.state.armed)

    def test_legacy_controller_does_not_filter_empower_or_reject_pump_run(self):
        c, _ = self.controller(mode="empower")
        self.assertIn(1009, c._initial_ids())
        self.assertIn(1013, c._poll_ids())
        c.submit(2027)
        self.assertEqual(c._commands[-1].command_id, 2027)


if __name__ == "__main__":
    unittest.main()

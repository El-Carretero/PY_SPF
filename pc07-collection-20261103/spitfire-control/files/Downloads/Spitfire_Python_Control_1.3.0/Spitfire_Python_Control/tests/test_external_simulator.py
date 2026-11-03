"""Offline scenarios with independently owned Empower, TDG and TCU faults."""
import unittest
from unittest.mock import patch

from spitfire_control.commands import COMMANDS, format_command
from spitfire_control.state import DeviceState, is_error_reply
from spitfire_control.transport import CommandCancelled, SimulatorTransport


class ExternalSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.sim = SimulatorTransport(empower_present=False)
        self.sim.connect()

    def tearDown(self):
        self.sim.close()

    def exchange(self, command_id, argument=None, sim=None):
        return (sim or self.sim).exchange(format_command(command_id, argument), 0.1)[0]

    def connected_sim(self, **kwargs):
        sim = SimulatorTransport(**kwargs)
        sim.connect()
        self.addCleanup(sim.close)
        return sim

    def test_missing_empower_is_never_reported_as_healthy(self):
        for cid, spec in COMMANDS.items():
            if cid < 2000 and spec.text.startswith('EMP:'):
                with self.subTest(cid=cid):
                    reply = self.exchange(cid)
                    self.assertTrue(is_error_reply(reply.value))
                    self.assertIn('not present', reply.value)

    def test_missing_pump_rejects_pump_writes_without_affecting_tdg(self):
        for cid, argument in [(2003, 20), (2005, None), (2006, None),
                              (2027, None), (2028, None), (2044, None)]:
            self.assertTrue(is_error_reply(self.exchange(cid, argument).value))
        self.assertEqual(self.exchange(1021).value, '0')
        self.assertEqual(self.exchange(1068).value, '0')

    def test_tdg_tcu_and_communication_diagnostics_survive_missing_empower(self):
        self.assertIn('Spitfire', self.exchange(1000).value)
        for cid in (1019, 1021, 1066, 1068, 1057, 1088, 1089):
            self.assertEqual(self.exchange(cid).value, '0')
        self.assertTrue(is_error_reply(self.exchange(1014).value))
        self.assertFalse(is_error_reply(self.exchange(1065).value))

    def test_injected_empower_words_do_not_make_absent_pump_query_available(self):
        self.sim.inject_empower_faults((64, 32, 2, 512))
        self.assertEqual(self.sim._values[1014], '64 32 2 512')
        self.assertTrue(is_error_reply(self.exchange(1014).value))
        for cid in (1066, 1057, 1088, 1089):
            self.assertEqual(self.exchange(cid).value, '0')

    def test_connect_and_queries_never_set_optout_or_enable_hv(self):
        for cid in (1000, 1068, 1021, 1066, 1088, 1089):
            self.exchange(cid)
        self.assertTrue(all(cid < 2000 for cid, text in self.sim.command_history))
        self.assertEqual(self.exchange(1068).value, '0')
        self.assertEqual(self.exchange(1021).value, '0')

    def test_explicit_optout_only_changes_optout(self):
        self.sim.inject_empower_faults((64, 32, 0, 0))
        self.sim.inject_tdg_fault(0x80)
        self.sim.inject_tcu_fault(8)
        self.sim.inject_comm_status(4)
        self.assertEqual(self.exchange(2036, 1).value, 'OK')
        self.assertEqual(self.exchange(1068).value, '1')
        self.assertEqual(self.exchange(1021).value, '0')
        self.assertEqual(self.sim._values[1014], '64 32 0 0')
        self.assertEqual(self.exchange(1066).value, '80')
        self.assertEqual(self.exchange(1088).value, '8')
        self.assertEqual(self.exchange(1089).value, '4')
        self.assertTrue(is_error_reply(self.exchange(1013).value))
        self.assertTrue(is_error_reply(self.exchange(1014).value))

    def test_unsupported_optout_is_error_for_read_and_write(self):
        sim = self.connected_sim(empower_present=False, opt_out_supported=False)
        state = DeviceState(connected=True)
        for cid, arg in [(1068, None), (2036, 1)]:
            reply = self.exchange(cid, arg, sim)
            self.assertTrue(is_error_reply(reply.value))
            self.assertFalse(state.apply(reply))
        self.assertEqual(self.exchange(1021, sim=sim).value, '0')

    def test_unavailable_empower_fault_query_does_not_become_zero_faults(self):
        sim = self.connected_sim(empower_present=True, empower_faults_supported=False)
        state = DeviceState(connected=True)
        reply = self.exchange(1014, sim=sim)
        self.assertTrue(is_error_reply(reply.value))
        self.assertIn('Empower fault query unavailable', reply.value)
        self.assertFalse(state.apply(reply))
        self.assertIn(1014, state.invalid_ids)
        self.assertFalse(state.is_fresh(1014))

    def test_legacy_mixed_names_are_aliases_for_empower_only(self):
        sim = self.connected_sim(mixed_faults_supported=False)
        self.assertFalse(sim.empower_faults_supported)
        self.assertTrue(is_error_reply(self.exchange(1014, sim=sim).value))
        sim.mixed_faults_supported = True
        sim.inject_mixed_faults((1, 2, 3, 4))
        self.assertEqual(self.exchange(1014, sim=sim).value, '1 2 3 4')
        for cid in (1066, 1057, 1088):
            self.assertEqual(self.exchange(cid, sim=sim).value, '0')

    def test_persistent_faults_survive_every_reset(self):
        sim = self.connected_sim()
        sim.inject_empower_faults((0x40, 0x20, 0x02, 512))
        sim.inject_tdg_fault(0x40)
        sim.inject_tcu_fault(4)
        sim.inject_comm_status(0x800)
        for cid in (2044, 2049, 2052, 2050, 2055):
            self.assertEqual(self.exchange(cid, sim=sim).value, 'OK')
            self.assertEqual(self.exchange(1014, sim=sim).value, '64 32 2 512')
            self.assertEqual(self.exchange(1066, sim=sim).value, '40')
            self.assertEqual(self.exchange(1057, sim=sim).value, '4')
            self.assertEqual(self.exchange(1088, sim=sim).value, '4')
            self.assertEqual(self.exchange(1089, sim=sim).value, '2048')

    def test_empower_reset_uses_correct_masks_and_preserves_other_modules(self):
        sim = self.connected_sim()
        # Latched, non-active fixture with known and unknown Empower bits.
        sim._values[1014] = '383 511 287 4294967807'
        sim._values[1066] = 0x40
        sim._values[1057] = sim._values[1088] = 2
        sim.inject_comm_status(4)
        self.exchange(2044, sim=sim)
        self.assertEqual(self.exchange(1014, sim=sim).value, '260 257 268 4294967296')
        self.assertEqual(self.exchange(1066, sim=sim).value, '40')
        self.assertEqual(self.exchange(1057, sim=sim).value, '2')
        self.assertEqual(self.exchange(1088, sim=sim).value, '2')
        self.assertEqual(self.exchange(1089, sim=sim).value, '4')

    def test_tdg_reset_cannot_change_any_empower_or_tcu_bit(self):
        sim = self.connected_sim()
        sim._values[1014] = '383 511 287 4294967807'
        sim._values[1066] = 0x40
        sim._values[1057] = sim._values[1088] = 2
        self.exchange(2052, sim=sim)
        self.assertEqual(self.exchange(1014, sim=sim).value, '383 511 287 4294967807')
        self.assertEqual(self.exchange(1066, sim=sim).value, '0')
        self.assertEqual(self.exchange(1057, sim=sim).value, '2')
        self.assertEqual(self.exchange(1088, sim=sim).value, '2')

    def test_tcu_reset_cannot_change_any_empower_or_tdg_bit(self):
        sim = self.connected_sim()
        sim._values[1014] = '383 511 287 4294967807'
        sim._values[1066] = 0x40
        sim._values[1057] = sim._values[1088] = 2
        self.exchange(2049, sim=sim)
        self.assertEqual(self.exchange(1014, sim=sim).value, '383 511 287 4294967807')
        self.assertEqual(self.exchange(1066, sim=sim).value, '40')
        self.assertEqual(self.exchange(1057, sim=sim).value, '0')
        self.assertEqual(self.exchange(1088, sim=sim).value, '0')

    def test_unknown_empower_bits_remain_after_global_reset(self):
        sim = self.connected_sim()
        sim._values[1014] = '260 257 268 4294967296'
        self.exchange(2050, sim=sim)
        self.assertEqual(self.exchange(1014, sim=sim).value, '260 257 268 4294967296')

    def test_communication_status_is_observational_not_resettable(self):
        self.sim.inject_comm_status(0x800)
        for cid in (2049, 2052, 2050, 2055):
            self.exchange(cid)
            self.assertEqual(self.exchange(1089).value, '2048')
        self.sim.inject_comm_status(0)
        self.assertEqual(self.exchange(1089).value, '0')

    def test_tdg_status_and_faults_use_hex_reply_representation(self):
        self.sim.inject_tdg_status(0x20)
        self.sim.inject_tdg_fault(0x100)
        self.assertEqual(self.exchange(1039).value, '20')
        self.assertEqual(self.exchange(1066).value, '100')
        self.exchange(2052)
        self.assertEqual(self.exchange(1039).value, '20')
        self.assertEqual(self.exchange(1066).value, '100')

    def test_cancelled_send_has_no_history_or_write_effect(self):
        def cancel(send):
            raise CommandCancelled('cancelled before send')
        with self.assertRaises(CommandCancelled):
            self.sim.exchange(format_command(2036, 1), 0.1, send_guard=cancel)
        self.assertEqual(self.sim.command_history, [])
        self.assertEqual(self.exchange(1068).value, '0')

    def test_injection_rejects_malformed_fault_values(self):
        for words in [(0, 0, 0), (0, 0, 0, -1), (0, 0, 0, 1.5), (0, 0, 0, True)]:
            with self.assertRaises(ValueError):
                self.sim.inject_empower_faults(words)
        for method in (self.sim.inject_tdg_fault, self.sim.inject_tcu_fault,
                       self.sim.inject_comm_status, self.sim.inject_tdg_status):
            for value in (-1, 1.5, True):
                with self.assertRaises(ValueError):
                    method(value)

    def test_seed_fixture_stays_at_missing_or_out_of_range_frequency(self):
        for mhz in (0, 40, 78.9, 80, 81.1, 90):
            self.sim.set_seed_frequency(mhz)
            for cid in (1065, 1000, 1088, 1065, 1065):
                reply = self.exchange(cid)
                if cid == 1065:
                    self.assertEqual(float(reply.value), mhz)

    def test_oscillator_reference_write_cannot_create_observed_seed_clock(self):
        before_1024 = self.exchange(1024).value
        self.sim.set_seed_frequency(0)
        self.assertEqual(self.exchange(2046, 79.95).value, 'OK')
        self.assertEqual(self.sim._osc_reference_mhz, 79.95)
        self.assertEqual(float(self.exchange(1065).value), 0)
        self.assertEqual(self.exchange(1024).value, before_1024)
        self.sim.set_seed_frequency(82)
        self.exchange(2046, 80)
        self.assertEqual(float(self.exchange(1065).value), 82)

    def test_seed_fixture_rejects_invalid_frequencies(self):
        for mhz in (-1, float('nan'), float('inf'), -float('inf'), True, None, 'invalid'):
            with self.assertRaises(ValueError):
                self.sim.set_seed_frequency(mhz)
        self.assertEqual(float(self.exchange(1065).value), 80)

    def test_simulator_never_opens_sockets(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            sim = SimulatorTransport(empower_present=False)
            sim.connect()
            try:
                self.assertIn('Spitfire', self.exchange(1000, sim=sim).value)
            finally:
                sim.close()


if __name__ == '__main__':
    unittest.main()

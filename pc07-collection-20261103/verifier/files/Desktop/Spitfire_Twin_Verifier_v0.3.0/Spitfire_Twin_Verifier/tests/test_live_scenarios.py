"""Real loopback UDP checks for synthetic scenario/capture integration."""
import json
import socket
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from spitfire_twin_verifier.compare import compare_transactions
from spitfire_twin_verifier.model import ResponseProfile, VirtualSpitfire
from spitfire_twin_verifier.protocol import decode_replies, encode_commands
from spitfire_twin_verifier.records import CaptureStore
from spitfire_twin_verifier.server import ServerError, VirtualDeviceServer


class LiveScenarioTests(unittest.TestCase):
    def setUp(self):
        self.capture = CaptureStore()
        self.device = VirtualSpitfire()
        self.clients = []
        labels = {}
        for label in ("XP", "PY"):
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.bind(("127.0.0.1", 0))
            client.settimeout(2)
            labels[f"127.0.0.1:{client.getsockname()[1]}"] = label
            self.clients.append(client)
        self.server = VirtualDeviceServer("127.0.0.1", 0, self.device, self.capture, labels)

    def tearDown(self):
        self.server.stop()
        for client in self.clients:
            client.close()

    def start(self, scenario="interlock_open", clock="manual"):
        self.server.set_scenario(scenario, clock=clock)
        self.server.start()

    def wait_for(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.002)
        self.fail("Timed out waiting for loopback server/capture condition")

    def exchange(self, index=0, line="[1066]TDG:STBHFLT?"):
        count = len(self.capture.transactions())
        client = self.clients[index]
        client.sendto(encode_commands([line]), self.server.local_address)
        data, _ = client.recvfrom(4096)
        self.wait_for(lambda: len(self.capture.transactions()) > count)
        return decode_replies(data)[0]

    def test_manual_interlock_fixture_replies_raw_hex_and_records_provenance(self):
        self.start()
        self.server.advance_scenario(50)
        self.assertEqual(self.exchange().value, "4000")
        tx = self.capture.transactions()[-1]
        state = json.loads(tx.scenario_state_json)
        self.assertEqual(tx.scenario, "interlock_open")
        self.assertEqual(tx.scenario_time_ms, 50)
        self.assertEqual(tx.scenario_phase, 4)
        self.assertEqual(state["evidence"], "synthetic_policy")
        self.assertIn("interlock_open", state["latched_faults"])
        self.assertEqual(self.capture.snapshot().metadata["physical_validation"], "UNVERIFIED")

    def test_reset_clears_engines_epochs_time_and_capture(self):
        self.start()
        self.server.advance_scenario(50)
        self.assertEqual(self.exchange().value, "4000")
        previous_id = self.capture.session_id
        self.assertTrue(self.server._scenario_clients)
        self.server.reset_session()
        self.assertNotEqual(self.capture.session_id, previous_id)
        self.assertEqual(self.server._scenario_clients, {})
        self.assertEqual(self.server._scenario_manual_ms, 0)
        self.assertEqual(self.capture.transactions(), [])
        self.assertEqual(self.exchange().value, "0")
        self.assertEqual(self.capture.transactions()[-1].scenario_time_ms, 0)
        self.assertTrue(self.server.running)

    def test_realtime_epochs_start_independently_on_first_client_packet(self):
        clock = {"now": 100.0}
        with patch("spitfire_twin_verifier.server.time", SimpleNamespace(perf_counter=lambda: clock["now"])):
            self.start(clock="realtime")
            self.assertEqual(self.exchange(0).value, "0")
            clock["now"] = 100.06
            self.assertEqual(self.exchange(0).value, "4000")
            self.assertEqual(self.exchange(1).value, "0")
            txs = self.capture.transactions()
            self.assertAlmostEqual(txs[1].scenario_time_ms, 60, places=6)
            self.assertEqual(txs[2].scenario_time_ms, 0)
            self.assertNotEqual(self.server._scenario_clients["XP"][1], self.server._scenario_clients["PY"][1])
            self.server.reset_session()
            clock["now"] = 200.0
            self.assertEqual(self.exchange(0).value, "0")
            self.assertEqual(self.server._scenario_clients["XP"][1], 200.0)
            self.server.stop()

    def test_changing_scenario_while_running_is_blocked(self):
        self.start()
        with self.assertRaises(ServerError):
            self.server.set_scenario("missing_trigger")
        with self.assertRaises(ServerError):
            self.server.set_scenario(None)
        self.assertEqual(self.server._scenario_spec["id"], "interlock_open")
        self.assertEqual(self.exchange().value, "0")

    def test_pending_response_retains_request_phase_after_manual_advance(self):
        self.device.set_profile(ResponseProfile(delay_ms={1066: 200}))
        self.start()
        self.server.advance_scenario(50)
        self.clients[0].sendto(encode_commands(["[1066]TDG:STBHFLT?"]), self.server.local_address)
        self.wait_for(lambda: bool(self.capture.snapshot().pending))
        self.server.advance_scenario(150)
        raw, _ = self.clients[0].recvfrom(4096)
        self.assertEqual(decode_replies(raw)[0].value, "4000")
        self.wait_for(lambda: len(self.capture.transactions()) == 1)
        tx = self.capture.transactions()[0]
        self.assertEqual(tx.scenario_time_ms, 50)
        self.assertEqual(tx.scenario_phase, 4)
        self.assertFalse(json.loads(tx.scenario_state_json)["signals"]["interlock_closed"])
        self.assertEqual(self.exchange().value, "0")
        self.assertEqual(self.capture.transactions()[-1].scenario_time_ms, 150)
        self.assertTrue(json.loads(self.capture.transactions()[-1].scenario_state_json)["signals"]["interlock_closed"])

    def test_same_wire_value_at_different_phase_is_not_match(self):
        self.start("trigger_jitter")
        left = self.exchange(0, "[1031]ECU:HUM?")
        self.server.advance_scenario(102, client_key="PY")
        right = self.exchange(1, "[1031]ECU:HUM?")
        self.assertEqual(left.value, right.value)
        self.assertEqual(self.capture.transactions()[0].profile_json, self.capture.transactions()[1].profile_json)
        result = compare_transactions(self.capture.snapshot(), "XP", "PY", ignore_polling=True)
        self.assertEqual(result.verdict, "DIFFERENT")
        self.assertEqual(result.semantic_verdict, "DIFFERENT")
        self.assertEqual(result.rows[0].status, "SCENARIO_PHASE_DIFF")

    def test_matching_wire_and_phase_keeps_gui_and_physical_unverified(self):
        self.start()
        self.server.advance_scenario(50)
        self.exchange(0)
        self.exchange(1)
        result = compare_transactions(self.capture.snapshot(), "XP", "PY")
        self.assertEqual(result.content_verdict, "MATCH")
        self.assertEqual(result.verdict, "OBSERVATION_REQUIRED")
        self.assertEqual(result.gui_verdict, "NOT_CHECKED")
        self.assertEqual(self.capture.snapshot().metadata["xp_runtime_validation"], "UNVERIFIED")

    def test_server_continues_after_scenario_end(self):
        self.start()
        for target in (1000, 2000):
            self.server.advance_scenario(target)
            self.assertEqual(self.exchange().value, "0")
            self.assertTrue(self.server.running)
            tx = self.capture.transactions()[-1]
            self.assertEqual(tx.scenario_time_ms, 200)
            self.assertTrue(json.loads(tx.scenario_state_json)["finished"])

    def test_manual_clock_rejects_nonfinite_and_wrong_types_without_crash(self):
        self.start()
        for bad in (float("nan"), float("inf"), -1, True, "50"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.server.advance_scenario(bad)
        self.assertEqual(self.exchange().value, "0")
        self.assertTrue(self.server.running)

    def test_manual_advance_rejected_for_realtime_or_no_scenario(self):
        with self.assertRaises(ServerError):
            self.server.advance_scenario(1)
        self.start(clock="realtime")
        with self.assertRaises(ServerError):
            self.server.advance_scenario(1)

    def test_global_manual_advance_preflights_all_client_clocks_atomically(self):
        self.start()
        self.exchange(1)  # Insert PY first so an unsafe loop partially updates it.
        self.exchange(0)
        self.server.advance_scenario(100, client_key="XP")
        before = {key: engine.snapshot() for key, (engine, _) in self.server._scenario_clients.items()}
        with self.assertRaises(ValueError):
            self.server.advance_scenario(50)
        after = {key: engine.snapshot() for key, (engine, _) in self.server._scenario_clients.items()}
        self.assertEqual(before, after)

    def test_extreme_integer_rejected_as_validation_error(self):
        self.start()
        with self.assertRaises(ValueError):
            self.server.advance_scenario(10**10000)
        self.assertTrue(self.server.running)


if __name__ == "__main__":
    unittest.main()

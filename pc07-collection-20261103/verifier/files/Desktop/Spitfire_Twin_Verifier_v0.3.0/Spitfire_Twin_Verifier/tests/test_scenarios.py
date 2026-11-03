import copy
import json
from pathlib import Path
import tempfile
import unittest

from spitfire_twin_verifier.scenarios import (
    ScenarioEngine, ScenarioError, list_scenarios, load_scenario, run_scenario,
)


def fixture(events=(), assertions=(), duration=500, **kwargs):
    return dict(schema_version=1, id="test", name="Test", description="Synthetic test",
                duration_ms=duration, events=list(events), assertions=list(assertions), **kwargs)


def event(at, kind, **kwargs):
    return dict(at_ms=at, type=kind, **kwargs)


class ScenarioTests(unittest.TestCase):
    def test_all_builtins_have_assertions_pass_and_no_physical_claim(self):
        items = list_scenarios()
        self.assertGreaterEqual(len(items), 12)
        for item in items:
            with self.subTest(item=item["id"]):
                result = run_scenario(item["id"])
                self.assertEqual(result["model_verdict"], "PASS")
                self.assertTrue(result["assertions"])
                self.assertEqual(result["client_equivalence"], "UNVERIFIED")
                self.assertEqual(result["physical_validation"], "UNVERIFIED")
                self.assertEqual(result["evidence"], "synthetic_policy")

    def test_replay_is_exactly_deterministic(self):
        self.assertEqual(run_scenario("seed_loss_recovery"), run_scenario("seed_loss_recovery"))

    def test_clients_have_independent_clocks_and_state(self):
        left = ScenarioEngine("seed_loss_recovery")
        right = ScenarioEngine("seed_loss_recovery")
        left.advance_to(60)
        right.advance_to(10)
        self.assertIn("seed_missing", left.snapshot()["active_faults"])
        self.assertEqual(right.snapshot()["active_faults"], [])
        self.assertEqual(right.wire_effects()["overrides"], {})

    def test_no_assertions_is_unverified_not_pass(self):
        self.assertEqual(run_scenario(fixture())["model_verdict"], "UNVERIFIED")

    def test_failed_assertion_is_fail(self):
        result = run_scenario(fixture(assertions=[dict(at_ms=0, path="armed", expected=True)]))
        self.assertEqual(result["model_verdict"], "FAIL")

    def test_stable_order_at_equal_timestamps(self):
        first = event(0, "signals", values={"pump_ready": False})
        second = event(0, "signals", values={"pump_ready": True})
        engine = ScenarioEngine(fixture([first, second]))
        state = engine.advance_to(0)
        self.assertTrue(state["signals"]["pump_ready"])
        self.assertIn("pump_not_ready", state["latched_faults"])
        self.assertEqual(state["phase"], 2)

    def test_watchdog_expires_without_new_input(self):
        engine = ScenarioEngine(fixture([event(0, "arm"), event(0, "trigger")]))
        self.assertTrue(engine.advance_to(249)["armed"])
        state = engine.advance_to(250)
        self.assertFalse(state["armed"])
        self.assertIn("trigger_missing", state["latched_faults"])
        self.assertEqual(engine.transitions[-1]["time_ms"], 250)

    def test_trigger_exactly_at_deadline_wins(self):
        engine = ScenarioEngine(fixture([event(0, "arm"), event(0, "trigger"), event(250, "trigger")],
                                        policy={"expected_trigger_hz": 4}))
        self.assertTrue(engine.advance_to(250)["armed"])
        self.assertNotIn("watchdog_timeout", [e["event"] for e in engine.transitions])

    def test_late_trigger_cannot_erase_timeout_history(self):
        engine = ScenarioEngine(fixture([event(0, "arm"), event(0, "trigger"), event(251, "trigger")],
                                        policy={"expected_trigger_hz": 4, "max_jitter_us": 2000}))
        state = engine.advance_to(251)
        self.assertFalse(state["armed"])
        self.assertIn("trigger_missing", state["latched_faults"])
        self.assertIn("watchdog_timeout", [e["event"] for e in engine.transitions])

    def test_repeated_arm_cannot_extend_watchdog(self):
        engine = ScenarioEngine(fixture([event(0, "arm"), event(100, "arm"), event(200, "arm")]))
        self.assertIn("trigger_missing", engine.advance_to(250)["latched_faults"])

    def test_recovery_does_not_auto_arm(self):
        engine = ScenarioEngine("seed_loss_recovery")
        state = engine.advance_to(150)
        self.assertTrue(state["signals"]["seed_present"])
        self.assertFalse(state["armed"])
        self.assertTrue(state["latched_faults"])
        self.assertFalse(engine.advance_to(200)["armed"])
        self.assertTrue(engine.advance_to(210)["armed"])

    def test_reset_while_signal_bad_is_denied(self):
        engine = ScenarioEngine(fixture([event(0, "reset"), event(1, "arm")],
                                        initial_signals={"interlock_closed": False}))
        state = engine.advance_to(1)
        self.assertFalse(state["reset_accepted"])
        self.assertFalse(state["armed"])
        self.assertIn("interlock_open", state["active_faults"])

    def test_beyond_duration_clamps_and_remains_stable(self):
        engine = ScenarioEngine("nominal_external_10hz")
        first = engine.advance_to(500)
        second = engine.advance_to(600)
        third = engine.advance_to(10_000)
        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(first["time_ms"], 400)
        self.assertTrue(first["finished"])

    def test_time_reversal_and_nonfinite_rejected(self):
        engine = ScenarioEngine(fixture())
        engine.advance_to(1)
        for val in (0, float("nan"), float("inf"), True, "2", 10**10000):
            with self.subTest(value=type(val).__name__), self.assertRaises(ScenarioError):
                engine.advance_to(val)

    def test_abstract_fault_does_not_invent_wire_bits(self):
        engine = ScenarioEngine("thermal_flow_hv")
        engine.advance_to(50)
        self.assertEqual(engine.wire_effects()["overrides"], {})
        self.assertEqual(engine.wire_effects()["drop_ids"], [])

    def test_explicit_seed_fixture_only_uses_measured_seed_id(self):
        engine = ScenarioEngine("seed_loss_recovery")
        engine.advance_to(50)
        self.assertEqual(engine.wire_effects()["overrides"], {1065: "0"})

    def test_wire_effects_clear_and_copy(self):
        engine = ScenarioEngine("communication_loss")
        engine.advance_to(50)
        effects = engine.wire_effects()
        self.assertEqual(effects["overrides"], {1089: "2"})
        self.assertEqual(effects["request_drop_ids"], [2017])
        effects["overrides"][1089] = "999"
        self.assertEqual(engine.wire_effects()["overrides"][1089], "2")
        engine.advance_to(150)
        self.assertEqual(engine.wire_effects()["delay_ms"], {})
        self.assertEqual(engine.wire_effects()["request_drop_ids"], [])

    def test_null_override_removes_one_override(self):
        engine = ScenarioEngine(fixture([
            event(0, "wire", wire={"overrides": {"1065": "0", "1089": "2"}}),
            event(1, "wire", wire={"overrides": {"1065": None}}),
        ]))
        engine.advance_to(1)
        self.assertEqual(engine.wire_effects()["overrides"], {1089: "2"})

    def test_snapshot_does_not_share_mutable_state(self):
        engine = ScenarioEngine(fixture())
        snap = engine.snapshot()
        snap["signals"]["pump_ready"] = False
        snap["active_faults"].append("made_up")
        self.assertTrue(engine.snapshot()["signals"]["pump_ready"])
        self.assertEqual(engine.snapshot()["active_faults"], [])

    def test_injected_event_is_current_time_only(self):
        engine = ScenarioEngine(fixture([event(0, "arm")]))
        state = engine.inject(event(0, "signals", values={"hv_ok": False}))
        self.assertFalse(state["armed"])
        self.assertEqual(state["phase"], 2)
        with self.assertRaises(ScenarioError):
            engine.inject(event(10, "arm"))

    def test_unknown_fields_rejected_at_all_levels(self):
        variants = [
            fixture(unrecognized=True),
            fixture(policy={"invented": 1}),
            fixture(initial_signals={"invented": True}),
            fixture([dict(at_ms=0, type="arm", invented=1)]),
            fixture([event(0, "wire", wire={"invented": []})]),
            fixture(assertions=[dict(at_ms=0, path="armed", expected=False, invented=1)]),
        ]
        for raw in variants:
            with self.subTest(raw=raw), self.assertRaises(ScenarioError):
                load_scenario(raw)

    def test_invalid_event_shapes_rejected(self):
        variants = [
            fixture([event(0, "signals", values={"pump_ready": 1})]),
            fixture([event(0, "arm", phase_us=10)]),
            fixture([event(0, [])]),
            fixture([event(0, "trigger", phase_us=float("inf"))]),
            fixture([event(0, "signals", values={"seed_frequency_mhz": -1})]),
            fixture([event(501, "arm")]),
            fixture([event(1, "arm"), event(0, "disarm")]),
        ]
        for raw in variants:
            with self.subTest(raw=repr(raw)), self.assertRaises(ScenarioError):
                load_scenario(raw)

    def test_invalid_wire_ids_and_values_rejected(self):
        effects = [
            {"overrides": {"2017": "1"}}, {"overrides": {"9999": "1"}},
            {"overrides": {"01065": "1"}}, {"overrides": {"1065": "1\n2"}},
            {"overrides": {"1065": "한글"}}, {"overrides": {"1065": 1}},
            {"drop_ids": [1065, 1065]}, {"drop_ids": [True]},
            {"drop_ids": [1065.1]}, {"delay_ms": {"1065": -1}},
            {"delay_ms": {"1065": float("nan")}},
        ]
        for effects_item in effects:
            with self.subTest(effects=effects_item), self.assertRaises(ScenarioError):
                load_scenario(fixture([event(0, "wire", wire=effects_item)]))

    def test_invalid_policy_rejected(self):
        policies = [{"expected_trigger_hz": 0}, {"trigger_timeout_ms": 0},
                    {"seed_tolerance_mhz": -1}, {"rate_tolerance_fraction": 2},
                    {"expected_seed_mhz": float("nan")}]
        for policy in policies:
            with self.subTest(policy=policy), self.assertRaises(ScenarioError):
                load_scenario(fixture(policy=policy))

    def test_invalid_assertion_rejected(self):
        assertions = [dict(at_ms=0, path="__class__", expected=0),
                      dict(at_ms=0, path=[], expected=0),
                      dict(at_ms=0, path="armed", op=[], expected=False),
                      dict(at_ms=0, path="armed", expected=float("nan")),
                      dict(at_ms=0, path="armed"),
                      dict(at_ms=501, path="armed", expected=False)]
        for assertion in assertions:
            with self.subTest(assertion=assertion), self.assertRaises(ScenarioError):
                load_scenario(fixture(assertions=[assertion]))

    def test_comparison_type_error_is_failed_assertion(self):
        result = run_scenario(fixture(assertions=[dict(at_ms=0, path="last_trigger_ms", op="gt", expected=0)]))
        self.assertEqual(result["model_verdict"], "FAIL")

    def test_bool_not_equal_numeric_one(self):
        result = run_scenario(fixture([event(0, "arm")], assertions=[dict(at_ms=0, path="armed", expected=1)]))
        self.assertEqual(result["model_verdict"], "FAIL")

    def test_json_roundtrip_path_and_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8-sig")
            self.assertEqual(load_scenario(path)["id"], "test")

    def test_duplicate_json_field_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom.json"
            path.write_text('{"id":"x","id":"y"}', encoding="utf-8")
            with self.assertRaises(ScenarioError):
                load_scenario(path)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom.json"
            path.write_text('{"duration_ms":NaN}', encoding="utf-8")
            with self.assertRaises(ScenarioError):
                load_scenario(path)

    def test_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "custom.json"
            path.write_text(" " * 2_000_001, encoding="utf-8")
            with self.assertRaises(ScenarioError):
                load_scenario(path)

    def test_missing_name_and_traversal_rejected(self):
        for name in ("not_a_builtin", "../not_a_builtin", "x/y", ""):
            with self.subTest(name=name), self.assertRaises(ScenarioError):
                load_scenario(name)

    def test_schema_version_bool_is_not_one(self):
        raw = fixture()
        raw["schema_version"] = True
        with self.assertRaises(ScenarioError):
            load_scenario(raw)


if __name__ == "__main__":
    unittest.main()

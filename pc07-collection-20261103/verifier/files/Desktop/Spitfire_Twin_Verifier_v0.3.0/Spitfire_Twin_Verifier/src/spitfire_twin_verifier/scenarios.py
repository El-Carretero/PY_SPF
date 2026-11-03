"""Deterministic event fixtures; NOT a certified Spitfire hardware simulator.

All safety behavior below is an explicitly synthetic policy. Wire effects are
opt-in fixtures, never inferred status-bit mappings. A model test passing is
not evidence that either client or physical equipment passed that test.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

from .catalog import COMMANDS

SCHEMA_VERSION = 1
MAX_TIME_MS = 86_400_000
MAX_EVENTS = 10_000
MAX_FILE_BYTES = 2_000_000
DATA_DIRECTORY = Path(__file__).with_name("data") / "scenarios"
LIMITATIONS = [
    "Synthetic policy fixture, not measured or certified Spitfire firmware behavior.",
    "No physical laser, electrical edge, energy, or optical pulse simulation.",
    "Model assertions do not prove XP/Python client reactions or GUI alarms.",
    "Wire overrides are explicit synthetic stimuli; no automatic fault-bit causation is claimed.",
    "Virtual time is deterministic; live UDP wall-clock scheduling is not nanosecond timing.",
]
SIGNAL_DEFAULTS = {
    "seed_present": True, "seed_frequency_mhz": 80.0,
    "pump_present": True, "pump_ready": True,
    "interlock_closed": True, "temperature_ok": True,
    "flow_ok": True, "hv_ok": True, "communication_ok": True,
}
POLICY_DEFAULTS = {
    "expected_seed_mhz": 80.0, "seed_tolerance_mhz": 1.0,
    "expected_trigger_hz": 10.0, "trigger_timeout_ms": 250.0,
    "max_jitter_us": 1000.0, "max_phase_slip_us": 100.0,
    "rate_tolerance_fraction": 0.05,
}
BOOL_SIGNALS = set(SIGNAL_DEFAULTS) - {"seed_frequency_mhz"}
STATE_PATHS = {
    "time_ms", "duration_ms", "finished", "phase", "processed_events",
    "armed", "inhibited", "active_faults", "latched_faults",
    "trigger_count", "accepted_trigger_count", "last_trigger_ms",
    "last_interval_ms", "last_phase_us", "last_jitter_us", "reset_accepted",
    *("signals." + key for key in SIGNAL_DEFAULTS),
}


class ScenarioError(ValueError):
    """Invalid or unsupported scenario; never silently ignored."""


def _keys(value: Any, allowed: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        raise ScenarioError(f"{where} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise ScenarioError(f"{where} field names must be strings")
    extra = set(value) - allowed
    if extra:
        raise ScenarioError(f"Unknown {where} fields: {sorted(extra)}")
    return value


def _number(value: Any, where: str, low: float = 0.0,
            high: float = MAX_TIME_MS) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"{where} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or not low <= value <= high:
        raise ScenarioError(f"{where} outside [{low}, {high}]")
    return float(value)


def _text(value: Any, where: str, limit: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ScenarioError(f"{where} must be nonempty text <= {limit} characters")
    return value


def _signals(value: Any) -> dict:
    _keys(value, set(SIGNAL_DEFAULTS), "signals")
    for key, item in value.items():
        if key in BOOL_SIGNALS and type(item) is not bool:
            raise ScenarioError(f"signals.{key} must be boolean")
        if key == "seed_frequency_mhz":
            _number(item, key, 0, 100_000)
    return copy.deepcopy(value)


def _query_id(value: Any, *, query_only: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ScenarioError("Wire ID must be an integer or decimal string")
    try:
        cid = int(value)
    except (ValueError, TypeError) as exc:
        raise ScenarioError("Invalid wire ID") from exc
    if str(cid) != str(value) or cid not in COMMANDS or (query_only and cid >= 2000):
        raise ScenarioError(f"Unknown/non-query wire ID: {value}")
    return cid


def _wire(value: Any) -> dict:
    _keys(value, {"overrides", "drop_ids", "request_drop_ids", "error_ids", "delay_ms"}, "wire")
    result = {}
    for key, item in value.items():
        if key in {"drop_ids", "request_drop_ids", "error_ids"}:
            if not isinstance(item, list) or len(item) > 146:
                raise ScenarioError(f"{key} must be a list of at most 146 IDs")
            ids = [_query_id(i, query_only=False) for i in item]
            if len(ids) != len(set(ids)):
                raise ScenarioError(f"Duplicate {key}")
            result[key] = ids
        else:
            if not isinstance(item, dict) or len(item) > 90:
                raise ScenarioError(f"{key} must be an object of at most 90 IDs")
            result[key] = {}
            for raw_id, val in item.items():
                cid = _query_id(raw_id, query_only=key == "overrides")
                if cid in result[key]:
                    raise ScenarioError(f"Duplicate normalized ID {cid}")
                if key == "delay_ms":
                    _number(val, f"delay_ms.{cid}", 0, 60_000)
                elif val is not None:
                    if (not isinstance(val, str) or len(val) > 1024
                            or not val.isascii() or "\n" in val or "\r" in val):
                        raise ScenarioError("Wire overrides must be single-line ASCII <=1024 or null")
                result[key][cid] = val
    return result


def _event(raw: Any) -> dict:
    _keys(raw, {"at_ms", "type", "values", "phase_us", "jitter_us", "wire", "note"}, "event")
    _number(raw.get("at_ms"), "event.at_ms")
    kind = raw.get("type")
    allowed = {
        "signals": {"values"}, "trigger": {"phase_us", "jitter_us"},
        "missing_trigger": set(), "reset": set(), "arm": set(),
        "disarm": set(), "wire": {"wire"}, "clear_wire": set(),
    }
    if not isinstance(kind, str) or kind not in allowed:
        raise ScenarioError(f"Unsupported event type {kind!r}")
    if set(raw) - {"at_ms", "type", "note"} - allowed[kind]:
        raise ScenarioError(f"Fields do not apply to event {kind}")
    if "note" in raw:
        _text(raw["note"], "event.note")
    result = copy.deepcopy(raw)
    if kind == "signals":
        result["values"] = _signals(raw.get("values"))
    if kind == "wire":
        result["wire"] = _wire(raw.get("wire"))
    for key in ("phase_us", "jitter_us"):
        if key in raw:
            _number(raw[key], key, -1e9, 1e9)
    return result


def validate_scenario(raw: Any) -> dict:
    _keys(raw, {"schema_version", "id", "name", "description", "duration_ms",
                "policy", "initial_signals", "events", "assertions", "evidence_reference"}, "scenario")
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != SCHEMA_VERSION:
        raise ScenarioError("Unsupported scenario schema_version; expected 1")
    for key in ("id", "name", "description"):
        _text(raw.get(key), key)
    duration = _number(raw.get("duration_ms"), "duration_ms")
    if "evidence_reference" in raw:
        _text(raw["evidence_reference"], "evidence_reference", 2000)
    policy = dict(POLICY_DEFAULTS)
    supplied = raw.get("policy", {})
    _keys(supplied, set(policy), "policy")
    for key, val in supplied.items():
        _number(val, key, 0, 1e9)
        if key in {"expected_seed_mhz", "expected_trigger_hz", "trigger_timeout_ms"} and val <= 0:
            raise ScenarioError(f"{key} must be positive")
        if key == "rate_tolerance_fraction" and val > 1:
            raise ScenarioError("rate_tolerance_fraction must be <= 1")
        policy[key] = float(val)
    events = raw.get("events")
    assertions = raw.get("assertions")
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ScenarioError(f"events must be a list of at most {MAX_EVENTS}")
    if not isinstance(assertions, list) or len(assertions) > MAX_EVENTS:
        raise ScenarioError(f"assertions must be a list of at most {MAX_EVENTS}")
    validated_events = [_event(event) for event in events]
    times = [event["at_ms"] for event in validated_events]
    if times != sorted(times) or any(t > duration for t in times):
        raise ScenarioError("Events must be chronological and within duration_ms")
    for assertion in assertions:
        _keys(assertion, {"at_ms", "path", "op", "expected", "description"}, "assertion")
        _number(assertion.get("at_ms"), "assertion.at_ms", 0, duration)
        if not isinstance(assertion.get("path"), str) or assertion["path"] not in STATE_PATHS:
            raise ScenarioError(f"Unsupported assertion path: {assertion.get('path')}")
        if not isinstance(assertion.get("op", "eq"), str) or assertion.get("op", "eq") not in {"eq", "ne", "lt", "lte", "gt", "gte", "contains", "not_contains"}:
            raise ScenarioError("Unsupported assertion operation")
        if "expected" not in assertion:
            raise ScenarioError("Assertion requires expected")
        # JSON-only finite values. Reject exotic Python objects in mapping inputs too.
        try:
            json.dumps(assertion["expected"], allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ScenarioError("Assertion expected must be finite JSON") from exc
        if "description" in assertion:
            _text(assertion["description"], "assertion.description")
    result = copy.deepcopy(raw)
    result["policy"] = policy
    result["initial_signals"] = _signals(raw.get("initial_signals", {}))
    result["events"] = validated_events
    return result


def load_scenario(source: str | Path | dict) -> dict:
    if isinstance(source, dict):
        return validate_scenario(source)
    path = Path(source)
    if not path.is_file():
        name = str(source)
        # Builtin names cannot escape the data directory.
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in name):
            raise ScenarioError(f"Scenario file not found: {source}")
        path = DATA_DIRECTORY / (name + ".json")
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ScenarioError("Scenario exceeds 2 MB")
        data = path.read_text(encoding="utf-8-sig")
        def unique_pairs(pairs):
            result = {}
            for key, val in pairs:
                if key in result:
                    raise ScenarioError(f"Duplicate JSON field: {key}")
                result[key] = val
            return result
        raw = json.loads(data, object_pairs_hook=unique_pairs,
                         parse_constant=lambda value: (_ for _ in ()).throw(ScenarioError(f"Nonfinite JSON {value}")))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ScenarioError(f"Cannot load scenario {source}: {exc}") from exc
    return validate_scenario(raw)


def list_scenarios() -> list[dict]:
    result = []
    for path in sorted(DATA_DIRECTORY.glob("*.json")):
        item = load_scenario(path)
        result.append({key: item[key] for key in ("id", "name", "description", "duration_ms")} |
                      {"evidence": "synthetic_policy"})
    return result


class ScenarioEngine:
    """One independent virtual clock and policy state per client/session.

    `advance_to(t)` processes all events at or before t, preserving file order
    for equal timestamps. A trigger exactly at its watchdog deadline wins;
    later triggers cannot retroactively erase the timeout transition.
    """
    def __init__(self, scenario: str | Path | dict):
        self.scenario = load_scenario(scenario)
        self.policy = self.scenario["policy"]
        self.time_ms = 0.0
        self.signals = dict(SIGNAL_DEFAULTS) | self.scenario["initial_signals"]
        self.armed = False
        self.active_faults: set[str] = set()
        self.latched_faults: set[str] = set()
        self.trigger_count = self.accepted_trigger_count = 0
        self.last_trigger_ms = self.last_interval_ms = None
        self.last_phase_us = self.last_jitter_us = None
        self.reset_accepted = False
        self._deadline = None
        self._index = 0
        self._processed_events = 0
        self._wire = {"overrides": {}, "drop_ids": [], "request_drop_ids": [], "error_ids": [], "delay_ms": {}}
        self.transitions: list[dict] = []
        self._signal_faults()
        self._enforce()

    def _signal_faults(self):
        checks = {
            "seed_missing": self.signals["seed_present"],
            "seed_rate_mismatch": abs(self.signals["seed_frequency_mhz"] - self.policy["expected_seed_mhz"]) <= self.policy["seed_tolerance_mhz"],
            "pump_missing": self.signals["pump_present"],
            "pump_not_ready": self.signals["pump_ready"],
            "interlock_open": self.signals["interlock_closed"],
            "overtemperature": self.signals["temperature_ok"],
            "flow_fault": self.signals["flow_ok"],
            "hv_fault": self.signals["hv_ok"],
            "communication_lost": self.signals["communication_ok"],
        }
        for fault, healthy in checks.items():
            if healthy:
                self.active_faults.discard(fault)
            else:
                self.active_faults.add(fault)

    def _enforce(self):
        self.latched_faults.update(self.active_faults)
        if self.active_faults or self.latched_faults:
            self.armed = False
            self._deadline = None

    def snapshot(self) -> dict:
        return {
            "time_ms": self.time_ms, "signals": dict(self.signals),
            "duration_ms": self.scenario["duration_ms"],
            "finished": self.time_ms >= self.scenario["duration_ms"],
            "phase": self._processed_events, "processed_events": self._processed_events,
            "active_faults": sorted(self.active_faults), "latched_faults": sorted(self.latched_faults),
            "armed": self.armed, "inhibited": not self.armed,
            "trigger_count": self.trigger_count, "accepted_trigger_count": self.accepted_trigger_count,
            "last_trigger_ms": self.last_trigger_ms, "last_interval_ms": self.last_interval_ms,
            "last_phase_us": self.last_phase_us, "last_jitter_us": self.last_jitter_us,
            "reset_accepted": self.reset_accepted,
            "evidence": "synthetic_policy", "physical_validation": "UNVERIFIED",
        }

    def wire_effects(self) -> dict:
        """Explicit query stimuli only; caller must preserve synthetic provenance."""
        return copy.deepcopy(self._wire)

    def _record(self, kind, note=""):
        self._processed_events += 1
        self.transitions.append({"time_ms": self.time_ms, "event": kind, "note": note,
                                 "state": self.snapshot()})

    def _expire_before(self, target: float, *, inclusive: bool):
        due = self._deadline
        if due is not None and (due < target or (inclusive and due == target)):
            self.time_ms = due
            self.active_faults.add("trigger_missing")
            self._enforce()
            self._record("watchdog_timeout", "Synthetic policy deadline, not a measured device timer")

    def _apply(self, event: dict):
        kind = event["type"]
        if kind == "signals":
            self.signals.update(event["values"])
            self._signal_faults()
        elif kind == "trigger":
            self.trigger_count += 1
            transient = {"trigger_missing", "duplicate_trigger", "trigger_rate_mismatch", "trigger_jitter", "phase_slip"}
            self.active_faults.difference_update(transient)
            interval = None if self.last_trigger_ms is None else self.time_ms - self.last_trigger_ms
            self.last_interval_ms = interval
            if interval is not None:
                expected = 1000.0 / self.policy["expected_trigger_hz"]
                if interval == 0:
                    self.active_faults.add("duplicate_trigger")
                elif abs(1000.0 / interval - self.policy["expected_trigger_hz"]) > self.policy["expected_trigger_hz"] * self.policy["rate_tolerance_fraction"]:
                    self.active_faults.add("trigger_rate_mismatch")
                self.last_jitter_us = event.get("jitter_us", (interval - expected) * 1000.0)
            else:
                self.last_jitter_us = event.get("jitter_us", 0.0)
            self.last_phase_us = event.get("phase_us", 0.0)
            if abs(self.last_jitter_us) > self.policy["max_jitter_us"]:
                self.active_faults.add("trigger_jitter")
            if abs(self.last_phase_us) > self.policy["max_phase_slip_us"]:
                self.active_faults.add("phase_slip")
            self.last_trigger_ms = self.time_ms
            if self.armed and not self.active_faults and not self.latched_faults:
                self.accepted_trigger_count += 1
                self._deadline = self.time_ms + self.policy["trigger_timeout_ms"]
        elif kind == "missing_trigger":
            self.active_faults.add("trigger_missing")
        elif kind == "reset":
            # Clearing transient timing faults is an explicit operator action.
            self.active_faults.difference_update({"trigger_missing", "duplicate_trigger", "trigger_rate_mismatch", "trigger_jitter", "phase_slip"})
            self._signal_faults()
            self.reset_accepted = not self.active_faults
            if self.reset_accepted:
                self.latched_faults.clear()
                self.armed = False
                self._deadline = None
                self.last_trigger_ms = None
        elif kind == "arm":
            self._signal_faults()
            was_armed = self.armed
            self.armed = not self.active_faults and not self.latched_faults
            if self.armed and not was_armed:
                self.last_trigger_ms = None
                self._deadline = self.time_ms + self.policy["trigger_timeout_ms"]
        elif kind == "disarm":
            self.armed = False
            self._deadline = None
        elif kind == "wire":
            for key, value in event["wire"].items():
                if key in {"overrides", "delay_ms"}:
                    for cid, val in value.items():
                        if val is None or (key == "delay_ms" and val == 0):
                            self._wire[key].pop(cid, None)
                        else:
                            self._wire[key][cid] = val
                else:
                    self._wire[key] = list(value)
        elif kind == "clear_wire":
            self._wire = {"overrides": {}, "drop_ids": [], "request_drop_ids": [], "error_ids": [], "delay_ms": {}}
        self._enforce()
        self._record(kind, event.get("note", ""))

    def advance_to(self, milliseconds: float) -> dict:
        target = min(_number(milliseconds, "advance_to", self.time_ms, 1e15),
                     self.scenario["duration_ms"])
        events = self.scenario["events"]
        while self._index < len(events) and events[self._index]["at_ms"] <= target:
            event = events[self._index]
            self._expire_before(event["at_ms"], inclusive=False)
            self.time_ms = float(event["at_ms"])
            self._apply(event)
            self._index += 1
        self._expire_before(target, inclusive=True)
        self.time_ms = target
        return self.snapshot()

    def inject(self, event: dict) -> dict:
        """Apply an explicit UI/test event at current time, recording provenance."""
        validated = _event(event)
        if validated["at_ms"] != self.time_ms:
            raise ScenarioError("Injected event must use the engine's current time")
        self.advance_to(self.time_ms)
        self._apply(validated)
        return self.snapshot()


def _assert(actual, op, expected) -> bool:
    try:
        if op == "eq":
            return type(actual) is type(expected) and actual == expected if isinstance(actual, bool) or isinstance(expected, bool) else actual == expected
        if op == "ne":
            return not _assert(actual, "eq", expected)
        if op in {"lt", "lte", "gt", "gte"}:
            if isinstance(actual, bool) or isinstance(expected, bool):
                return False
            return {"lt": lambda: actual < expected, "lte": lambda: actual <= expected,
                    "gt": lambda: actual > expected, "gte": lambda: actual >= expected}[op]()
        if op == "contains":
            return expected in actual
        if op == "not_contains":
            return expected not in actual
    except (TypeError, ValueError):
        return False
    return False


def run_scenario(source: str | Path | dict) -> dict:
    engine = ScenarioEngine(source)
    results = []
    for assertion in sorted(engine.scenario["assertions"], key=lambda item: item["at_ms"]):
        snapshot = engine.advance_to(assertion["at_ms"])
        actual: Any = snapshot
        for part in assertion["path"].split("."):
            actual = actual[part]
        op = assertion.get("op", "eq")
        results.append(dict(assertion, op=op, actual=copy.deepcopy(actual),
                            passed=bool(_assert(actual, op, assertion["expected"]))))
    final_state = engine.advance_to(engine.scenario["duration_ms"])
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": engine.scenario["id"], "name": engine.scenario["name"],
        "model_verdict": ("PASS" if all(a["passed"] for a in results) else "FAIL") if results else "UNVERIFIED",
        "client_equivalence": "UNVERIFIED", "physical_validation": "UNVERIFIED",
        "evidence": "synthetic_policy", "assertions": results,
        "transitions": engine.transitions, "final_state": final_state,
        "wire_effects": engine.wire_effects(), "limitations": list(LIMITATIONS),
    }

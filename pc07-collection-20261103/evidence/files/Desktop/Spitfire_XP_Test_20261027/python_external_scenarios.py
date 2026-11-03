"""Actual Python 1.3.0 external controller against an isolated UDP fixture.

Only 127.0.0.1 and an ephemeral port are allowed. The sole permitted write is
EMPOPTOUT (2036) to the synthetic device. No HV/channel/pump output is enabled.
This is a backend policy test, not XP equivalence, GUI or physical validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import queue
import re
import sys
import threading
import time
import traceback
from types import SimpleNamespace

LOOPBACK = "127.0.0.1"
LABEL = "Python 1.3.0 external backend"
SCOPE = "SYNTHETIC_EXTERNAL_POLICY_NOT_XP_EQUIVALENCE_OR_HARDWARE"
HARNESS_VERSION = "1.0.0"
MAX_EVENTS = 30000
MAX_TRANSACTIONS = 15000
EXPECTED_CASE_COUNT = 19


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client-project", required=True, type=Path)
    p.add_argument("--verifier-project", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--timeout", type=float, default=1.0)
    p.add_argument("--case-deadline", type=float, default=7.0)
    return p


def validate(args):
    if not math.isfinite(args.timeout) or not 0.1 <= args.timeout <= 2.0:
        raise ValueError("Timeout must be finite and within 0.1..2.0 seconds")
    if not math.isfinite(args.case_deadline) or not 2.0 <= args.case_deadline <= 15.0:
        raise ValueError("Case deadline must be finite and within 2..15 seconds")
    for key, package, module in (("client_project", "spitfire_control", "controller.py"),
                                 ("verifier_project", "spitfire_twin_verifier", "server.py")):
        path = getattr(args, key).resolve(strict=True)
        if not (path / "src" / package / module).is_file():
            raise ValueError(f"{key} is not the expected source project")
        setattr(args, key, path)
    args.output = args.output.resolve()
    if args.output.exists():
        raise ValueError("Output exists; a fresh evidence directory is required")
    for source in (args.client_project, args.verifier_project):
        if args.output == source or args.output.is_relative_to(source):
            raise ValueError("Output must be outside both source projects")
    return args


def json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=json_default)
        stream.write("\n")


def source_hashes(project, package):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((project / "src" / package).rglob("*.py"))}


def load_api(client_project, verifier_project):
    for source, package in ((client_project, "spitfire_control"),
                            (verifier_project, "spitfire_twin_verifier")):
        sys.path.insert(0, str(source / "src"))
        module = importlib.import_module(package)
        if Path(module.__file__).resolve().parent != source / "src" / package:
            raise ValueError(f"Unexpected installed {package} shadows the source")
    from spitfire_control import __version__ as client_version
    from spitfire_control.controller import LaserController
    from spitfire_control.commands import format_command
    from spitfire_control.profiles import EXTERNAL_REQUIRED_READS, EMPOWER_QUERY_IDS
    from spitfire_control.transport import UdpSettings, UdpTransport, TransportError
    from spitfire_twin_verifier import __version__ as verifier_version
    from spitfire_twin_verifier.model import VirtualSpitfire, ResponseProfile
    from spitfire_twin_verifier.records import CaptureStore
    from spitfire_twin_verifier.server import VirtualDeviceServer
    if client_version != "1.3.0":
        raise ValueError(f"Harness is pinned to Python client 1.3.0, got {client_version}")

    class OptoutOnlyLoopbackTransport(UdpTransport):
        def __init__(self, port):
            self.expected_port = int(port)
            self.blocked_attempts = []
            super().__init__(UdpSettings(remote_host=LOOPBACK, remote_port=port,
                                         local_host=LOOPBACK, local_port=0))

        def check_endpoint(self):
            s = self.settings
            if (s.remote_host, int(s.remote_port), s.local_host, int(s.local_port)) != (
                    LOOPBACK, self.expected_port, LOOPBACK, 0):
                raise TransportError("Harness requires immutable loopback-only endpoints")
            if not 1024 < self.expected_port <= 65535:
                raise TransportError("Harness requires an ephemeral non-instrument port")
            if self._remote is not None and self._remote != (LOOPBACK, self.expected_port):
                raise TransportError("Harness rejects modified resolved endpoints")

        def connect(self):
            self.check_endpoint()
            super().connect()
            self.check_endpoint()

        def exchange(self, command_line, timeout, *, send_guard=None):
            self.check_endpoint()
            read = re.fullmatch(r"\[(10[0-8][0-9])\][^\r\n;]+", command_line)
            if read:
                cid = int(read.group(1))
                allowed_lines = {format_command(cid)}
                if cid == 1026:
                    allowed_lines.update(format_command(cid, channel) for channel in range(1, 6))
                read = command_line in allowed_lines
            optout = re.fullmatch(r"\[2036\]EMPOPTOUT [01]", command_line)
            if not (read or optout):
                self.blocked_attempts.append(command_line)
                raise TransportError("Harness blocks every write except synthetic EMPOPTOUT 0/1")
            return super().exchange(command_line, timeout, send_guard=send_guard)

    return SimpleNamespace(Controller=LaserController, Transport=OptoutOnlyLoopbackTransport,
                           Device=VirtualSpitfire, Profile=ResponseProfile,
                           Store=CaptureStore, Server=VirtualDeviceServer,
                           required=tuple(EXTERNAL_REQUIRED_READS), empower=set(EMPOWER_QUERY_IDS),
                           client_version=client_version, verifier_version=verifier_version)


class ScenarioRun:
    def __init__(self, args, api):
        self.args, self.api = args, api
        self.capture = api.Store()
        self.device = api.Device(isolated_clients=True)
        self.server = api.Server(LOOPBACK, 0, self.device, self.capture, {LOOPBACK: LABEL})
        self.controller = self.transport = None
        self.actions, self.events, self.snapshots, self.cases = [], [], [], []
        self.started = time.monotonic()
        self.errors = []
        self.endpoint = None
        self.last_state = None
        self.current_profile = None

    def now(self):
        return {"utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": time.monotonic() - self.started}

    @staticmethod
    def facts(state):
        return {"pump_mode": state.pump_mode, "connected": state.connected,
                "armed": state.armed, "last_error": state.last_error,
                "invalid_ids": sorted(state.invalid_ids),
                "pending_readbacks": sorted(state.pending_readbacks),
                "fault_active": state.fault_active, "faults_known": state.faults_known,
                "opt_out_confirmed": state.external_opt_out_confirmed,
                "external_enable_reason": state.external_enable_reason(),
                "module_communication": {name: state.communication_state(name)
                                         for name in ("EMPOWER", "TDG", "TCU", "COMPRESSOR")},
                "laser_on": state.laser_on, "high_voltage": state.high_voltage}

    def drain(self):
        while self.controller is not None:
            try:
                event = self.controller.events.get_nowait()
            except queue.Empty:
                break
            if len(self.events) >= MAX_EVENTS:
                raise RuntimeError("Event evidence bound reached")
            self.events.append({**self.now(), "kind": event.kind, "message": event.message,
                                "reply": asdict(event.reply) if event.reply else None,
                                "state": self.facts(event.state) if event.state else None})

    def record(self, action, **details):
        self.drain()
        self.actions.append({**self.now(), "action": action, **details})
        if self.controller is not None:
            state = self.controller.state
            self.snapshots.append({**self.now(), "action": action, "state": asdict(state),
                                   "derived": self.facts(state)})

    def wait(self, predicate, description, deadline=None):
        end = time.monotonic() + (deadline or self.args.case_deadline)
        pause = threading.Event()
        while time.monotonic() < end:
            self.drain()
            if not self.server.running or not self.controller.running:
                raise RuntimeError("Fixture or real client worker stopped unexpectedly")
            if len(self.capture.snapshot().transactions) >= MAX_TRANSACTIONS:
                raise RuntimeError("Transaction evidence bound reached")
            if predicate():
                return
            pause.wait(0.015)
        raise AssertionError(f"Deadline waiting for {description}")

    def profile(self, name, *, overrides=None, error_ids=(), drop_ids=()):
        values = {1050: "EXT", 1067: "EXT", 1051: "EXT", 1065: "80"}
        values.update(overrides or {})
        p = self.api.Profile(name=name, overrides=values, error_ids=set(error_ids), drop_ids=set(drop_ids))
        self.server.set_profile(p)
        self.current_profile = json.loads(json.dumps(p.to_dict()))
        self.record("set_profile", profile=p.to_dict())
        return p

    def boundary(self):
        tx = self.capture.snapshot().transactions
        return max((t.sequence for t in tx), default=0)

    def matching_readbacks(self, ids, boundary, profile):
        """Require new fixture-provenance replies AND actual controller consumption.

        A fresh timestamp alone could belong to an earlier in-flight response.
        Profile + sequence + request time + current raw value exclude that evidence.
        This harness does not claim to add sequence tokens to the real protocol.
        """
        matching = {}
        for tx in self.capture.snapshot().transactions:
            if (tx.sequence > boundary and tx.command_id in ids and tx.status == "REPLIED"
                    and json.loads(tx.profile_json) == profile):
                matching[tx.command_id] = tx
        state = self.controller.state
        for cid in ids:
            tx = matching.get(cid)
            if tx is None or not state.is_fresh(cid):
                return False
            stamp = state.updated_at.get(cid)
            # sent_utc is logged after sendto and may follow client consumption.
            # Request receipt necessarily precedes this reply/consumption, and
            # the real client performs one exchange at a time.
            if (stamp is None or not tx.timestamp_utc or stamp < datetime.fromisoformat(tx.timestamp_utc)
                    or state.raw_values.get(cid) != tx.response_value):
                return False
        return True

    def refresh(self, *ids):
        boundary = self.boundary()
        profile = self.current_profile.copy()
        self.controller.query_now(ids)
        self.wait(lambda: self.matching_readbacks(ids, boundary, profile),
                  "new profile-matched readbacks consumed by controller")
        self.record("fresh_profile_matched_readbacks", command_ids=list(ids),
                    after_transaction_sequence=boundary, profile=profile)

    def all_fresh(self):
        return all(self.controller.state.is_fresh(cid) for cid in self.api.required)

    def arm(self):
        self.controller.arm(True)
        self.record("arm_synthetic_loopback")
        assert self.controller.state.armed

    def deny(self, command_id, argument=None):
        try:
            self.controller.submit(command_id, argument, origin="external harness rejection probe")
        except (PermissionError, ValueError) as exc:
            self.record("submission_rejected", command_id=command_id, argument=argument, reason=str(exc))
            return str(exc)
        self.controller.arm(False)
        raise AssertionError(f"Expected command {command_id} to be rejected before enqueue")

    def recover(self, *, overrides=None):
        self.profile("healthy recovery", overrides=overrides)
        self.refresh(*self.api.required)
        state = self.controller.state
        assert state.connected and state.external_opt_out_confirmed
        assert not state.external_enable_reason(), state.external_enable_reason()
        assert not state.fault_active
        assert not state.armed, "Recovery must not automatically ARM"
        self.record("recovery_all_18_confirmed", required=list(self.api.required))
        hold_start = time.monotonic()
        boundary, profile = self.boundary(), self.current_profile.copy()
        event_start = len(self.events)

        def stable_disarmed():
            state = self.controller.state
            assert not state.armed, "Recovery automatically re-armed during observation"
            assert not any(e["state"] and e["state"]["armed"] for e in self.events[event_start:]), \
                "An ARM event occurred during recovery observation"
            return (time.monotonic() - hold_start >= 1.1
                    and self.matching_readbacks((1000,), boundary, profile)
                    and self.all_fresh() and state.connected
                    and state.external_opt_out_confirmed and not state.external_enable_reason())

        self.wait(stable_disarmed, "at least 1.1 seconds plus a new heartbeat without automatic ARM")
        self.record("recovered_disarmed", observation_seconds=time.monotonic() - hold_start,
                    heartbeat_after_transaction_sequence=boundary)

    def case(self, name, fn):
        start = self.now()
        before_tx = len(self.capture.snapshot().transactions)
        before_event = len(self.events)
        self.capture.mark_scenario(name)
        self.record("case_start", case=name)
        error = None
        try:
            fn()
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        self.record("case_end", case=name, passed=error is None)
        tx = self.capture.snapshot().transactions[before_tx:]
        result = {"name": name, "verdict": "PASS" if error is None else "FAIL",
                  "started": start, "ended": self.now(), "error": error,
                  "transaction_sequences": [t.sequence for t in tx],
                  "event_index_range": [before_event, len(self.events)],
                  "final_facts": self.facts(self.controller.state)}
        self.cases.append(result)
        print(json.dumps({"case": name, "verdict": result["verdict"], "error": error}), flush=True)
        if error:
            raise AssertionError(f"Case failed: {name}: {error['message']}")

    def start(self):
        self.profile("external startup; absent Empower communication", overrides={1089: "4"})
        self.server.start()
        self.endpoint = self.server.local_address
        self.transport = self.api.Transport(self.endpoint[1])
        self.controller = self.api.Controller(self.transport, timeout=self.args.timeout,
            poll_interval=1.0, auto_poll=False, monitor_hv=False, pump_mode="external",
            log_directory=str(self.args.output / "client_audit"))
        self.capture.set_metadata(harness="python_external_scenarios.py", harness_version=HARNESS_VERSION,
            scope=SCOPE, pump_mode="external", automatic_polling=False, endpoint=list(self.endpoint),
            permitted_writes=[2036], outputs_enabled=False, gui_validation="NOT_PERFORMED",
            physical_validation="UNVERIFIED", xp_equivalence="NOT_EVALUATED",
            client_settings_loaded=False, client_version=self.api.client_version,
            verifier_version=self.api.verifier_version)
        self.controller.start()
        self.record("controller_started", endpoint=list(self.endpoint))

    def execute_cases(self):
        def startup():
            def enough():
                counts = Counter(t.command_id for t in self.capture.snapshot().transactions)
                return all(counts[cid] >= 2 for cid in self.api.required) and self.all_fresh()
            self.wait(enough, "two observations of all 18 required queries with automatic polling OFF")
            tx = self.capture.snapshot().transactions
            assert not self.api.empower.intersection(t.command_id for t in tx)
            assert not any(t.writable for t in tx)
            assert not self.controller.state.armed
            assert self.controller.state.laser_on is None
        self.case("startup_excludes_empower_and_keeps_18_required_queries", startup)

        def initial_optout():
            state = self.controller.state
            assert state.value(1068) == 0 and not state.external_opt_out_confirmed
            assert state.value(1089) == 4 and state.fault_active
            assert "opt-out" in state.external_enable_reason()
            self.deny(2017)
            self.deny(2036, 1)  # DISARM is not firmware opt-out permission.
        self.case("optout_zero_keeps_empower_com_fault_and_blocks_output", initial_optout)

        def excluded_commands():
            for cid, arg in ((1014, None), (1078, None), (2047, 1), (2005, None), (2053, 1)):
                self.deny(cid, arg)
        self.case("programmer_cannot_bypass_empower_or_protection_exclusions", excluded_commands)

        def optout_success():
            self.arm()
            before = len(self.capture.snapshot().transactions)
            self.controller.submit(2036, 1, origin="external harness explicit synthetic opt-out")
            self.wait(lambda: self.controller.state.external_opt_out_confirmed, "opt-out readback=1")
            tx = self.capture.snapshot().transactions[before:]
            write = next(t for t in tx if t.command_id == 2036)
            assert write.response_value == "OK"
            assert any(t.command_id == 1068 and t.response_value == "1" and t.sequence > write.sequence for t in tx)
            state = self.controller.state
            assert state.value(1089) == 4 and not state.fault_active
            assert state.external_enable_reason() == ""
        self.case("explicit_optout_ack_then_readback_excludes_only_empower_com", optout_success)

        for bit, label in ((1, "main"), (2, "tdg"), (8, "tcu"), (16, "unknown"), (6, "empower_plus_tdg")):
            def retained_fault(bit=bit, label=label):
                self.profile(f"{label} communication fault", overrides={1089: str(bit)})
                self.refresh(1089)
                assert self.controller.state.value(1089) == bit
                assert self.controller.state.fault_active
                assert self.controller.state.external_enable_reason()
                self.deny(2017)
            self.case(f"communication_{label}_fault_retained", retained_fault)

        for cid, module in ((1019, "TDG"), (1028, "TCU"), (1015, "COMPRESSOR")):
            def module_fault(cid=cid, module=module):
                self.profile(f"{module} module communication bit", overrides={1089: "4", cid: "2048"})
                self.refresh(1019, 1028, 1015, 1089)
                state = self.controller.state
                assert state.value(cid) == 2048
                assert state.communication_state(module) == "fault"
                assert module in state.external_enable_reason(), state.external_enable_reason()
                # Dedicated module status and aggregate fault_active differ;
                # eligibility must still reject this module communication fault.
                self.deny(2017)
            self.case(f"module_{module.lower()}_communication_2048_blocks", module_fault)

        def clear_com():
            self.profile("only Empower COM after recovery", overrides={1089: "4"})
            self.refresh(*self.api.required)
            assert self.controller.state.external_opt_out_confirmed
            assert not self.controller.state.fault_active
            assert not self.controller.state.external_enable_reason()
        self.case("cleared_non_empower_com_restores_eligibility_not_output", clear_com)

        def ack_without_readback():
            self.profile("ACK but reported opt-out remains zero", overrides={1068: "0", 1089: "4"})
            self.refresh(1068)
            self.arm()
            start = len(self.capture.snapshot().transactions)
            self.controller.submit(2036, 1, origin="synthetic ACK/readback disagreement")
            self.wait(lambda: any(t.command_id == 2036 for t in self.capture.snapshot().transactions[start:]),
                      "opt-out ACK")
            self.refresh(1068)
            tx = self.capture.snapshot().transactions[start:]
            assert any(t.command_id == 2036 and t.response_value == "OK" for t in tx)
            assert self.controller.state.value(1068) == 0
            assert not self.controller.state.external_opt_out_confirmed
            assert self.controller.state.fault_active
            self.deny(2017)
            self.controller.arm(False)
            self.record("disarm_after_ack_readback_disagreement")
            self.recover(overrides={1089: "4"})
        self.case("ack_without_confirming_optout_readback_never_enables", ack_without_readback)

        def rejected_optout():
            self.profile("synthetic unsupported opt-out write", error_ids=(2036,), overrides={1068: "0", 1089: "4"})
            self.refresh(1068)
            self.arm()
            start = len(self.events)
            self.controller.submit(2036, 1, origin="synthetic unsupported command probe")
            self.wait(lambda: any(e["kind"] == "error" and e["reply"] and e["reply"]["command_id"] == 2036
                                  for e in self.events[start:]), "write error response")
            assert not self.controller.state.armed
            assert not self.controller.state.external_opt_out_confirmed
            self.deny(2017)
            self.recover(overrides={1089: "4"})
        self.case("unsupported_optout_write_disarms_and_blocks", rejected_optout)

        def unsupported_read():
            self.arm()
            self.profile("synthetic unsupported opt-out query", error_ids=(1068,), overrides={1089: "4"})
            start = len(self.events)
            self.controller.query_now((1068,))
            self.wait(lambda: any(e["kind"] == "error" and e["reply"] and e["reply"]["command_id"] == 1068
                                  for e in self.events[start:]), "opt-out query error")
            assert not self.controller.state.armed
            assert not self.controller.state.external_opt_out_confirmed
            self.deny(2017)
            self.recover(overrides={1089: "4"})
        self.case("unsupported_optout_readback_invalidates_and_disarms", unsupported_read)

        def bad_com():
            self.arm()
            self.profile("malformed required COM readback", overrides={1089: "not-a-status"})
            start = len(self.events)
            self.controller.query_now((1089,))
            self.wait(lambda: any(e["kind"] == "error" and e["reply"] and e["reply"]["command_id"] == 1089
                                  for e in self.events[start:]), "invalid COM error")
            assert not self.controller.state.armed
            assert not self.controller.state.is_fresh(1089)
            self.deny(2017)
            self.recover(overrides={1089: "4"})
        self.case("invalid_required_com_readback_disarms_recovery_stays_disarmed", bad_com)

        def required_timeout():
            self.arm()
            self.profile("lost required COM replies", drop_ids=(1089,), overrides={1089: "4"})
            start = len(self.events)
            self.controller.query_now((1089,))
            self.wait(lambda: any(e["kind"] == "error" and "Timed out" in e["message"] and "1089" in e["message"]
                                  for e in self.events[start:]), "required COM reply timeout")
            assert not self.controller.state.armed
            assert not self.controller.state.is_fresh(1089)
            self.deny(2017)
            self.recover(overrides={1089: "4"})
        self.case("required_com_timeout_disarms_recovery_stays_disarmed", required_timeout)

        def full_loss():
            self.arm()
            self.profile("all replies lost", drop_ids=range(1000, 1090))
            start = len(self.events)
            self.controller.query_now((1000,))
            self.wait(lambda: any(e["kind"] == "error" and "Timed out" in e["message"]
                                  for e in self.events[start:]), "full controller response loss")
            assert not self.controller.state.armed
            assert not self.controller.state.connected
            self.deny(2017)
            self.recover(overrides={1089: "4"})
        self.case("full_link_loss_disarms_recovery_never_rearms", full_loss)

    def finish(self):
        if self.controller:
            self.last_state = self.controller.state
            self.controller.stop()
            self.drain()
            if self.controller.running:
                self.errors.append("Controller thread did not stop")
        if self.transport:
            self.transport.close()
        self.server.stop()
        final = self.capture.snapshot()
        final.save_jsonl(self.args.output / "capture.jsonl")
        for name, data in (("actions.json", self.actions), ("events.json", self.events),
                           ("snapshots.json", self.snapshots), ("cases.json", self.cases)):
            write_json(self.args.output / name, data)
        writes = [asdict(t) for t in final.transactions if t.writable]
        unexpected = [t.sequence for t in final.transactions if t.validation != "VALID"
                      or t.source_ip != LOOPBACK or t.status not in {"REPLIED", "DROPPED"}]
        fixture_errors = [asdict(m) for m in final.messages if m.level in {"ERROR", "PROTOCOL", "REJECTED"}]
        passed = len(self.cases) == EXPECTED_CASE_COUNT and all(c["verdict"] == "PASS" for c in self.cases)
        blocked = self.transport.blocked_attempts if self.transport else []
        good = (passed and not self.errors and not blocked and not unexpected and not fixture_errors
                and not final.pending and all(w["command_id"] == 2036 for w in writes))
        summary = {"status": "SYNTHETIC_EXTERNAL_CASES_PASS" if good else "INCOMPLETE_OR_FAILED",
                   "scope": SCOPE, "harness_version": HARNESS_VERSION,
                   "client_version": self.api.client_version, "verifier_version": self.api.verifier_version,
                   "pump_mode": "external", "automatic_polling": False,
                   "case_count": len(self.cases), "expected_case_count": EXPECTED_CASE_COUNT,
                   "passed": sum(c["verdict"] == "PASS" for c in self.cases),
                   "failed": sum(c["verdict"] == "FAIL" for c in self.cases),
                   "elapsed_seconds": time.monotonic() - self.started,
                   "runtime": {"platform": platform.platform(), "python": sys.version},
                   "endpoint": list(self.endpoint) if self.endpoint else None,
                   "transactions": len(final.transactions),
                   "command_counts": dict(Counter(t.command_id for t in final.transactions)),
                   "transaction_status_counts": dict(Counter(t.status for t in final.transactions)),
                   "write_transactions": writes, "blocked_outbound_attempts": blocked,
                   "unexpected_transaction_sequences": unexpected, "fixture_errors": fixture_errors,
                   "pending": list(final.pending), "errors": self.errors,
                   "last_state_before_cleanup": self.facts(self.last_state) if self.last_state else None,
                   "final_controller_running": self.controller.running if self.controller else False,
                   "final_fixture_running": self.server.running,
                   "client_source_hashes": source_hashes(self.args.client_project, "spitfire_control"),
                   "verifier_source_hashes": source_hashes(self.args.verifier_project, "spitfire_twin_verifier"),
                   "gui_validation": "NOT_PERFORMED", "physical_validation": "UNVERIFIED",
                   "xp_python_equivalence": "NOT_EVALUATED",
                   "limitations": ["No GUI launched; actual client backend only.",
                       "Every fault and response is a synthetic fixture, not firmware certification.",
                       "Only opt-out writes reached the loopback fixture; no HV/channel/pump output enabled.",
                       "Expected error/timeout events are retained as evidence, not counted automatically as failures.",
                       "Actual optical timing, physical interlocks and firmware opt-out meaning remain unverified."]}
        write_json(self.args.output / "summary.json", summary)
        print(json.dumps({k: summary[k] for k in ("status", "case_count", "passed", "failed", "transactions", "elapsed_seconds", "errors")}), flush=True)
        return 0 if good else 2


def run(args):
    args = validate(args)
    api = load_api(args.client_project, args.verifier_project)
    args.output.mkdir(parents=True, exist_ok=False)
    runner = ScenarioRun(args, api)
    try:
        runner.start()
        runner.execute_cases()
    except KeyboardInterrupt:
        runner.errors.append({"type": "KeyboardInterrupt", "message": "Acquisition interrupted"})
    except Exception as exc:
        runner.errors.append({"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    finally:
        exit_code = runner.finish()
    return exit_code


def main():
    try:
        return run(parser().parse_args())
    except Exception as exc:
        print(json.dumps({"status": "PREFLIGHT_OR_SAVE_ERROR", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

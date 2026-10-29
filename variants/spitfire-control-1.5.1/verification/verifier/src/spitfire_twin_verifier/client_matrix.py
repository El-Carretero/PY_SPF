"""Execute selected *trusted* Python clients against a loopback-only twin.

This invokes the selected version's format_command, UdpTransport, reply parser
and DeviceState in a fresh interpreter. It does not substitute our own client
for the tested implementation, and does not claim GUI or hardware validation.
The subprocess/audit guard is not a sandbox for hostile source code.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zipfile

from .catalog import COMMANDS
from .model import ResponseProfile, VirtualSpitfire
from .profiles import InspectionError, inspect_client, materialized_client
from .records import CaptureStore
from .server import VirtualDeviceServer


# Stable independent oracles for the specified synthetic wire fixtures.
# TDG hexadecimal decoding and module faults intentionally expose older-client
# differences rather than accepting each client's previous behavior as truth.
def matrix_cases() -> list[dict]:
    return [
        {"id": "nominal_readbacks", "label": "Nominal replies and engineering units", "profile": {},
         "operations": [{"id": 1010, "expected_value": 1000},
                        {"id": 1024, "expected_value": 80},
                        {"id": 1021, "expected_value": 0},
                        {"id": 1031, "expected_value": 34},
                        {"id": 1053, "expected_value": 1000},
                        {"id": 1045, "expected_value": 0}]},
        {"id": "config_readback", "label": "Virtual divisor write followed by independent query", "profile": {},
         "operations": [{"id": 2020, "argument": 2, "expected_value": "OK"},
                        {"id": 1025, "expected_value": 2}]},
        {"id": "empower_fault_words", "label": "Four-word Empower fault reply", "profile": {"overrides": {1014: "1 16 2 3"}},
         "operations": [{"id": 1014, "expected_value": [1, 16, 2, 3], "expected_fault_active": True}]},
        {"id": "tdg_hex_fault", "label": "TDG hexadecimal register interpretation", "profile": {"overrides": {1066: "4000"}},
         "operations": [{"id": 1066, "expected_value": 16384}]},
        {"id": "dedicated_tdg_fault", "label": "Dedicated TDG fault contributes to alarm state", "profile": {"overrides": {1014: "0 0 0 0", 1066: "4000"}},
         "operations": [{"id": 1014, "expected_value": [0, 0, 0, 0]},
                        {"id": 1066, "expected_fault_active": True}]},
        {"id": "invalid_numeric", "label": "Malformed numeric reply rejected", "profile": {"overrides": {1024: "not-a-number"}},
         "operations": [{"id": 1024, "expected_accepted": False, "expected_value": None}]},
        {"id": "crlf_replies", "label": "CRLF reply compatibility", "profile": {"line_ending": "\r\n"},
         "operations": [{"id": 1030, "expected_value": 25}]},
        {"id": "response_loss", "label": "Lost response yields a transport timeout", "profile": {"drop_ids": {1024}},
         "operations": [{"id": 1024, "expected_timeout": True}]},
        {"id": "malformed_header", "label": "Invalid protocol header is not accepted", "profile": {"malformed_reply_header": True},
         "operations": [{"id": 1024, "expected_timeout": True}]},
    ] + _external_cases()


def _external_cases() -> list[dict]:
    """Synthetic raw reply fixtures for actual external-pump software policy."""
    healthy = {1068: "1", 1019: "0", 1066: "0", 1021: "0", 1087: "0", 1039: "0",
               1050: "EXT", 1051: "EXT", 1065: "80", 1088: "0", 1089: "0", 1033: "0",
               1044: "0", 1028: "0", 1015: "0", 1069: "0",
               1045: "OFF BWD ENA DELAY VALUE = 0", 1046: "OFF BWD ENA DELAY VALUE = 0"}
    def case(case_id, label, tail=(), *, overrides=None, config=None, baseline_allowed=True):
        values = {**healthy, **(overrides or {})}
        operations = [{"id": cid} for cid in values]
        operations[-1]["expected_enable_allowed"] = baseline_allowed
        return {"id": case_id, "label": label, "profile": {"overrides": values},
                "requires_feature": "external_state_policy", "state_config": {
                    "pump_mode": "external", "external_seed_mhz": 80.0,
                    "external_seed_tolerance_mhz": 1.0, "external_pump_hz": 10.0, **(config or {})},
                "operations": operations + list(tail)}
    return [
        case("external_ready", "External software readiness: 80 MHz seed / expected 10 Hz pump"),
        case("external_seed_loss_recovery", "Seed readback lost, then restored", [
            {"id": 1065, "wire_overrides": {1065: "0"}, "expected_value": 0,
             "expected_enable_allowed": False, "expected_timing_allowed": False},
            {"id": 1065, "wire_overrides": {1065: "80"}, "expected_value": 80,
             "expected_enable_allowed": True, "expected_timing_allowed": True}]),
        case("external_oscillator_source", "INT oscillator reference rejected; EXT restores eligibility", [
            {"id": 1050, "wire_overrides": {1050: "INT"}, "expected_value": 0,
             "expected_enable_allowed": False},
            {"id": 1050, "wire_overrides": {1050: "EXT"}, "expected_value": 1,
             "expected_enable_allowed": True}]),
        case("external_trigger_source", "INT amplifier trigger rejected; EXT restores eligibility", [
            {"id": 1051, "wire_overrides": {1051: "INT"}, "expected_value": 0,
             "expected_enable_allowed": False},
            {"id": 1051, "wire_overrides": {1051: "EXT"}, "expected_value": 1,
             "expected_enable_allowed": True}]),
        case("external_key_interlock", "TDG key interlock blocks software eligibility", [
            {"id": 1066, "wire_overrides": {1066: "4000"}, "expected_value": 16384,
             "expected_fault_active": True, "expected_enable_allowed": False},
            {"id": 1066, "wire_overrides": {1066: "0"}, "expected_value": 0,
             "expected_fault_active": False, "expected_enable_allowed": True}]),
        case("external_tcu_humidity", "TCU humidity-latch fault blocks software eligibility", [
            {"id": 1088, "wire_overrides": {1088: "16"}, "expected_value": 16,
             "expected_fault_active": True, "expected_enable_allowed": False}]),
        case("external_tdg_communication", "TDG communication fault blocks software eligibility", [
            {"id": 1089, "wire_overrides": {1089: "2"}, "expected_value": 2,
             "expected_fault_active": True, "expected_enable_allowed": False}]),
        case("external_empower_absent", "Empower absent does not imply external pump emission", [
            {"id": 1014, "wire_overrides": {1014: "255 255 255 123"},
             "expected_fault_active": False, "expected_enable_allowed": True},
            {"id": 1013, "wire_overrides": {1013: "1"}, "expected_laser_on": None,
             "expected_enable_allowed": True}], overrides={1089: "4"}),
        case("external_optout_confirmation", "Missing opt-out readback blocks eligibility", [
            {"id": 1068, "wire_overrides": {1068: "0"}, "expected_enable_allowed": False},
            {"id": 1068, "wire_overrides": {1068: "1"}, "expected_enable_allowed": True}]),
        case("external_invalid_pump_expectation", "Invalid pump expectation rejected by actual timing validator",
             [{"id": 1065, "expected_timing_config_valid": False, "expected_enable_allowed": False}],
             config={"external_pump_hz": 0.0}, baseline_allowed=False),
    ]


_WORKER = r'''
import sys, json, socket, time
payload = json.loads(sys.argv[1])
# The guard prevents accidental hardware access by supported clients. It is
# deliberately not advertised as security isolation for malicious Python code.
def guard(event, args):
    if event in ("socket.connect", "socket.bind"):
        address = args[1]
    elif event == "socket.sendto":
        address = args[1]
    elif event in ("socket.gethostbyname", "socket.gethostbyaddr"):
        if args[0] != "127.0.0.1":
            raise PermissionError("Matrix permits only loopback destinations")
        return
    elif event == "socket.getaddrinfo":
        if args[0] != "127.0.0.1":
            raise PermissionError("Matrix permits only loopback destinations")
        return
    else:
        return
    if not isinstance(address, tuple) or address[0] != "127.0.0.1":
        raise PermissionError("Matrix permits only 127.0.0.1 socket operations")
sys.addaudithook(guard)
sys.path.insert(0, payload["source_root"])
from spitfire_control import __version__
from spitfire_control.commands import format_command
from spitfire_control.transport import UdpSettings, UdpTransport, TransportError
from spitfire_control.state import DeviceState
transport = UdpTransport(UdpSettings(remote_host="127.0.0.1", remote_port=payload["port"],
                                    local_host="127.0.0.1", local_port=0))
state = DeviceState()
for key, value in payload.get("state_config", {}).items():
    setattr(state, key, value)
state.transport_open = True
rows = []
try:
    transport.connect()
    for op in payload["operations"]:
        row = {"id": op["id"]}
        started = time.perf_counter()
        try:
            line = format_command(op["id"], op.get("argument"))
            row["command"] = line
            replies = transport.exchange(line, timeout=0.35)
            row["replies"] = [{"id": r.command_id, "value": r.value} for r in replies]
            accepted = [state.apply(r) for r in replies]
            # The live controller marks a link connected after receiving valid
            # transport replies. Supply that harness condition before inspecting
            # freshness-gated decoded state; this is not a polling-loop test.
            state.connected = bool(replies)
            row["accepted"] = bool(accepted) and all(accepted)
            row["value"] = state.value(op["id"])
            row["fault_active"] = bool(state.fault_active)
            if payload.get("external_policy"):
                row["enable_reason"] = state.external_enable_reason()
                row["timing_reason"] = state.external_timing_reason()
                row["enable_allowed"] = row["enable_reason"] == ""
                row["timing_allowed"] = row["timing_reason"] == ""
                row["laser_on"] = state.laser_on
                from spitfire_control.timing import validate_timing_expectations
                try:
                    validate_timing_expectations(state.external_seed_mhz, state.external_seed_tolerance_mhz,
                                                 state.external_pump_hz)
                    row["timing_config_valid"] = True
                except ValueError:
                    row["timing_config_valid"] = False
            row["transport_error"] = False
        except TransportError as exc:
            row.update(transport_error=True, error=str(exc),
                       timed_out="timed out" in str(exc).lower())
        except Exception as exc:
            row.update(error=type(exc).__name__ + ": " + str(exc), unexpected_error=True)
        row["elapsed_ms"] = (time.perf_counter() - started) * 1000
        rows.append(row)
finally:
    transport.close()
print("SPITFIRE_MATRIX_RESULT=" + json.dumps({"version": __version__, "operations": rows}, allow_nan=False))
'''


def _match(expected, actual) -> bool:
    if isinstance(expected, (float, int)) and not isinstance(expected, bool):
        return (isinstance(actual, (float, int)) and not isinstance(actual, bool) and
                math.isfinite(actual) and math.isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-9))
    return expected == actual


def _evaluate(case: dict, actual: dict) -> tuple[str, list[dict]]:
    rows, details = actual.get("operations", []), []
    for index, op in enumerate(case["operations"]):
        row = rows[index] if index < len(rows) else {}
        failures = []
        if row.get("id") != op["id"]:
            failures.append("Missing or reordered operation")
        if row.get("unexpected_error"):
            failures.append(row.get("error", "Unexpected error"))
        if op.get("expected_timeout"):
            if not row.get("transport_error") or not row.get("timed_out"):
                failures.append("Expected a transport timeout, not a reply or another exception")
        else:
            if row.get("transport_error"):
                failures.append(row.get("error", "Unexpected transport error"))
            if not _match(op.get("expected_accepted", True), row.get("accepted")):
                failures.append("Reply acceptance differs")
            for key in ("value", "fault_active", "enable_allowed", "timing_allowed", "laser_on", "timing_config_valid"):
                if "expected_" + key in op and not _match(op["expected_" + key], row.get(key)):
                    failures.append(key + " differs")
        details.append({"id": op["id"], "status": "FAIL" if failures else "PASS",
                        "expected": op, "actual": row, "differences": failures})
    if len(rows) != len(case["operations"]):
        details.append({"status": "FAIL", "differences": ["Operation count differs"]})
    return ("FAIL" if any(d["status"] == "FAIL" for d in details) else "PASS"), details


def _interpreter(python_executable=None) -> list[str]:
    """A frozen verifier is not a Python interpreter and must never spawn itself."""
    if python_executable:
        executable = str(python_executable)
    elif getattr(sys, "frozen", False):
        executable = shutil.which("py") or shutil.which("python")
        if not executable:
            raise ValueError("Actual-client matrix needs Python 3.10+ installed. Install Python or select --python-executable.")
    else:
        executable = sys.executable
    command = [executable]
    if Path(executable).name.lower() in {"py", "py.exe"}:
        command.append("-3")
    try:
        probe = subprocess.run(command + ["-I", "-c", "import sys,json;print(json.dumps(list(sys.version_info[:3])))"],
                               text=True, capture_output=True, timeout=10)
        version = json.loads(probe.stdout.strip())
        if probe.returncode or not isinstance(version, list) or tuple(version) < (3, 10):
            raise ValueError("Python 3.10+ is required for actual-client matrix")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Cannot launch Python 3.10+. Use --python-executable with the interpreter path.") from exc
    return command


class _FixtureDevice(VirtualSpitfire):
    """Ordered wire checkpoints, not real hardware events or automatic recovery."""
    def __init__(self, operations):
        super().__init__()
        self.operations = operations
        self.operation_index = 0

    def answer(self, client_key, command, profile=None):
        selected = (profile or self.get_profile()).copy()
        if self.operation_index < len(self.operations):
            op = self.operations[self.operation_index]
            if op["id"] == command.command_id:
                selected.overrides.update(op.get("wire_overrides", {}))
        self.operation_index += 1
        return super().answer(client_key, command, selected)


def _run_case(source_root: Path, inspection: dict, case: dict, timeout: float, interpreter: list[str]) -> dict:
    feature = case.get("requires_feature")
    if feature and feature not in inspection.get("adapter_features", []):
        return {"id": case["id"], "label": case["label"], "status": "UNSUPPORTED",
                "detail": f"Selected client does not expose the {feature} adapter. This is not a pass."}
    needed = {op["id"] for op in case["operations"]}
    if any(inspection["commands"].get(str(cid)) != COMMANDS[cid].text for cid in needed):
        return {"id": case["id"], "label": case["label"], "status": "UNSUPPORTED",
                "detail": "The selected client lacks an exact shared command ID/text required by this case."}
    device, capture = _FixtureDevice(case["operations"]), CaptureStore()
    device.set_profile(ResponseProfile(name=case["id"], **case["profile"]))
    server = VirtualDeviceServer("127.0.0.1", 0, device, capture, {"127.0.0.1": "Matrix client"})
    server.start()
    result = {"id": case["id"], "label": case["label"], "status": "ERROR",
              "evidence_scope": "real_client_transport_and_state_vs_synthetic_fixture"}
    try:
        payload = {"source_root": str(source_root), "port": server.local_address[1],
                   "operations": case["operations"], "state_config": case.get("state_config", {}),
                   "external_policy": feature == "external_state_policy"}
        process = subprocess.run(interpreter + ["-I", "-c", _WORKER, json.dumps(payload)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=timeout, cwd=str(source_root))
        result["returncode"] = process.returncode
        lines = [line[len("SPITFIRE_MATRIX_RESULT="):] for line in process.stdout.splitlines()
                 if line.startswith("SPITFIRE_MATRIX_RESULT=")]
        if process.returncode != 0 or len(lines) != 1:
            result["detail"] = "Client worker did not return exactly one successful result"
            result["stderr"] = process.stderr[-6000:]
            result["stdout"] = process.stdout[-6000:]
        else:
            actual = json.loads(lines[0])
            if actual.get("version") != inspection["version"]:
                result["detail"] = "Imported version differs from inspected version"
            else:
                result["status"], result["operations"] = _evaluate(case, actual)
    except subprocess.TimeoutExpired:
        result["detail"] = f"Client subprocess exceeded {timeout:g} s and was terminated"
    except (OSError, ValueError) as exc:
        result["detail"] = f"{type(exc).__name__}: {exc}"
    finally:
        server.stop()
    result["wire_transactions"] = [asdict(item) for item in capture.transactions()]
    result["wire_pending"] = list(capture.snapshot().pending)
    if result["status"] == "PASS" and len(result["wire_transactions"]) != len(case["operations"]):
        result["status"] = "ERROR"
        result["detail"] = "Client reported success without matching wire capture coverage"
    return result


def run_matrix(client_paths, output_dir=None, timeout: float = 15.0, *, trusted: bool = False,
               python_executable=None) -> dict:
    """Run real selected Python source; callers must obtain explicit trust consent.

    No remote destination argument exists: the server and each worker bind to
    127.0.0.1 on ephemeral ports. Do not run untrusted source code.
    """
    if not trusted:
        raise ValueError("Matrix executes selected Python source. Confirm that you trust it, then pass trusted=True.")
    paths = list(client_paths)
    if not paths or len(paths) > 20:
        raise ValueError("Select between 1 and 20 Python source folders/ZIPs")
    if not math.isfinite(timeout) or not 1 <= timeout <= 120:
        raise ValueError("Per-case subprocess timeout must be 1..120 seconds")
    interpreter = _interpreter(python_executable)
    report = {"schema_version": 1, "run_id": uuid.uuid4().hex,
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "status": "ERROR", "clients": [],
              "scope": "Real Python command formatter, UDP transport, reply parser and state decoder",
              "external_policy_scope": "Actual external_enable_reason / external_timing_reason / validate_timing_expectations on synthetic UDP readbacks; no emission commands",
              "python_interpreter": interpreter,
              "xp_execution": "NOT_PERFORMED", "hardware_validation": "NOT_PERFORMED",
              "limitations": ["Synthetic replies are fixture oracles, not measured firmware behavior.",
                              "This matrix does not drive the full GUI, controller polling loop, or electrical timing.",
                              "XP Original is an external-capture profile and is never impersonated by a Python worker.",
                              "No assertion of identical physical laser protection or automatic shutdown is made."]}
    for path in paths:
        item = {"path": str(path), "status": "ERROR", "cases": []}
        report["clients"].append(item)
        try:
            inspection = inspect_client(path)
            item["inspection"] = inspection
            if not inspection["adapter_compatible"]:
                item.update(status="UNSUPPORTED", detail="No supported UdpTransport/DeviceState adapter")
                continue
            with materialized_client(path) as source_root:
                # Detect edits between inspection and source staging, including
                # version-preserving changes in behavior-relevant modules.
                staged = inspect_client(source_root)
                if staged["source_sha256"] != inspection["source_sha256"]:
                    raise InspectionError("Source changed between inspection and staging")
                item["cases"] = [_run_case(source_root, inspection, case, timeout, interpreter) for case in matrix_cases()]
            statuses = {case["status"] for case in item["cases"]}
            item["status"] = "ERROR" if "ERROR" in statuses else (
                "FAIL" if "FAIL" in statuses else "INCOMPLETE" if "UNSUPPORTED" in statuses else "PASS")
            item["inspection"]["evidence_status"] = "TRANSPORT_STATE_MATRIX_EXECUTED"
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            item["detail"] = f"{type(exc).__name__}: {exc}"
    statuses = {item["status"] for item in report["clients"]}
    report["status"] = "ERROR" if "ERROR" in statuses else (
        "FAIL" if "FAIL" in statuses else "INCOMPLETE" if statuses - {"PASS"} else "PASS")
    if output_dir is not None:
        directory = Path(output_dir) / ("client_matrix_" + report["run_id"][:12])
        directory.mkdir(parents=True, exist_ok=False)
        report["output_directory"] = str(directory.absolute())
        (directory / "matrix.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "matrix.html").write_text(_html_report(report), encoding="utf-8")
    return report


def _html_report(report: dict) -> str:
    esc = lambda value: html.escape(str(value))
    rows = []
    for client in report["clients"]:
        info = client.get("inspection", {})
        for case in client["cases"]:
            rows.append("<tr><td>" + esc(info.get("version", "unknown")) + "</td><td>" +
                        esc(case["label"]) + "</td><td class='" + esc(case["status"]) + "'>" +
                        esc(case["status"]) + "</td></tr>")
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>Spitfire Client Matrix</title>"
            "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px}"
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:10px;text-align:left}"
            ".PASS{color:#08733b}.FAIL,.ERROR{color:#b81717}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>"
            "<h1>Spitfire Client Matrix — " + esc(report["status"]) + "</h1><p>" + esc(report["scope"]) +
            "</p><p><strong>XP execution / physical hardware: NOT PERFORMED</strong></p>"
            "<table><tr><th>Version</th><th>Case</th><th>Result</th></tr>" + "".join(rows) +
            "</table><h2>Evidence, identities and limitations</h2><pre>" +
            esc(json.dumps(report, ensure_ascii=False, indent=2)) + "</pre></html>")

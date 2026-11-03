"""Offline acceptance checks and a bounded, fixed-allowlist UDP reader.

This module never constructs LaserController for hardware, reads saved GUI
settings, arms a controller, or sends any write (including OFF/reset/clear).
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import html
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from types import MappingProxyType
import uuid

from . import __version__
from .commands import COMMANDS
from .protocol import encode_datagram
from .state import DeviceState, is_error_reply
from .transport import UdpSettings, UdpTransport, TransportError


# Exact strings, not a broad 'ID < 2000' or '?' heuristic. In particular the
# ambiguous 1026 TDG:DEL and service SECRETMSG queries are intentionally absent.
READ_ONLY_COMMANDS = MappingProxyType({
    1000: "*idn?", 1021: "TDG:HV:ON?", 1007: "EMP:READ:DIODE:CURR?",
    1008: "EMP:READ:POW?", 1042: "TDG:READ:HV1VOLT?", 1043: "TDG:READ:HV2VOLT?",
    1034: "HED:VERS?", 1035: "EMP:VERS?", 1036: "TDG:VERS?", 1037: "ECU:VERS?",
    1013: "EMP:STB?", 1015: "HED:STB?", 1019: "TDG:STB?", 1028: "ECU:STB?",
    1014: "EMP:FAULT?", 1066: "TDG:STBHFLT?", 1057: "ECU:STBH?",
    1033: "ECUOPTOUT?", 1068: "EMPOPTOUT?", 1069: "HEDOPTOUT?",
    1044: "ECU:HUMOVERRIDE?", 1087: "TDG:FAULTOVERRIDE?",
    1030: "ECU:READTEMP?", 1031: "ECU:HUM?", 1032: "ECU:TEMP?",
    1009: "EMP:DIODE:CURR?", 1010: "EMP:QSW:PRF?", 1011: "EMP:QSW:PWID?",
    1012: "EMP:QSW:SOURCE?", 1060: "HED:MOTOR:SPEED?",
    1024: "TDG:OSC:FREQ?", 1025: "TDG:DIV?", 1040: "TDG:HV1:VOLT?", 1041: "TDG:HV2:VOLT?",
    1055: "TDG:READ:HV1CURR?", 1056: "TDG:READ:HV2CURR?",
    1045: "TDG:DEL1?", 1046: "TDG:DEL2?", 1047: "TDG:DEL3?",
    1048: "TDG:DEL4?", 1049: "TDG:DEL5?", 1050: "TDG:OSC:MODE?",
    1051: "TDG:TRIG:MODE?", 1053: "TDG:TRIG:FREQ?", 1080: "TDG:OSC:SETMODE?",
    1065: "TDG:READ:OSCQUEST?", 1077: "EMP:LBOTEMP?", 1084: "ECU:TECTEMP?",
})
GATE_IDS = frozenset({1000, 1021, 1007, 1008, 1042, 1043})
FLAG_IDS = frozenset({1033, 1068, 1069, 1044, 1087})
STATUS_IDS = frozenset({1013, 1015, 1019, 1028})
IDENTITY_IDS = frozenset({1000, 1034, 1035, 1036, 1037})
LIMITATIONS = [
    "PASS applies only to the checks performed; it is not permission to operate the laser.",
    "Physical emission inhibition, interlocks, optical output and calibration are not verified.",
    "No hardware write, ARM, RUN, OFF, HV switching, motion, fault clear, override or serial test is performed.",
    "A controller response reports controller state; it does not prove zero physical output or voltage.",
    "Legacy UDP is unauthenticated; delayed replies with the same ID cannot be fully distinguished.",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def checked_line(cid: int) -> str:
    if type(cid) is not int or cid not in READ_ONLY_COMMANDS:
        raise PermissionError(f"Command {cid!r} is not on the validation read-only allowlist")
    text = READ_ONLY_COMMANDS[cid]
    spec = COMMANDS[cid]
    if spec.writable or spec.text != text or not text.endswith("?"):
        raise PermissionError(f"Read-only catalogue mismatch for {cid}")
    return f"[{cid}]{text}"


def require_read_only_line(line: str) -> int:
    for cid in READ_ONLY_COMMANDS:
        if line == checked_line(cid):
            return cid
    raise PermissionError("Validation permits exact allowlisted queries without arguments only")


def literal_ipv4(value: str, *, local=False) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError("Use a literal IPv4 address, not a hostname or subnet") from exc
    if local and address.is_unspecified:
        return str(address)
    if address.is_multicast or address.is_unspecified or address.is_reserved or int(address) == 0xffffffff:
        raise ValueError("A unicast IPv4 address is required; broadcast/discovery is disabled")
    # Subnet-directed broadcasts cannot be inferred without a netmask. Reject
    # the common /24 boundary forms as an additional conservative check.
    if not address.is_loopback and int(address) & 0xff in {0, 255}:
        raise ValueError("Network/broadcast-looking .0 and .255 addresses are not accepted")
    return str(address)


@dataclass(frozen=True)
class ProbeOptions:
    host: str
    local_host: str = "0.0.0.0"
    remote_port: int = 1024
    local_port: int = 1024
    timeout: float = 2.0
    interval: float = .25
    cycles: int = 1
    max_seconds: float = 120.0
    expect_idn: str = ""

    def validate(self) -> None:
        literal_ipv4(self.host)
        literal_ipv4(self.local_host, local=True)
        for name in ("remote_port", "local_port"):
            value = getattr(self, name)
            if type(value) is not int or not (0 if name == "local_port" else 1) <= value <= 65535:
                raise ValueError(f"Invalid {name}")
        for name, low, high in (("timeout", .1, 5), ("interval", .2, 5), ("max_seconds", 1, 300)):
            value = getattr(self, name)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be finite and between {low} and {high}")
        if type(self.cycles) is not int or not 1 <= self.cycles <= 5:
            raise ValueError("cycles must be between 1 and 5")


class RunReport:
    def __init__(self, parent: Path, mode: str):
        self.directory = parent.expanduser().resolve() / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
        self.directory.mkdir(parents=True, exist_ok=False)
        self.data = {"schema_version": 1, "application_version": __version__, "mode": mode,
                     "started_utc": utc_now(), "finished_utc": None, "overall": "INCOMPLETE",
                     "environment": {"platform": platform.platform(), "python": sys.version,
                                     "executable": sys.executable, "is_windows": sys.platform == "win32"},
                     "windows_execution_verified": False, "physical_safety_verified": False,
                     "hardware_writes_permitted": False, "target": None, "checks": [],
                     "limitations": LIMITATIONS, "scope": "offline software checks"}
        # Reserve/write the journal and report before any device socket opens.
        self._journal = (self.directory / "trace.jsonl").open("x", encoding="utf-8")
        try:
            self.event("start", mode=mode)
            self.checkpoint()
        except BaseException:
            self._journal.close()
            raise

    def event(self, event: str, **details) -> None:
        self._journal.write(json.dumps({"utc": utc_now(), "event": event, **details}, ensure_ascii=False) + "\n")
        self._journal.flush()
        os.fsync(self._journal.fileno())

    def add(self, name: str, status: str, detail: str, *, required=True, **evidence) -> None:
        self.data["checks"].append({"name": name, "status": status, "detail": detail,
                                    "required": required, "evidence": evidence})
        self.checkpoint()

    def checkpoint(self) -> None:
        path = self.directory / "report.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def finish(self, interrupted=False) -> int:
        checks = self.data["checks"]
        statuses = Counter(c["status"] for c in checks)
        if interrupted:
            overall = "INTERRUPTED"
        elif statuses["FAIL"]:
            overall = "FAIL"
        elif any(c["required"] and c["status"] == "SKIP" for c in checks):
            overall = "INCOMPLETE"
        elif statuses["WARN"]:
            overall = "WARN"
        else:
            overall = "PASS"
        self.data.update(finished_utc=utc_now(), overall=overall, counts=dict(statuses))
        try:
            self.checkpoint()
            self.write_html()
        finally:
            self._journal.close()
        return {"PASS": 0, "FAIL": 1, "WARN": 2, "INCOMPLETE": 2, "INTERRUPTED": 130}[overall]

    def write_html(self) -> None:
        esc = lambda value: html.escape(str(value), quote=True)
        rows = []
        for check in self.data["checks"]:
            rows.append(f'<tr><td>{esc(check["status"])}</td><td>{esc(check["name"])}</td><td>{esc(check["detail"])}'
                        f'<details><summary>Evidence</summary><pre>{esc(json.dumps(check["evidence"], ensure_ascii=False, indent=2))}</pre></details></td></tr>')
        document = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Spitfire validation</title>'
                    '<style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#142b3b}'
                    'table{border-collapse:collapse;width:100%}td,th{border:1px solid #becbd3;padding:9px;text-align:left}'
                    'pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:8px 0}</style>'
                    f'<h1>Spitfire {esc(__version__)} — {esc(self.data["overall"])}</h1>'
                    f'<p>Scope: {esc(self.data["scope"])}<br>Mode: {esc(self.data["mode"])}<br>'
                    f'Windows GUI verified: {esc(self.data["windows_execution_verified"])}</p>'
                    '<p><strong>PASS is not authorization to operate the laser.</strong> 물리적 안전과 출력 성능은 검증하지 않습니다.</p>'
                    '<ul>' + ''.join(f'<li>{esc(item)}</li>' for item in LIMITATIONS) + '</ul>'
                    '<table><thead><tr><th>Result</th><th>Check</th><th>Details</th></tr></thead><tbody>'
                    + ''.join(rows) + '</tbody></table></html>')
        (self.directory / "report.html").write_text(document, encoding="utf-8")


class ReadOnlyUdpTransport(UdpTransport):
    def __init__(self, settings: UdpSettings, report: RunReport, *, deadline: float):
        super().__init__(settings)
        self.report = report
        self.deadline = deadline

    def exchange(self, command_line: str, timeout: float, *, send_guard=None):
        cid = require_read_only_line(command_line)
        if send_guard is not None:
            raise PermissionError("External send guards are not accepted by the validator")
        def guarded(send):
            require_read_only_line(command_line)
            if time.monotonic() >= self.deadline:
                raise TransportError("Hardware validation deadline reached")
            self.report.event("tx_attempt", command_id=cid, line=command_line,
                              datagram_hex=encode_datagram([command_line]).hex(), remote=self._remote)
            if time.monotonic() >= self.deadline:
                raise TransportError("Hardware deadline reached while recording the query; not sent")
            send()
            self.report.event("tx_sent", command_id=cid)
        replies = super().exchange(command_line, timeout, send_guard=guarded)
        for reply in replies:
            self.report.event("rx", command_id=reply.command_id, value=reply.value,
                              raw_line=reply.raw_line, validated_remote=self._remote)
        return replies


def assess_reply(cid: int, reply, state: DeviceState, expect_idn="") -> tuple[str, str, bool]:
    if reply.command_id != cid or is_error_reply(reply.value) or not state.apply(reply):
        return "FAIL", "Unexpected, error or undecodable reply", cid in GATE_IDS
    value = state.value(cid)
    if cid in IDENTITY_IDS:
        if (cid == 1000 and not any(c.isalpha() for c in str(value))) or str(value).upper() in {"OK", "ACK", "UNKNOWN", "N/A"}:
            return "FAIL", "Identity/version response is not identifiable text", cid == 1000
        if cid == 1000 and expect_idn and expect_idn.casefold() not in str(value).casefold():
            return "FAIL", "Controller identity does not match --expect-idn", True
    elif cid in GATE_IDS:
        if cid == 1021 and value not in (0, 1):
            return "FAIL", "HV ON? must report 0 or 1; stopping", True
        if value < 0:
            return "FAIL", "Negative/unavailable gate reading; stopping", True
        if value > 0:
            return "WARN", "Controller reports HV ON or positive output/current/HV; stopping without sending OFF", True
    elif cid in STATUS_IDS | FLAG_IDS | {1057, 1066}:
        if value < 0 or value != int(value) or (cid in FLAG_IDS and value not in (0, 1)):
            return "FAIL", "Invalid status/flag value", False
        if cid in STATUS_IDS and int(value) & 0x800:
            return "FAIL", "Module communication fault bit 0x800 is set", False
        if cid in FLAG_IDS and value:
            return "WARN", "Opt-out/override is enabled; not modified by validation", False
        if cid in {1057, 1066} and value:
            return "WARN", "Nonzero health/fault word; manual interpretation required", False
    elif cid == 1014 and any(value):
        return "WARN", "Nonzero Empower fault words; not cleared by validation", False
    elif 1045 <= cid <= 1049:
        delay = state.delays[cid - 1044]
        if None in (delay.switch, delay.bwd, delay.enable):
            return "WARN", "Delay number decoded, but one or more mode flags are unverified", False
    elif isinstance(value, (int, float)) and value < 0:
        return "WARN", "Negative value may be a firmware sentinel; not interpreted as healthy", False
    return "PASS", "Expected endpoint/ID reply received and decoded; physical accuracy not verified", False


def hardware_probe(options: ProbeOptions, report: RunReport) -> None:
    options.validate()
    plan = [(cid, checked_line(cid)) for cid in READ_ONLY_COMMANDS] * options.cycles
    report.data["target"] = asdict(options)
    report.data["scope"] = "offline software checks and fixed-allowlist UDP readback compatibility"
    report.checkpoint()
    started = time.monotonic()
    deadline = started + options.max_seconds
    transport = ReadOnlyUdpTransport(UdpSettings(options.host, options.remote_port,
                                               options.local_host, options.local_port), report, deadline=deadline)
    state = DeviceState()
    completed = 0
    failures = 0
    reason = ""
    try:
        transport.connect()
        report.add("UDP bind", "PASS", "Exclusive local bind succeeded; this alone does not verify a controller",
                   local=transport._socket.getsockname(), remote=transport._remote)
        next_send = time.monotonic()
        for cid, line in plan:
            remaining = deadline - time.monotonic()
            wait = max(0, next_send - time.monotonic())
            if remaining <= wait:
                reason = "Maximum hardware duration reached"
                break
            if wait:
                time.sleep(wait)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "Maximum hardware duration reached"
                break
            tick = time.monotonic()
            try:
                replies = transport.exchange(line, min(options.timeout, remaining))
                if len(replies) != 1:
                    raise TransportError("Expected exactly one matching reply")
            except TransportError as exc:
                failures += 1
                completed += 1
                report.add(f"query {cid}", "FAIL", str(exc), command=line)
                if cid in GATE_IDS or failures >= 2:
                    reason = "Gate query failed or two consecutive transport failures"
                    break
            else:
                failures = 0
                completed += 1
                status, detail, stop = assess_reply(cid, replies[0], state, options.expect_idn)
                evidence = {"command": line, "raw": replies[0].value, "decoded": state.value(cid),
                            "latency_ms": round((time.monotonic() - tick) * 1000, 3)}
                if 1045 <= cid <= 1049 and cid - 1044 in state.delays:
                    evidence["delay"] = asdict(state.delays[cid - 1044])
                report.add(f"query {cid}", status, detail, **evidence)
                if stop:
                    reason = detail
                    break
            # Spacing after completion, so slow controllers never receive bursts.
            next_send = time.monotonic() + options.interval
    except TransportError as exc:
        reason = str(exc)
        report.add("UDP connection", "FAIL", reason)
    finally:
        transport.close()  # No OFF, RESET, CLEAR or other cleanup command.
        report.add("hardware plan", "PASS" if completed == len(plan) and not reason else "SKIP",
                   reason or ("All planned read queries completed" if completed == len(plan)
                              else "Stopped before all planned queries completed"),
                   completed=completed, planned=len(plan),
                   elapsed_seconds=round(time.monotonic() - started, 3),
                   shutdown="socket close only; no device command")


def child_check(command: list[str], output: Path, log: Path, *, timeout=60) -> dict:
    if output.exists():
        raise FileExistsError("Refusing a stale child report")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env=env, cwd=output.parent)
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except BaseException:
        process.kill()
        process.communicate()
        raise
    log.write_bytes(stdout)
    if not output.is_file():
        return {"status": "FAIL", "detail": f"Child produced no report; exit {process.returncode}; see {log.name}"}
    result = json.loads(output.read_text(encoding="utf-8"))
    expected_code = {"PASS": 0, "WARN": 2, "SKIP": 2, "FAIL": 1}.get(result.get("status"))
    if expected_code is None or process.returncode != expected_code:
        return {"status": "FAIL", "detail": "Child exit code and report do not agree", "child": result}
    return result


def verify_exe_manifest(exe: Path) -> dict:
    manifest = json.loads(exe.with_suffix(".validation.json").read_text(encoding="utf-8-sig"))
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if (manifest.get("self_test_protocol") != 1 or manifest.get("version") != __version__
            or manifest.get("sha256", "").lower() != digest
            or manifest.get("file") != exe.name):
        raise ValueError("EXE validation manifest/hash/version mismatch; executable will not be started")
    return manifest


def offline_checks(report: RunReport, exe: Path | None = None) -> bool:
    report.add("Python", "PASS" if sys.version_info >= (3, 10) else "FAIL", sys.version)
    report.add("Windows host", "PASS" if sys.platform == "win32" else "SKIP",
               platform.platform(), required=False)
    try:
        import serial
        import tkinter
        report.add("Dependencies", "PASS", "pySerial and Tk imports succeeded",
                   serial=serial.VERSION, tk=tkinter.TkVersion)
        for cid in READ_ONLY_COMMANDS:
            encode_datagram([checked_line(cid)])
        report.add("Read-only allowlist", "PASS", "All fixed ID/text pairs match the application catalogue",
                   count=len(READ_ONLY_COMMANDS))
    except Exception as exc:
        report.add("Offline preflight", "FAIL", str(exc))
        return False
    source_root = Path(__file__).resolve().parents[1]
    # Only discover this source distribution's tests. An installed wheel must
    # not accidentally discover an unrelated site-packages/../tests directory.
    tests_dir = (source_root.parent / "tests" if source_root.name == "src"
                 and (source_root.parent / "pyproject.toml").is_file() else None)
    for kind in ("gui", "tests"):
        print(f"Checking offline {kind}...", flush=True)
        if kind == "tests" and tests_dir is None:
            report.add("Offline tests", "SKIP", "Test sources are not installed; use the source ZIP", required=False)
            continue
        output = report.directory / f"{kind}.json"
        command = [sys.executable, "-m", "spitfire_control.validation_worker", kind, "--output", str(output)]
        if kind == "tests":
            command.extend(["--tests-dir", str(tests_dir)])
        try:
            result = child_check(command, output, report.directory / f"{kind}-process.txt")
        except Exception as exc:
            result = {"status": "FAIL", "detail": str(exc)}
        report.add(f"Offline {kind}", result["status"], result.get("detail", "Isolated check completed"),
                   required=not (kind == "tests" and result["status"] == "SKIP"), result=result)
        if kind == "gui" and result["status"] == "PASS" and sys.platform == "win32":
            report.data["windows_execution_verified"] = True
    if exe is None:
        report.add("Windows EXE", "SKIP", "No --exe supplied; Python GUI results do not verify a packaged EXE", required=False)
    elif sys.platform != "win32":
        report.add("Windows EXE", "FAIL", "A Windows host is required for --exe")
    else:
        try:
            exe = exe.expanduser().resolve(strict=True)
            manifest = verify_exe_manifest(exe)
            output = report.directory / "exe.json"
            result = child_check([str(exe), "--simulator", "--self-test-report", str(output)],
                                 output, report.directory / "exe-process.txt")
            if result.get("version") != __version__ or result.get("mode") != "simulator":
                raise ValueError("EXE did not return the expected version/simulator evidence")
            report.add("Windows EXE", result["status"], "SHA-256 matched build manifest; self-test completed",
                       manifest=manifest, result=result)
        except Exception as exc:
            report.add("Windows EXE", "FAIL", str(exc))
    return not any(c["required"] and c["status"] != "PASS" for c in report.data["checks"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spitfire offline/Windows and read-only hardware validation")
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("offline", "hardware"):
        p = sub.add_parser(mode)
        p.add_argument("--output", type=Path, default=Path("validation_reports"))
        p.add_argument("--exe", type=Path, help="Optional EXE built with matching .validation.json")
        if mode == "hardware":
            p.add_argument("--host", required=True, help="Explicit unicast IPv4 controller address")
            p.add_argument("--local-host", default="0.0.0.0")
            p.add_argument("--remote-port", type=int, default=1024)
            p.add_argument("--local-port", type=int, default=1024)
            p.add_argument("--timeout", type=float, default=2.0)
            p.add_argument("--interval", type=float, default=.25)
            p.add_argument("--cycles", type=int, default=1)
            p.add_argument("--max-seconds", type=float, default=120)
            p.add_argument("--expect-idn", default="", help="Optional case-insensitive expected IDN substring")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    options = None
    if args.mode == "hardware":
        options = ProbeOptions(**{name: getattr(args, name) for name in ProbeOptions.__dataclass_fields__})
        try:
            options.validate()
        except ValueError as exc:
            parser.error(str(exc))
    try:
        report = RunReport(args.output, args.mode)
    except OSError as exc:
        print(f"Cannot create validation report; no device I/O attempted: {exc}", file=sys.stderr)
        return 1
    interrupted = False
    print(f"Report directory: {report.directory}", flush=True)
    try:
        ready = offline_checks(report, args.exe)
        if options is not None:
            if ready:
                print(f"Read-only UDP check: {options.host}:{options.remote_port}; no writes permitted", flush=True)
                hardware_probe(options, report)
            else:
                report.add("hardware plan", "SKIP", "Offline prerequisite did not pass; no hardware socket opened")
    except KeyboardInterrupt:
        interrupted = True
        report.add("Interrupted", "SKIP", "Ctrl+C; sockets closed without sending any shutdown command")
    except Exception as exc:
        report.add("Validation exception", "FAIL", f"{type(exc).__name__}: {exc}")
    try:
        code = report.finish(interrupted)
    except OSError as exc:
        print(f"Report write failed: {exc}; partial report/trace may remain in {report.directory}", file=sys.stderr)
        return 1
    print(f"{report.data['overall']}: {report.directory / 'report.html'}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

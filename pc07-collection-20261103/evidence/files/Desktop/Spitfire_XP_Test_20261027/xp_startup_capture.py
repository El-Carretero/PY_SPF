"""Bounded XP startup capture using an unmodified Spitfire Twin Verifier.

This standalone helper is a passive UDP fixture, not a hardware proxy. It
answers only the allowed source IPs and does not launch or prove the identity
of a guest program. It intentionally leaves XP-only comparisons INCOMPLETE.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib
import ipaddress
import json
import math
from pathlib import Path
import sys
import threading
import time
import traceback


XP_LABEL = "XP Original 1.6.0"
PYTHON_LABEL = "Python 1.3.0"
XP_SCOPE = "CAPTURE_ONLY_NOT_PROOF_OF_GUI_STARTUP"


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True, type=Path,
                   help="Directory containing the trusted Verifier src folder")
    p.add_argument("--output", required=True, type=Path,
                   help="Fresh output directory; an existing directory is rejected")
    p.add_argument("--bind", choices=("10.19.70.13", "127.0.0.1"), default="10.19.70.13")
    p.add_argument("--port", type=int, default=1024,
                   help="1024 for XP; 0 allowed only for loopback self-tests")
    p.add_argument("--original-ip", help="Defaults to 10.19.70.2, or 127.0.0.2 in loopback mode")
    p.add_argument("--python-ip", help="Defaults to 10.19.70.1, or 127.0.0.3 in loopback mode")
    p.add_argument("--allow-python", action="store_true",
                   help="Also accept the explicit Python IP; XP-only is the default")
    p.add_argument("--duration", type=float, default=60.0, help="Bounded acquisition seconds, 0.2..300")
    p.add_argument("--checkpoint-seconds", type=float, default=3.0, help="Checkpoint interval, 0.1..30")
    p.add_argument("--stop-file", type=Path,
                   help="Stop gracefully when this file exists; defaults to OUTPUT/STOP")
    p.add_argument("--max-transactions", type=int, default=50000)
    p.add_argument("--max-messages", type=int, default=2000)
    return p


def validate(args):
    for value, minimum, maximum, name in (
        (args.duration, 0.2, 300, "duration"),
        (args.checkpoint_seconds, 0.1, 30, "checkpoint interval"),
    ):
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be finite and within {minimum}..{maximum}")
    if not 0 <= args.port <= 65535 or (args.bind != "127.0.0.1" and args.port != 1024):
        raise ValueError("Host-only XP acquisition must use UDP1024; loopback allows 0..65535")
    for value, upper, name in ((args.max_transactions, 250000, "max transactions"),
                               (args.max_messages, 10000, "max messages")):
        if not 1 <= value <= upper:
            raise ValueError(f"{name} must be within 1..{upper}")
    loopback = args.bind == "127.0.0.1"
    args.original_ip = args.original_ip or ("127.0.0.2" if loopback else "10.19.70.2")
    args.python_ip = args.python_ip or ("127.0.0.3" if loopback else "10.19.70.1")
    addresses = [ipaddress.IPv4Address(x) for x in (args.bind, args.original_ip, args.python_ip)]
    if len(set(addresses)) != 3:
        raise ValueError("Bind, XP and Python addresses must be distinct")
    if loopback:
        if not all(a.is_loopback for a in addresses):
            raise ValueError("Loopback tests may only allow loopback clients")
    elif (args.original_ip, args.python_ip) != ("10.19.70.2", "10.19.70.1"):
        raise ValueError("Host-only client addresses are fixed to XP10.19.70.2 and Python10.19.70.1")
    args.project = args.project.resolve(strict=True)
    module_path = args.project / "src" / "spitfire_twin_verifier" / "server.py"
    if not module_path.is_file():
        raise ValueError("--project is not a Verifier source project")
    args.output = args.output.resolve()
    if args.output.exists():
        raise ValueError("Output already exists; choose a fresh acquisition directory")
    args.stop_file = (args.stop_file or args.output / "STOP").resolve()
    if args.stop_file.exists():
        raise ValueError("Stop file already exists; choose a fresh stop-file path")
    return args


def load_api(project):
    sys.path.insert(0, str(project / "src"))
    package = importlib.import_module("spitfire_twin_verifier")
    if Path(package.__file__).resolve().parent != project / "src" / "spitfire_twin_verifier":
        raise RuntimeError("An unrelated installed Verifier module was imported")
    from spitfire_twin_verifier.compare import compare_transactions
    from spitfire_twin_verifier.model import VirtualSpitfire
    from spitfire_twin_verifier.records import CaptureStore
    from spitfire_twin_verifier.report import write_report
    from spitfire_twin_verifier.server import VirtualDeviceServer

    class AllowedClientsServer(VirtualDeviceServer):
        """Drop non-allowlisted IPs before decoding or scheduling a response."""
        def __init__(self, *a, allowed_ips, **kw):
            super().__init__(*a, **kw)
            self.allowed_ips = frozenset(allowed_ips)

        def _process(self, data, sender, received):
            if sender[0] not in self.allowed_ips:
                self.capture.message(
                    "REJECTED", "Packet from non-allowlisted source; no response sent",
                    source_ip=sender[0], source_port=sender[1],
                    raw_hex=data[:1400].hex(" "),
                    details={"datagram_bytes": len(data), "raw_truncated": len(data) > 1400})
                return
            super()._process(data, sender, received)

    return package.__version__, CaptureStore, VirtualSpitfire, AllowedClientsServer, compare_transactions, write_report


def write_json(path, data):
    # New files only, except the caller's freshly created summary file.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def run(args):
    args = validate(args)
    version, CaptureStore, VirtualSpitfire, Server, compare, write_report = load_api(args.project)
    args.output.mkdir(parents=True, exist_ok=False)
    checkpoints = args.output / "checkpoints"
    checkpoints.mkdir()
    allowed = {args.original_ip}
    if args.allow_python:
        allowed.add(args.python_ip)
    capture = CaptureStore()
    device = VirtualSpitfire(isolated_clients=True)
    server = Server(args.bind, args.port, device, capture,
                    {args.original_ip: XP_LABEL, args.python_ip: PYTHON_LABEL}, allowed_ips=allowed)
    started = time.monotonic()
    checkpoints_saved = []
    errors = []
    stop_reason = "NOT_STARTED"
    endpoint = None
    report_directory = None
    acquisition_started = None

    def checkpoint():
        target = checkpoints / f"capture_{len(checkpoints_saved):06d}.jsonl"
        capture.snapshot().save_jsonl(target)
        checkpoints_saved.append(str(target))

    try:
        server.start()
        endpoint = server.local_address
        acquisition_started = time.monotonic()
        capture.set_metadata(
            harness="xp_startup_capture.py", harness_version="1.0.0",
            verifier_version=version, xp_runtime_validation=XP_SCOPE,
            physical_validation="UNVERIFIED", gui_observation="NOT_PERFORMED_BY_HARNESS",
            peer_identity="Source IP classification only; not process authentication",
            allowed_source_ips=sorted(allowed), bound_address=list(endpoint),
            acquisition_duration_limit_seconds=args.duration,
            scope="Passive virtual UDP fixture; no physical controller destination or proxy",
        )
        capture.mark_scenario("XP startup nominal fixture")
        ready = {"status": "LISTENING", "version": version,
                 "endpoint": list(endpoint), "allowed_source_ips": sorted(allowed),
                 "stop_file": str(args.stop_file), "xp_runtime_validation": XP_SCOPE,
                 "created_utc": datetime.now(timezone.utc).isoformat()}
        write_json(args.output / "ready.json", ready)
        print(json.dumps(ready, ensure_ascii=False), flush=True)
        checkpoint()
        next_checkpoint = acquisition_started + args.checkpoint_seconds
        pause = threading.Event()
        while True:
            now = time.monotonic()
            if args.stop_file.exists():
                stop_reason = "STOP_FILE"
                break
            if now - acquisition_started >= args.duration:
                stop_reason = "DURATION_LIMIT"
                break
            if not server.running:
                raise RuntimeError("UDP server exited before the acquisition ended")
            snapshot = capture.snapshot()
            if len(snapshot.transactions) >= args.max_transactions or len(snapshot.messages) >= args.max_messages:
                stop_reason = "EVIDENCE_LIMIT"
                break
            if now >= next_checkpoint:
                checkpoint()
                next_checkpoint = now + args.checkpoint_seconds
            pause.wait(min(0.1, max(0.0, args.duration - (now - acquisition_started))))
    except KeyboardInterrupt:
        stop_reason = "KEYBOARD_INTERRUPT"
        capture.message("HARNESS", "Graceful interruption requested")
    except Exception as exc:
        stop_reason = "ERROR"
        errors.append({"stage": "acquisition", "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc()})
        capture.message("HARNESS_ERROR", str(exc))
    finally:
        try:
            server.stop()
        except Exception as exc:
            errors.append({"stage": "stop", "error": f"{type(exc).__name__}: {exc}"})
        capture.set_metadata(xp_runtime_validation=XP_SCOPE, physical_validation="UNVERIFIED",
                             acquisition_stop_reason=stop_reason)
        try:
            checkpoint()
        except Exception as exc:
            errors.append({"stage": "checkpoint", "error": f"{type(exc).__name__}: {exc}"})
        final = capture.snapshot()
        result = None
        server_errors = [m.message for m in final.messages if m.level == "ERROR"]
        if server_errors:
            errors.append({"stage": "server", "messages": server_errors})
        try:
            result = compare(final, XP_LABEL, PYTHON_LABEL)
            report_directory = write_report(args.output / "reports", result, final)
        except Exception as exc:
            errors.append({"stage": "report", "error": f"{type(exc).__name__}: {exc}"})
        xp = [t for t in final.transactions if t.client_label == XP_LABEL]
        py = [t for t in final.transactions if t.client_label == PYTHON_LABEL]
        if errors:
            status, exit_code = "ACQUISITION_ERROR", 2
        elif stop_reason == "EVIDENCE_LIMIT":
            status, exit_code = "EVIDENCE_LIMIT_REACHED", 3
        elif not xp:
            status, exit_code = "NO_XP_TRANSACTIONS", 3
        else:
            status, exit_code = "CAPTURE_SAVED_NOT_XP_VALIDATION", 0
        summary = {
            "status": status, "exit_code": exit_code, "verifier_version": version,
            "stop_reason": stop_reason, "elapsed_seconds": time.monotonic() - started,
            "acquisition_seconds": (time.monotonic() - acquisition_started) if acquisition_started else 0,
            "endpoint": list(endpoint) if endpoint else None, "allowed_source_ips": sorted(allowed),
            "xp_runtime_validation": XP_SCOPE, "physical_validation": "UNVERIFIED",
            "comparison_verdict": result.verdict if result else "UNAVAILABLE",
            "gui_verdict": result.gui_verdict if result else "NOT_CHECKED",
            "xp_transactions": len(xp), "python_transactions": len(py),
            "xp_command_ids": sorted({t.command_id for t in xp}),
            "xp_write_commands": [{"id": t.command_id, "command": t.command, "argument": t.argument,
                                    "response": t.response_value, "status": t.status}
                                   for t in xp if t.writable],
            "transaction_status_counts": dict(Counter(t.status for t in final.transactions)),
            "validation_counts": dict(Counter(t.validation for t in final.transactions)),
            "message_level_counts": dict(Counter(m.level for m in final.messages)),
            "pending": list(final.pending), "errors": errors,
            "checkpoints": checkpoints_saved,
            "report_directory": str(report_directory) if report_directory else None,
            "notes": ["Exit 0 means capture was saved, not XP startup or equivalence PASS.",
                      "Original process/version/GUI must be observed independently.",
                      "Source IP is not process authentication."]}
        write_json(args.output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return exit_code


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return run(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Harness could not start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

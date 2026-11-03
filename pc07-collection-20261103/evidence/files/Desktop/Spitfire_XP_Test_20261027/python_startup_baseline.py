"""Bounded, read-only baseline of the real Python controller on loopback UDP.

This is a backend acquisition, not a GUI test, hardware validation, or proof of
equivalence with XP. It does not load or save the user's application settings.
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

SCOPE = "HEADLESS_REAL_CONTROLLER_LOOPBACK_BASELINE_NOT_GUI_OR_EQUIVALENCE"
LOOPBACK = "127.0.0.1"
LABEL = "Python 1.3.0 backend baseline"
MAX_EVENTS = 10000
MAX_TRANSACTIONS = 10000


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client-project", required=True, type=Path)
    p.add_argument("--verifier-project", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--duration", type=float, default=30.0,
                   help="Acquisition duration in seconds, 0.2..60; default 30")
    return p


def validate(args):
    if not math.isfinite(args.duration) or not 0.2 <= args.duration <= 60:
        raise ValueError("Duration must be finite and within 0.2..60 seconds")
    for key, package, module in (("client_project", "spitfire_control", "controller.py"),
                                 ("verifier_project", "spitfire_twin_verifier", "server.py")):
        value = getattr(args, key).resolve(strict=True)
        if not (value / "src" / package / module).is_file():
            raise ValueError(f"{key} is not the expected trusted source project")
        setattr(args, key, value)
    args.output = args.output.resolve()
    if args.output.exists():
        raise ValueError("Output exists; a fresh acquisition directory is required")
    for source in (args.client_project, args.verifier_project):
        if args.output == source or args.output.is_relative_to(source):
            raise ValueError("Output must be outside the trusted source projects")
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
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=json_default)
        stream.write("\n")


def load_api(client_project, verifier_project):
    for source, package in ((client_project, "spitfire_control"),
                            (verifier_project, "spitfire_twin_verifier")):
        sys.path.insert(0, str(source / "src"))
        imported = importlib.import_module(package)
        if Path(imported.__file__).resolve().parent != source / "src" / package:
            raise RuntimeError(f"An unrelated installed {package} module was imported")
    from spitfire_control import __version__ as client_version
    from spitfire_control.controller import LaserController
    from spitfire_control.transport import UdpSettings, UdpTransport, TransportError
    from spitfire_twin_verifier import __version__ as verifier_version
    from spitfire_twin_verifier.model import VirtualSpitfire
    from spitfire_twin_verifier.records import CaptureStore
    from spitfire_twin_verifier.server import VirtualDeviceServer
    if client_version != "1.3.0":
        raise ValueError(f"This baseline is pinned to client 1.3.0, got {client_version}")

    class ReadOnlyLoopbackTransport(UdpTransport):
        """Real UDP transport with additional harness-only outbound constraints."""
        def __init__(self, port):
            self.expected_port = int(port)
            self.blocked_attempts = []
            super().__init__(UdpSettings(remote_host=LOOPBACK, remote_port=port,
                                         local_host=LOOPBACK, local_port=0))

        def _check_endpoint(self):
            s = self.settings
            if (s.remote_host, int(s.remote_port), s.local_host, int(s.local_port)) != (
                    LOOPBACK, self.expected_port, LOOPBACK, 0):
                raise TransportError("Harness forbids changing loopback-only endpoints")
            if not 1024 < self.expected_port <= 65535:
                raise TransportError("Harness requires an ephemeral non-instrument port")

        def connect(self):
            self._check_endpoint()
            super().connect()

        def exchange(self, command_line, timeout, *, send_guard=None):
            self._check_endpoint()
            match = re.fullmatch(r"\[(\d+)\][^\r\n]+", command_line)
            if match is None or not 1000 <= int(match.group(1)) < 2000:
                self.blocked_attempts.append(command_line)
                raise TransportError("Harness blocks every write before UDP send")
            return super().exchange(command_line, timeout, send_guard=send_guard)

    return (client_version, verifier_version, LaserController, ReadOnlyLoopbackTransport,
            VirtualSpitfire, CaptureStore, VirtualDeviceServer)


def source_hashes(project, package):
    root = project / "src" / package
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.py"))}


def run(args):
    args = validate(args)
    (client_version, verifier_version, Controller, Transport, Device, Store, Server) = load_api(
        args.client_project, args.verifier_project)
    args.output.mkdir(parents=True, exist_ok=False)
    capture = Store()
    device = Device(isolated_clients=True)
    server = Server(LOOPBACK, 0, device, capture, {LOOPBACK: LABEL})
    transport = controller = None
    errors = []
    events = []
    states = []
    endpoint = None
    state_before_stop = None
    initial_ids = []
    poll_ids = []
    acquisition_started = None
    stop_reason = "NOT_STARTED"
    started = time.monotonic()

    def utc():
        return datetime.now(timezone.utc).isoformat()

    def drain_events():
        while controller is not None:
            try:
                event = controller.events.get_nowait()
            except queue.Empty:
                break
            if len(events) >= MAX_EVENTS:
                raise RuntimeError("Backend event evidence limit reached")
            state = event.state
            events.append({"observed_utc": utc(), "kind": event.kind,
                           "message": event.message, "reply": asdict(event.reply) if event.reply else None,
                           "state_flags": None if state is None else {
                               "connected": state.connected, "transport_open": state.transport_open,
                               "armed": state.armed, "last_error": state.last_error,
                               "invalid_ids": sorted(state.invalid_ids),
                               "pending_readbacks": sorted(state.pending_readbacks)}})
            if state is not None and state.armed:
                raise RuntimeError("Unexpected armed state in read-only baseline")

    try:
        server.start()
        endpoint = server.local_address
        if endpoint[0] != LOOPBACK:
            raise RuntimeError("Unexpected nonloopback fixture bind")
        transport = Transport(endpoint[1])
        controller = Controller(transport, timeout=1.0, poll_interval=1.0,
                                auto_poll=True, monitor_hv=False,
                                log_directory=str(args.output / "client_audit"), pump_mode="empower")
        initial_ids = list(controller._initial_ids())
        poll_ids = list(controller._poll_ids())
        if any(cid >= 2000 for cid in initial_ids + poll_ids):
            raise RuntimeError("Read-only baseline schedule contains a write")
        capture.set_metadata(harness="python_startup_baseline.py", harness_version="1.0.0",
                             scope=SCOPE, client_version=client_version, verifier_version=verifier_version,
                             gui_validation="NOT_PERFORMED", physical_validation="UNVERIFIED",
                             equivalence_validation="INCOMPLETE", endpoint=list(endpoint),
                             read_only_outbound_guard=True, no_arm_requested=True,
                             client_settings_loaded=False, source_ip_not_process_authentication=True)
        capture.mark_scenario("Python 1.3.0 startup nominal loopback baseline")
        ready = {"status": "LISTENING", "endpoint": list(endpoint), "scope": SCOPE,
                 "duration_limit_seconds": args.duration, "created_utc": utc()}
        write_json(args.output / "ready.json", ready)
        print(json.dumps(ready), flush=True)
        controller.start()
        acquisition_started = time.monotonic()
        next_snapshot = acquisition_started
        pause = threading.Event()
        while time.monotonic() - acquisition_started < args.duration:
            drain_events()
            if not controller.running:
                raise RuntimeError("Controller worker exited before duration limit")
            if not server.running:
                raise RuntimeError("Virtual fixture exited before duration limit")
            if len(capture.snapshot().transactions) >= MAX_TRANSACTIONS:
                raise RuntimeError("Wire evidence limit reached")
            now = time.monotonic()
            if now >= next_snapshot:
                states.append({"observed_utc": utc(), "state": asdict(controller.state)})
                next_snapshot = now + 1.0
            pause.wait(min(0.025, max(0.0, args.duration - (now - acquisition_started))))
        state_before_stop = asdict(controller.state)
        drain_events()
        stop_reason = "DURATION_LIMIT"
    except KeyboardInterrupt:
        stop_reason = "KEYBOARD_INTERRUPT"
    except Exception as exc:
        stop_reason = "ERROR"
        errors.append({"stage": "acquisition", "error": f"{type(exc).__name__}: {exc}",
                       "traceback": traceback.format_exc()})
    finally:
        if controller is not None:
            try:
                if state_before_stop is None:
                    state_before_stop = asdict(controller.state)
                controller.stop()
                drain_events()
                if controller.running:
                    raise RuntimeError("Controller did not stop cleanly")
            except Exception as exc:
                errors.append({"stage": "controller_stop", "error": str(exc)})
        if transport is not None:
            try:
                transport.close()
            except Exception as exc:
                errors.append({"stage": "transport_stop", "error": str(exc)})
        try:
            server.stop()
        except Exception as exc:
            errors.append({"stage": "fixture_stop", "error": str(exc)})
        snapshot = capture.snapshot()
        snapshot.save_jsonl(args.output / "capture.jsonl")
        write_json(args.output / "events.json", events)
        write_json(args.output / "states.json", {"snapshots": states,
                                                "last_state_before_cleanup": state_before_stop})
        tx = snapshot.transactions
        errors.extend({"stage": "client_event", "error": e["message"]}
                      for e in events if e["kind"] == "error")
        errors.extend({"stage": "fixture", "error": m.message}
                      for m in snapshot.messages if m.level in {"ERROR", "PROTOCOL", "REJECTED"})
        blocked = list(transport.blocked_attempts) if transport is not None else []
        writes = [t.command_id for t in tx if t.writable]
        invalid = [t.sequence for t in tx if t.status != "REPLIED" or t.validation != "VALID"]
        connected = bool(state_before_stop and state_before_stop["connected"])
        good = (stop_reason == "DURATION_LIMIT" and not errors and tx and connected
                and not blocked and not writes and not invalid and not snapshot.pending)
        exit_code = 0 if good else 2
        summary = {"status": "BACKEND_BASELINE_CAPTURED" if good else "BASELINE_INCOMPLETE_OR_ERROR",
                   "exit_code": exit_code, "scope": SCOPE, "stop_reason": stop_reason,
                   "client_version": client_version, "verifier_version": verifier_version,
                   "runtime": {"platform": platform.platform(), "python": sys.version},
                   "endpoint": list(endpoint) if endpoint else None,
                   "elapsed_seconds": time.monotonic() - started,
                   "requested_acquisition_seconds": args.duration,
                   "transactions": len(tx), "command_ids": sorted({t.command_id for t in tx}),
                   "command_counts": dict(Counter(t.command_id for t in tx)),
                   "initial_readonly_schedule_ids": initial_ids, "automatic_poll_schedule_ids": poll_ids,
                   "heartbeat_id": 1000, "heartbeat_interval_seconds": 1.0,
                   "write_ids": writes, "blocked_outbound_attempts": blocked,
                   "invalid_transaction_sequences": invalid, "pending": list(snapshot.pending),
                   "event_kind_counts": dict(Counter(e["kind"] for e in events)),
                   "connected_before_cleanup": connected, "errors": errors,
                   "gui_validation": "NOT_PERFORMED", "physical_validation": "UNVERIFIED",
                   "xp_python_equivalence": "INCOMPLETE",
                   "client_source_hashes": source_hashes(args.client_project, "spitfire_control"),
                   "verifier_source_hashes": source_hashes(args.verifier_project, "spitfire_twin_verifier"),
                   "notes": ["Real LaserController and UdpTransport backend, no GUI launched.",
                             "Nominal synthetic fixture; no physical hardware traffic.",
                             "Fresh independent device state, not shared with XP capture.",
                             "No ARM or write command was requested; extra harness guard blocks writes.",
                             "Exit 0 means baseline acquired, not equivalence or physical validation."]}
        write_json(args.output / "summary.json", summary)
        print(json.dumps({k: v for k, v in summary.items() if k not in {
            "client_source_hashes", "verifier_source_hashes", "command_counts"}}, default=json_default), flush=True)
    return exit_code


def main():
    try:
        return run(parser().parse_args())
    except Exception as exc:
        print(json.dumps({"status": "PREFLIGHT_OR_SAVE_ERROR", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

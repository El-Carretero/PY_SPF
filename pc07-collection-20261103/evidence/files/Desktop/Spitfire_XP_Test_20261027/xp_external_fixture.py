"""Passive, bounded XP virtual-device fixture with explicit staged stimuli.

No hardware proxy, no outbound instrument commands, and no claim of firmware
or optical equivalence. Only replies to the one allowlisted virtual client.
Product source is imported unchanged from an explicitly supplied directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
import threading
import time
import traceback

VERSION = "1.0.0"
SCOPE = "XP_VIRTUAL_FIXTURE_CAPTURE_NOT_FIRMWARE_OR_OPTICAL_VALIDATION"
LABEL = "XP Original 1.6.0"
BASE_OVERRIDES = {1050: "EXT", 1051: "EXT", 1067: "EXT", 1065: "80", 1021: "0", 1039: "0"}
OVERRIDE_IDS = frozenset({1013, 1014, 1015, 1019, 1021, 1028, 1033, 1039, 1044,
                          1045, 1046, 1050, 1051, 1065, 1066, 1067, 1068, 1069,
                          1078, 1087, 1088, 1089})
FAULT_IDS = frozenset(range(1000, 1090)) | {2036}
MAX_CONTROL_BYTES = 32768
MAX_TRANSACTIONS = 100000
MAX_MESSAGES = 10000


def utc():
    return datetime.now(timezone.utc).isoformat()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--duration", type=float, default=900)
    p.add_argument("--checkpoint-seconds", type=float, default=2)
    p.add_argument("--loopback-test", action="store_true",
                   help="Bind 127.0.0.1 ephemeral port; accept 127.0.0.2 only")
    return p


def validate(args):
    for value, low, high, label in ((args.duration, .2, 1800, "duration"),
                                    (args.checkpoint_seconds, .05, 30, "checkpoint")):
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{label} must be finite and in {low}..{high}")
    args.project = args.project.resolve(strict=True)
    if not (args.project / "src/spitfire_twin_verifier/server.py").is_file():
        raise ValueError("Expected trusted Verifier source project")
    args.output = args.output.resolve()
    if args.output.exists():
        raise ValueError("Output already exists; use a fresh acquisition directory")
    if args.output == args.project or args.output.is_relative_to(args.project):
        raise ValueError("Evidence must be outside product source")
    return args


def load_api(project):
    sys.path.insert(0, str(project / "src"))
    package = importlib.import_module("spitfire_twin_verifier")
    if Path(package.__file__).resolve().parent != project / "src/spitfire_twin_verifier":
        raise RuntimeError("Unexpected installed Verifier imported")
    from spitfire_twin_verifier.model import VirtualSpitfire, ResponseProfile
    from spitfire_twin_verifier.records import CaptureStore
    from spitfire_twin_verifier.server import VirtualDeviceServer

    class AllowedClientServer(VirtualDeviceServer):
        def __init__(self, *a, allowed_ip, **kw):
            super().__init__(*a, **kw)
            self.allowed_ip = allowed_ip

        def _process(self, data, sender, received):
            if sender[0] != self.allowed_ip:
                self.capture.message("REJECTED", "Non-allowlisted source; no reply",
                                     source_ip=sender[0], source_port=sender[1],
                                     raw_hex=data[:1400].hex(" "))
                return
            if len(self.capture._transactions) >= MAX_TRANSACTIONS:
                self.capture.message("LIMIT", "Transaction evidence limit reached")
                self._stop.set()
                return
            super()._process(data, sender, received)

    return package.__version__, VirtualSpitfire, ResponseProfile, CaptureStore, AllowedClientServer


def atomic_json(path, data):
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_capture(path, snapshot):
    fd, temp = tempfile.mkstemp(prefix="capture.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        snapshot.save_jsonl(Path(temp))
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _id(value, allowed):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("Command ID must be canonical decimal")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid command ID") from exc
    if str(number) != str(value) or number not in allowed:
        raise ValueError(f"Command ID {value!r} not allowlisted")
    return number


def validate_control(raw, expected_seq):
    if not isinstance(raw, dict):
        raise ValueError("Control must be an object")
    allowed = {"seq", "stage", "overrides", "error_ids", "drop_ids", "request_drop_ids", "delay_ms", "reset_device", "note"}
    if set(raw) - allowed:
        raise ValueError("Unknown control fields")
    if type(raw.get("seq")) is not int or raw["seq"] != expected_seq:
        raise ValueError("Control sequence must match next numbered filename")
    stage = raw.get("stage")
    if not isinstance(stage, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", stage):
        raise ValueError("Stage must be 1..80 ASCII letters/digits/underscore/hyphen")
    if type(raw.get("reset_device", False)) is not bool:
        raise ValueError("reset_device must be boolean")
    note = raw.get("note", "")
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError("note must be text <=1000 characters")
    result = {"seq": expected_seq, "stage": stage, "reset_device": raw.get("reset_device", False), "note": note}
    overrides = raw.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    result["overrides"] = {}
    for key, value in overrides.items():
        cid = _id(key, OVERRIDE_IDS)
        if not isinstance(value, str) or not value.isascii() or len(value) > 128 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Override values must be single-line ASCII strings <=128 characters")
        result["overrides"][cid] = value
    for field in ("error_ids", "drop_ids", "request_drop_ids"):
        values = raw.get(field, [])
        if not isinstance(values, list) or len(values) > len(FAULT_IDS):
            raise ValueError(f"Invalid {field}")
        ids = [_id(value, FAULT_IDS) for value in values]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {field}")
        result[field] = ids
    delays = raw.get("delay_ms", {})
    if not isinstance(delays, dict):
        raise ValueError("delay_ms must be an object")
    result["delay_ms"] = {}
    for key, value in delays.items():
        cid = _id(key, FAULT_IDS)
        if type(value) is not int or not 0 <= value <= 15000:
            raise ValueError("Delay must be integer 0..15000ms")
        result["delay_ms"][cid] = value
    return result


def make_profile(Profile, control):
    overrides = dict(BASE_OVERRIDES)
    overrides.update(control.get("overrides", {}))
    return Profile(name=control["stage"], overrides=overrides,
                   error_ids=set(control.get("error_ids", [])),
                   drop_ids=set(control.get("drop_ids", [])),
                   request_drop_ids=set(control.get("request_drop_ids", [])),
                   delay_ms=dict(control.get("delay_ms", {})))


def stage_counts(snapshot):
    result = {}
    for transaction in snapshot.transactions:
        row = result.setdefault(transaction.scenario, {"transactions": 0, "ids": {}, "status": {}})
        row["transactions"] += 1
        cid = str(transaction.command_id)
        row["ids"][cid] = row["ids"].get(cid, 0) + 1
        row["status"][transaction.status] = row["status"].get(transaction.status, 0) + 1
    return result


def run(args):
    args = validate(args)
    version, Device, Profile, Store, Server = load_api(args.project)
    args.output.mkdir(parents=True, exist_ok=False)
    controls = args.output / "controls"
    controls.mkdir()
    stages_dir = args.output / "stages"
    stages_dir.mkdir()
    bind, port, allowed_ip = (("127.0.0.1", 0, "127.0.0.2") if args.loopback_test else
                              ("10.19.70.13", 1024, "10.19.70.2"))
    capture = Store()
    device = Device(isolated_clients=True)
    active = {"seq": 0, "stage": "external_reference_optout0", "overrides": {}, "reset_device": False}
    device.set_profile(make_profile(Profile, active))
    server = Server(bind, port, device, capture, {allowed_ip: LABEL}, allowed_ip=allowed_ip)
    applied = []
    errors = []
    rejected_controls = []
    started = time.monotonic()
    state = "STARTING"
    stop_reason = "NOT_STARTED"
    last_seq = 0
    rejected_seq = set()
    hashes = {p.relative_to(args.project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((args.project / "src/spitfire_twin_verifier").rglob("*.py"))}

    def checkpoint(final=False):
        snap = capture.snapshot()
        atomic_capture(args.output / "capture.jsonl", snap)
        data = {"status": state, "scope": SCOPE, "harness_version": VERSION,
                "created_utc": utc(), "elapsed_seconds": time.monotonic() - started,
                "duration_limit_seconds": args.duration, "stop_reason": stop_reason,
                "endpoint": list(server.local_address) if server.local_address else None,
                "allowed_source_ip": allowed_ip, "stage": active["stage"], "last_control_seq": last_seq,
                "active_profile": device.get_profile().to_dict(), "transactions": len(snap.transactions),
                "stage_counts": stage_counts(snap), "pending": list(snap.pending),
                "last_transactions": [asdict(t) for t in snap.transactions[-15:]],
                "message_counts": dict(Counter(m.level for m in snap.messages)),
                "applied_controls": applied, "rejected_controls": rejected_controls, "errors": errors,
                "gui_validation": "ROOT_OBSERVATIONS_REQUIRED", "physical_validation": "UNVERIFIED",
                "xp_python_equivalence": "INCOMPLETE", "source_ip_is_not_process_authentication": True}
        atomic_json(args.output / "status.json", data)
        if final:
            data.update(runtime={"platform": platform.platform(), "python": sys.version},
                        verifier_version=version, source_hashes=hashes,
                        notes=["Only replies to the allowlisted virtual client; no hardware proxy.",
                               "Control profiles are explicit synthetic stimuli, not firmware behavior.",
                               "Exit 0 means saved capture, not XP/Python equivalence or GUI PASS.",
                               "Fixed EXT/seed/HV readbacks are fixture assumptions, not measurements.",
                               "Stage tags are latched at request reception; delayed replies retain original stage.",
                               "Opt-out starts at model default 0 and is writable unless overridden explicitly."])
            atomic_json(args.output / "summary.json", data)
        return snap

    try:
        server.start()
        capture.mark_scenario(active["stage"])
        capture.set_metadata(harness="xp_external_fixture.py", harness_version=VERSION,
                             scope=SCOPE, allowed_source_ip=allowed_ip, physical_validation="UNVERIFIED",
                             profile_policy="external-reference fixed EXT/seed/HV; opt-out mutable")
        ready = {"status": "LISTENING", "endpoint": list(server.local_address),
                 "allowed_source_ip": allowed_ip, "controls_directory": str(controls),
                 "stop_file": str(args.output / "STOP"), "scope": SCOPE, "created_utc": utc()}
        atomic_json(args.output / "ready.json", ready)
        print(json.dumps(ready), flush=True)
        state, stop_reason = "LISTENING", "DURATION_LIMIT"
        next_checkpoint = 0.0
        while time.monotonic() - started < args.duration:
            if (args.output / "STOP").exists():
                stop_reason = "STOP_FILE"
                break
            if not server.running:
                raise RuntimeError("Fixture worker stopped unexpectedly")
            snap = capture.snapshot()
            if len(snap.transactions) >= MAX_TRANSACTIONS or len(snap.messages) >= MAX_MESSAGES:
                stop_reason = "EVIDENCE_LIMIT"
                break
            seq = last_seq + 1
            control_path = controls / f"{seq:06d}.json"
            if control_path.is_file() and seq not in rejected_seq:
                try:
                    if control_path.stat().st_size > MAX_CONTROL_BYTES:
                        raise ValueError("Control file exceeds size limit")
                    raw_bytes = control_path.read_bytes()
                    control = validate_control(json.loads(raw_bytes.decode("utf-8-sig")), seq)
                    # Use the server's request lock so reset/profile/tag form one boundary.
                    with server._gate, capture.locked():
                        before = capture.snapshot()
                        if control["reset_device"] and before.pending:
                            raise ValueError("Cannot reset device while delayed replies are pending")
                        stage_path = stages_dir / f"{last_seq:06d}_{active['stage']}.jsonl"
                        atomic_capture(stage_path, before)
                        if control["reset_device"]:
                            device.reset()
                            capture.message("DEVICE_RESET", "Synthetic device state reset; evidence preserved",
                                            details={"seq": seq, "stage": control["stage"]})
                        server.set_profile(make_profile(Profile, control))
                        capture.mark_scenario(control["stage"])
                        record = {"applied_utc": utc(), "control": control,
                                  "control_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                                  "last_prior_transaction": before.transactions[-1].sequence if before.transactions else 0}
                        applied.append(record)
                        capture.message("CONTROL", "Explicit synthetic profile applied", details=record)
                        active, last_seq = control, seq
                    print(json.dumps({"control_applied": seq, "stage": active["stage"]}), flush=True)
                    checkpoint()
                except (ValueError, OSError, UnicodeError) as exc:
                    rejection = {"seq": seq, "rejected_utc": utc(), "error": str(exc)}
                    rejected_controls.append(rejection)
                    rejected_seq.add(seq)
                    capture.message("CONTROL_REJECTED", str(exc), details=rejection)
                    print(json.dumps({"control_rejected": rejection}), flush=True)
            if time.monotonic() >= next_checkpoint:
                checkpoint()
                next_checkpoint = time.monotonic() + args.checkpoint_seconds
            threading.Event().wait(.05)
    except KeyboardInterrupt:
        stop_reason = "KEYBOARD_INTERRUPT"
    except Exception as exc:
        stop_reason = "ERROR"
        errors.append({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
    finally:
        server.stop()
        state = "CAPTURE_SAVED" if not errors else "ACQUISITION_ERROR"
        snap = checkpoint(final=True)
        atomic_capture(stages_dir / f"{last_seq:06d}_{active['stage']}.jsonl", snap)
        print(json.dumps({"status": state, "stop_reason": stop_reason,
                          "transactions": len(snap.transactions), "errors": errors}), flush=True)
    return 2 if errors else (3 if stop_reason == "EVIDENCE_LIMIT" else 0)


def main(argv=None):
    try:
        return run(parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"status": "PREFLIGHT_OR_SAVE_ERROR", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

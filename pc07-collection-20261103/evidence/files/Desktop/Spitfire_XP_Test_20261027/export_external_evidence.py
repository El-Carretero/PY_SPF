"""Export one completed external-mode capture's allowlisted text evidence.

Historical ready.json may say LISTENING; only final summary.json/status.json
are completion authorities. This does not inspect or terminate remote processes.
No screenshots, cumulative stages, sources, archives, or old transfers are read.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

TEXT_SUFFIXES = {".json", ".jsonl", ".csv"}
CHILDREN = {"client_audit", "controls"}
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
XP_FINAL = {"CAPTURE_SAVED", "ACQUISITION_ERROR"}
PYTHON_FINAL = {"SYNTHETIC_EXTERNAL_CASES_PASS", "INCOMPLETE_OR_FAILED"}


def safe_file(path: Path, root: Path) -> Path:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ValueError(f"Links are not evidence files: {path.name}")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Not a regular file: {path.name}")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("Evidence path escapes capture root")
    parts = path.relative_to(root).parts
    if any(p in {"", ".", ".."} or "\\" in p or ":" in p or any(ord(c) < 32 for c in p) for p in parts):
        raise ValueError("Unsafe archive entry name")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Evidence file exceeds bounded export size")
    return path


def read_json(path: Path, root: Path):
    return json.loads(safe_file(path, root).read_text(encoding="utf-8-sig"))


def validate_completed(root: Path) -> dict:
    summary = read_json(root / "summary.json", root)
    if not isinstance(summary, dict):
        raise ValueError("summary.json must contain an object")
    status = summary.get("status")
    if status not in XP_FINAL | PYTHON_FINAL:
        raise ValueError(f"Capture has no recognized final status: {status!r}")
    if status in XP_FINAL:
        if summary.get("endpoint") is not None:
            raise ValueError("Final XP summary still reports a listening endpoint")
        if summary.get("stop_reason") not in {"STOP_FILE", "DURATION_LIMIT", "EVIDENCE_LIMIT", "KEYBOARD_INTERRUPT", "ERROR"}:
            raise ValueError("XP summary has no recognized stop reason")
    else:
        for field in ("final_controller_running", "final_fixture_running"):
            if summary.get(field) is not False:
                raise ValueError(f"Python capture is not stopped: {field}")
    status_path = root / "status.json"
    if status_path.exists() or status_path.is_symlink():
        current = read_json(status_path, root)
        if not isinstance(current, dict) or current.get("status") != status:
            raise ValueError("status.json disagrees with the completed summary")
        if current.get("endpoint") is not None:
            raise ValueError("status.json still reports an active endpoint")
    return summary


def collect_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.iterdir()):
        if path.name in CHILDREN:
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("Evidence child directory must not be a link")
            if not path.is_dir():
                raise ValueError("Expected evidence child directory")
            for child in sorted(path.iterdir()):
                if child.suffix.lower() in TEXT_SUFFIXES:
                    files.append(safe_file(child, root))
        elif path.suffix.lower() in TEXT_SUFFIXES:
            files.append(safe_file(path, root))
    if root / "capture.jsonl" not in files:
        raise ValueError("Completed capture.jsonl is required")
    if sum(p.stat().st_size for p in files) > MAX_TOTAL_BYTES:
        raise ValueError("Evidence exceeds bounded total export size")
    return files


def export(root: Path, destination: Path) -> dict:
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        raise ValueError("Capture root must not be a link")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Capture root must be a directory")
    destination = destination.absolute()
    if destination.suffix.lower() != ".zip":
        raise ValueError("Destination must have a .zip suffix")
    if not destination.parent.is_dir():
        raise ValueError("Destination parent must already exist")
    destination = destination.parent.resolve(strict=True) / destination.name
    sidecar = destination.with_suffix(".b64")
    if os.path.lexists(destination) or os.path.lexists(sidecar):
        raise ValueError("Archive and base64 sidecar must both be fresh paths")
    summary = validate_completed(root)
    paths = collect_files(root)
    # Take a bounded byte snapshot; export must not silently mix file revisions.
    payloads = []
    observed_stats = []
    for path in paths:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(data) != before.st_size:
            raise ValueError("Evidence changed while being read")
        payloads.append((path.relative_to(root).as_posix(), data))
        observed_stats.append((path, after.st_size, after.st_mtime_ns))
    for path, size, mtime in observed_stats:
        current = path.stat()
        if (current.st_size, current.st_mtime_ns) != (size, mtime):
            raise ValueError("Evidence changed during export snapshot")
    if validate_completed(root) != summary:
        raise ValueError("Summary changed during export")
    records = [{"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
               for name, data in payloads]
    manifest = "".join(f"{r['sha256']}  {r['name']}\n" for r in records).encode("utf-8")
    # Exclusive creation preserves all pre-existing archives, including races.
    with destination.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in payloads:
                archive.writestr(name, data)
            archive.writestr("SHA256SUMS.txt", manifest)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("Export archive CRC verification failed")
    payload = destination.read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    with sidecar.open("x", encoding="ascii", newline="\n") as stream:
        for offset in range(0, len(encoded), 8000):
            stream.write(encoded[offset:offset + 8000] + "\n")
    return {"status": "COMPLETED_TEXT_EVIDENCE_EXPORTED", "source_status": summary["status"],
            "capture_root": str(root), "archive": str(destination),
            "archive_sha256": hashlib.sha256(payload).hexdigest(), "archive_bytes": len(payload),
            "base64_file": str(sidecar), "base64_characters": len(encoded),
            "base64_lines": (len(encoded) + 7999) // 8000, "files": records,
            "excluded": ["stages", "screenshots", "other directories", "source code", "existing archives/transfers"],
            "xp_python_equivalence": "NOT_EVALUATED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export(args.root, args.destination), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "EXPORT_ERROR", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

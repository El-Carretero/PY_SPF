#!/usr/bin/env python3
"""Offline source provenance and command-table comparison (Python 3.10+).

From the repository root:
  python comparisons/spitfire-control-1.5.1/verify_snapshot.py
  python comparisons/spitfire-control-1.5.1/verify_snapshot.py --archive /path/to/Spitfire_Python_Control_1.5.1.zip

Maintainers can reproduce the committed data from the original archive with:
  python comparisons/spitfire-control-1.5.1/verify_snapshot.py --generate --archive /path/to/Spitfire_Python_Control_1.5.1.zip

The script uses only the standard library, parses Python literals with ast, and
never imports either application, opens sockets, or changes the imported tree.
The command comparison concerns IDs and literal names, not runtime equivalence.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
VARIANT_REL = "variants/spitfire-control-1.5.1"
BASELINE_COMMIT = "2faf7e16f410096f9fe8c987a680cb128dfb5ba2"
BASELINE_PROTOCOL_SHA256 = "ac094bff051910341d1d5cfdb6b0f4cace66f9bb619ea2b74f0393199e87ab77"
ARCHIVE_NAME = "Spitfire_Python_Control_1.5.1.zip"
ARCHIVE_SHA256 = "7ec75b0bff448bab932252ed524761eba4c101be1d1d6fb86099fe98ec863c00"
ARCHIVE_ROOT = "Spitfire_Python_Control_1.5.1"
SOURCE_PATHS = {
    "baseline": "spitfire/protocol.py",
    "variant": f"{VARIANT_REL}/src/spitfire_control/commands.py",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def assignment(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            if node.value is None:
                break
            return node.value
    raise ValueError(f"Missing source assignment: {name}")


def command_artifacts() -> tuple[bytes, bytes]:
    source_bytes = {label: (REPO / path).read_bytes() for label, path in SOURCE_PATHS.items()}
    if sha256(source_bytes["baseline"]) != BASELINE_PROTOCOL_SHA256:
        raise ValueError(f"Baseline protocol differs from comparison commit {BASELINE_COMMIT}")
    baseline = ast.parse(source_bytes["baseline"])
    variant = ast.parse(source_bytes["variant"])
    base_queries = ast.literal_eval(assignment(baseline, "QUERIES"))
    base_writes = ast.literal_eval(assignment(baseline, "COMMANDS"))
    variant_queries = ast.literal_eval(assignment(variant, "_QUERIES"))
    writes_node = assignment(variant, "_WRITES")
    if not isinstance(writes_node, ast.Dict):
        raise ValueError("Variant _WRITES is no longer a dictionary literal")
    variant_writes = {}
    for key, value in zip(writes_node.keys, writes_node.values):
        if key is None or not isinstance(value, ast.Tuple) or not value.elts:
            raise ValueError("Unexpected variant command entry")
        variant_writes[ast.literal_eval(key)] = ast.literal_eval(value.elts[0])
    base_all = {**base_queries, **base_writes}
    variant_all = {**variant_queries, **variant_writes}
    rows = []
    for command_id in sorted(base_all.keys() | variant_all.keys()):
        base_text = base_all.get(command_id)
        variant_text = variant_all.get(command_id)
        if command_id not in base_all:
            status = "variant_only"
        elif command_id not in variant_all:
            status = "baseline_only"
        else:
            status = "identical" if base_text == variant_text else "changed"
        rows.append({
            "id": command_id,
            "direction": "query" if command_id < 2000 else "write",
            "baseline_text": base_text,
            "variant_text": variant_text,
            "status": status,
        })
    summary = {
        "scope": "Literal command IDs and names only; runtime, profile policy, formatting and GUI behavior are not compared here.",
        "baseline_commit": BASELINE_COMMIT,
        "sources": {
            label: {"path": SOURCE_PATHS[label], "sha256": sha256(data)}
            for label, data in source_bytes.items()
        },
        "counts": {
            "baseline_queries": len(base_queries),
            "baseline_writes": len(base_writes),
            "variant_queries": len(variant_queries),
            "variant_writes": len(variant_writes),
            "identical": sum(row["status"] == "identical" for row in rows),
            "changed": sum(row["status"] == "changed" for row in rows),
            "baseline_only": sum(row["status"] == "baseline_only" for row in rows),
            "variant_only": sum(row["status"] == "variant_only" for row in rows),
        },
    }
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["id", "direction", "baseline_text", "variant_text", "status"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8"), json_bytes(summary)


def archive_manifest(archive: Path) -> dict:
    archive_data = archive.read_bytes()
    actual_sha = sha256(archive_data)
    if actual_sha != ARCHIVE_SHA256:
        raise ValueError(f"Unexpected archive SHA-256: {actual_sha}")
    files = []
    seen = set()
    with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != ARCHIVE_ROOT:
                raise ValueError(f"Unexpected archive path: {info.filename}")
            rel = path.relative_to(ARCHIVE_ROOT).as_posix()
            if rel in seen:
                raise ValueError(f"Duplicate archive member: {rel}")
            seen.add(rel)
            data = zf.read(info)
            files.append({"path": rel, "size_bytes": len(data), "sha256": sha256(data)})
    files.sort(key=lambda item: item["path"])
    return {
        "schema_version": 1,
        "baseline_commit": BASELINE_COMMIT,
        "archive": {"filename": ARCHIVE_NAME, "sha256": actual_sha, "size_bytes": len(archive_data), "root": ARCHIVE_ROOT},
        "destination": VARIANT_REL,
        "file_count": len(files),
        "total_uncompressed_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
    }


def verify_files(manifest: dict) -> list[str]:
    destination = REPO / VARIANT_REL
    errors = []
    expected = set()
    for entry in manifest["files"]:
        rel = PurePosixPath(entry["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Unsafe manifest path: {rel}")
        expected.add(rel.as_posix())
        path = destination / rel
        if path.is_symlink() or not path.is_file():
            errors.append(f"Missing/non-regular file: {rel}")
            continue
        data = path.read_bytes()
        if len(data) != entry["size_bytes"] or sha256(data) != entry["sha256"]:
            errors.append(f"Changed file: {rel}")
    actual = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file() or path.is_symlink()}
    errors.extend(f"Unexpected file: {path}" for path in sorted(actual - expected))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, help="Optionally verify against the original uploaded ZIP")
    parser.add_argument("--generate", action="store_true", help="Rebuild manifest and command data; requires --archive")
    args = parser.parse_args()
    if args.generate and args.archive is None:
        parser.error("--generate requires --archive")
    try:
        manifest_path = HERE / "snapshot_manifest.json"
        if args.generate:
            manifest = archive_manifest(args.archive)
            errors = verify_files(manifest)
            if errors:
                raise ValueError("\n".join(errors))
            manifest_path.write_bytes(json_bytes(manifest))
        else:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if args.archive is not None and archive_manifest(args.archive) != manifest:
            raise ValueError("Manifest does not match the original archive")
        errors = verify_files(manifest)
        csv_data, summary_data = command_artifacts()
        for name, data in [("command_comparison.csv", csv_data), ("command_summary.json", summary_data)]:
            path = HERE / name
            if args.generate:
                path.write_bytes(data)
            elif not path.is_file() or path.read_bytes() != data:
                errors.append(f"Comparison artifact is missing or stale: {name}")
        if errors:
            raise ValueError("\n".join(errors))
        counts = json.loads(summary_data)["counts"]
        print(f"PASS: {manifest['file_count']} imported files match the snapshot manifest ({manifest['total_uncompressed_bytes']} bytes).")
        print(f"PASS: {counts['identical']} command entries identical; {counts['changed']} changed, {counts['baseline_only']} baseline-only, {counts['variant_only']} variant-only.")
        if args.archive is not None:
            print(f"PASS: original archive SHA-256 {ARCHIVE_SHA256} and every member match.")
        return 0
    except (OSError, ValueError, KeyError, SyntaxError, zipfile.BadZipFile) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

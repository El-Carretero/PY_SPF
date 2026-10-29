"""Version declarations and *static* inspection of client source artifacts.

Profiles describe an adapter, not a certificate of hardware compatibility.
Inspection never imports the selected package. ZIPs are validated before any
bytes are extracted, and only the selected Python package is ever extracted.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from .catalog import COMMANDS

MAX_ENTRIES = 20000
MAX_TOTAL_BYTES = 200 * 1024 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_TOTAL = 20 * 1024 * 1024
PACKAGE = "spitfire_control"


class InspectionError(ValueError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def catalog_digest(entries: dict[int, str]) -> str:
    return _digest(json.dumps(sorted(entries.items()), ensure_ascii=True,
                              separators=(",", ":")).encode("ascii"))


CATALOG_SHA256 = catalog_digest({cid: spec.text for cid, spec in COMMANDS.items()})
_PROFILES = [
    {"id": "xp_gui_1.6.0", "label": "XP Original 1.6.0", "family": "xp_gui", "version": "1.6.0",
     "adapter": "external_udp_capture", "evidence_status": "STATIC_RECOVERY_ONLY",
     "capabilities": ["eclipse_udp", "external_capture"],
     "limitations": ["Actual XP execution must be observed separately; no automatic XP claim."]},
    {"id": "python_1.1.3", "label": "Python 1.1.3", "family": "python", "version": "1.1.3",
     "adapter": "spitfire_control_udp_v1", "evidence_status": "DECLARED_NOT_RUN",
     "capabilities": ["eclipse_udp", "transport_state_matrix"],
     "limitations": ["No external-pump policy support is assumed.", "GUI and hardware require separate evidence."]},
    {"id": "python_1.3.0", "label": "Python 1.3.0", "family": "python", "version": "1.3.0",
     "adapter": "spitfire_control_udp_v1", "evidence_status": "DECLARED_NOT_RUN",
     "capabilities": ["eclipse_udp", "transport_state_matrix", "external_pump_policy_declared"],
     "limitations": ["Declared external-pump support is not a physical timing validation.",
                     "GUI and hardware require separate evidence."]},
]


def list_profiles() -> list[dict]:
    """Return declarations; a matrix run supplies separate per-artifact evidence."""
    return copy.deepcopy(_PROFILES)


def get_profile(profile_id: str) -> dict:
    for profile in _PROFILES:
        if profile["id"] == profile_id:
            return copy.deepcopy(profile)
    raise ValueError(f"Unknown client profile: {profile_id}")


def _safe_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise InspectionError("ZIP has too many entries")
    total = 0
    names = set()
    for item in entries:
        name = item.filename
        parts = PurePosixPath(name).parts
        if (not parts or name.startswith(("/", "\\")) or "\\" in name or
                any(p in {".", ".."} or ":" in p for p in parts) or "\x00" in name):
            raise InspectionError(f"Unsafe ZIP member path: {name!r}")
        reserved = {"CON", "PRN", "AUX", "NUL", *("COM" + str(i) for i in range(1, 10)),
                    *("LPT" + str(i) for i in range(1, 10))}
        if any(p.endswith((" ", ".")) or p.split(".")[0].upper() in reserved for p in parts):
            raise InspectionError(f"Windows-unsafe ZIP member path: {name!r}")
        normalized = "/".join(parts).casefold()
        if normalized in names:
            raise InspectionError(f"Duplicate/case-colliding ZIP member: {name!r}")
        names.add(normalized)
        mode = (item.external_attr >> 16) & 0xffff
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
            raise InspectionError("ZIP contains a symlink or special file")
        if item.flag_bits & 1:
            raise InspectionError("Encrypted ZIPs are not supported")
        total += item.file_size
        if total > MAX_TOTAL_BYTES or item.file_size > MAX_TOTAL_BYTES:
            raise InspectionError("ZIP uncompressed size exceeds 200 MiB limit")
        if item.file_size > 1024 * 1024 and item.file_size > max(1, item.compress_size) * 1000:
            raise InspectionError("ZIP compression ratio exceeds inspection limit")
    return entries


def _sources(path: Path) -> tuple[dict[str, bytes], str, str]:
    """Read only source-package bytes, with resource bounds; no code execution."""
    if path.is_symlink():
        raise InspectionError("Select a real directory or ZIP, not a symlink")
    source: dict[str, bytes] = {}
    source_bytes = 0
    if path.is_file():
        if not zipfile.is_zipfile(path):
            raise InspectionError("Select a Python source folder or ZIP (EXE inspection is not supported)")
        with zipfile.ZipFile(path) as archive:
            entries = _safe_zip_members(archive)
            candidates = [item for item in entries if item.filename.endswith(PACKAGE + "/__init__.py")]
            # Source releases may also contain packaging copies: ambiguity is explicit.
            if len(candidates) != 1:
                raise InspectionError("ZIP must contain exactly one spitfire_control source package")
            prefix = candidates[0].filename[:-len("__init__.py")]
            for item in entries:
                if item.filename.startswith(prefix) and item.filename.endswith(".py"):
                    if item.file_size > MAX_SOURCE_BYTES:
                        raise InspectionError("Individual source exceeds 2 MiB limit")
                    source_bytes += item.file_size
                    if source_bytes > MAX_SOURCE_TOTAL:
                        raise InspectionError("Python source exceeds 20 MiB limit")
                    source[item.filename[len(prefix):]] = archive.read(item)
        artifact_digest, kind = _file_digest(path), "zip"
    elif path.is_dir():
        candidates = [path / "src" / PACKAGE, path / PACKAGE]
        if path.name == PACKAGE:
            candidates.insert(0, path)
        packages = [p for p in candidates if (p / "__init__.py").is_file()]
        if len(packages) != 1:
            # A single wrapper directory from an extracted release is allowed.
            children = list(path.iterdir())
            if len(children) > MAX_ENTRIES:
                raise InspectionError("Directory has too many entries")
            packages = [p / "src" / PACKAGE for p in children if p.is_dir()
                        and not p.is_symlink() and (p / "src" / PACKAGE / "__init__.py").is_file()]
        if len(packages) != 1:
            raise InspectionError("Folder must identify exactly one spitfire_control source package")
        package = packages[0]
        for parent in [package, *package.parents]:
            if parent.is_symlink():
                raise InspectionError("Source path contains a symlink")
            if parent == path:
                break
        for index, item in enumerate(package.rglob("*")):
            if index >= MAX_ENTRIES:
                raise InspectionError("Source tree has too many entries")
            if item.is_symlink():
                raise InspectionError("Source tree contains a symlink")
            if item.is_file() and item.suffix == ".py":
                if item.stat().st_size > MAX_SOURCE_BYTES:
                    raise InspectionError("Individual source exceeds 2 MiB limit")
                source_bytes += item.stat().st_size
                if source_bytes > MAX_SOURCE_TOTAL:
                    raise InspectionError("Python source exceeds 20 MiB limit")
                source[item.relative_to(package).as_posix()] = item.read_bytes()
        artifact_digest, kind = "", "directory"
    else:
        raise InspectionError(f"Client path does not exist: {path}")
    if sum(map(len, source.values())) > MAX_SOURCE_TOTAL:
        raise InspectionError("Python source exceeds 20 MiB limit")
    canonical = b"".join(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest()
                         for name, data in sorted(source.items()))
    source_digest = _digest(canonical)
    return source, artifact_digest or source_digest, kind


def _tree(source: dict[str, bytes], name: str) -> ast.Module:
    try:
        return ast.parse(source[name].decode("utf-8-sig"), filename=name)
    except (KeyError, UnicodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise InspectionError(f"Cannot statically parse {name}: {exc}") from exc


def _catalog(tree: ast.Module) -> dict[int, str]:
    entries = {}
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None)
        if not isinstance(target, ast.Name) or target.id not in {"_QUERIES", "_WRITES", "QUERIES", "WRITES"}:
            continue
        if not isinstance(node.value, ast.Dict):
            raise InspectionError("Command catalogue is dynamic; static adapter inspection cannot prove it")
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(value, ast.Tuple) and value.elts:
                value = value.elts[0]
            if not (isinstance(key, ast.Constant) and type(key.value) is int and
                    isinstance(value, ast.Constant) and isinstance(value.value, str)):
                raise InspectionError("Command catalogue contains a nonliteral command")
            if key.value in entries:
                raise InspectionError("Duplicate command ID in source catalogue")
            entries[key.value] = value.value
    return entries


def inspect_client(path: str | Path) -> dict:
    """Inspect source without running it. Version strings alone never prove identity."""
    path = Path(path).expanduser().absolute()
    source, artifact_sha, kind = _sources(path)
    version = None
    for node in _tree(source, "__init__.py").body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                version = node.value.value
    if not version or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,80}", version):
        raise InspectionError("No safe literal __version__ was found")
    entries = _catalog(_tree(source, "commands.py"))
    classes = {n.name for n in _tree(source, "transport.py").body if isinstance(n, ast.ClassDef)}
    state_tree = _tree(source, "state.py")
    state_classes = {n.name for n in state_tree.body if isinstance(n, ast.ClassDef)}
    state_methods = {n.name for cls in state_tree.body if isinstance(cls, ast.ClassDef) and cls.name == "DeviceState"
                     for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    features = []
    if {"external_enable_reason", "external_timing_reason"}.issubset(state_methods) and "timing.py" in source:
        functions = {n.name for n in _tree(source, "timing.py").body if isinstance(n, ast.FunctionDef)}
        if "validate_timing_expectations" in functions:
            features.append("external_state_policy")
    compatible = {"UdpTransport", "UdpSettings"}.issubset(classes) and "DeviceState" in state_classes
    known = next((p for p in _PROFILES if p["family"] == "python" and p["version"] == version), None)
    digest = catalog_digest(entries)
    source_digest = _digest(b"".join(name.encode("utf-8") + b"\0" + hashlib.sha256(data).digest()
                                    for name, data in sorted(source.items())))
    warnings = ["Static inspection does not execute code or establish trust. Matrix execution runs selected source.",
                "A subprocess and loopback audit guard are not a security sandbox."]
    if digest != CATALOG_SHA256:
        warnings.append("Catalogue differs from recovered GUI 1.6.0. Only shared command IDs/texts can be tested.")
    if not known:
        warnings.append("Unknown version: capabilities are not inferred from the version string.")
    return {"path": str(path), "kind": kind, "artifact_sha256": artifact_sha,
            "artifact_hash_scope": "whole_zip" if kind == "zip" else "python_source_tree",
            "source_sha256": source_digest, "version": version,
            "profile_id": known["id"] if known else None,
            "catalog_sha256": digest, "catalog_entries": len(entries),
            "unique_commands": len(set(entries.values())),
            "nonempty_slots": sum(bool(v) for v in entries.values()),
            "unique_nonempty_commands": len({v for v in entries.values() if v}),
            "casefolded_unique_commands": len({v.upper() for v in entries.values()}),
            "catalog_matches_recovered": digest == CATALOG_SHA256,
            "adapter_compatible": compatible, "inspection_status": "STATIC_ONLY",
            "adapter_features": features,
            "evidence_status": "NOT_EXECUTED", "warnings": warnings,
            "commands": {str(cid): text for cid, text in sorted(entries.items())}}


@contextmanager
def materialized_client(path: str | Path):
    """Copy only validated source into an isolated temporary tree for explicit runs."""
    source, _, _ = _sources(Path(path).expanduser().absolute())
    with tempfile.TemporaryDirectory(prefix="spitfire-client-") as temporary:
        root = Path(temporary)
        for name, data in source.items():
            target = root / PACKAGE / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        yield root

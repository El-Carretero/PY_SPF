"""Small JSON configuration with conservative network defaults."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from .network import validate_ipv4


MAX_CONFIG_BYTES = 64 * 1024
# Windows can reject replacement of a destination while another thread has
# that file open, including one of our own readers. Atomic replacement protects
# file contents, but is not itself synchronization. All config I/O in this
# process shares this lock; it does not coordinate independent processes or
# override filesystem permissions. Genuine I/O failures retain their behavior.
_CONFIG_IO_LOCK = RLock()


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate configuration key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite configuration value: {value}")


def _field_value(name, value):
    if name in {"bind_ip", "original_ip", "python_ip"}:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be an IPv4 string")
        # Match the GUI's existing unicast policy. Loading settings never opens
        # a socket, and a corrupt value cannot broaden the bind to a wildcard.
        return validate_ipv4(value, field=name)
    if name == "bind_port":
        if type(value) is not int or not 1 <= value <= 65535:
            raise ValueError("bind_port must be an integer in 1..65535")
        return value
    if name == "isolated_clients":
        if type(value) is not bool:
            raise ValueError("isolated_clients must be a boolean")
        return value
    limit = 4096 if name == "output_directory" else 128
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError(f"{name} must be nonempty printable text <= {limit} characters")
    # JSON escapes can represent lone surrogates that Tk and UTF-8 cannot use.
    value.encode("utf-8", "strict")
    return value.strip()


@dataclass(slots=True)
class AppConfig:
    bind_ip: str = "127.0.0.1"
    bind_port: int = 1024
    original_ip: str = "10.19.70.2"
    python_ip: str = "10.19.70.1"
    original_label: str = "XP Original 1.6.0"
    python_label: str = "Python 1.3.0"
    isolated_clients: bool = True
    output_directory: str = "verification_reports"

    @classmethod
    def path(cls) -> Path:
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        else:
            root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return root / "SpitfireTwinVerifier" / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        path = cls.path()
        try:
            with _CONFIG_IO_LOCK:
                with path.open("rb") as stream:
                    raw = stream.read(MAX_CONFIG_BYTES + 1)
            if len(raw) > MAX_CONFIG_BYTES:
                raise ValueError("configuration exceeds 64 KiB")
            data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_json,
                              parse_constant=_reject_constant)
            if not isinstance(data, dict):
                raise ValueError("configuration must be a JSON object")
            return cls(**cls._validated(data, strict=False))
        except (OSError, ValueError, TypeError, RecursionError):
            return cls()

    @classmethod
    def _validated(cls, supplied, *, strict):
        """Keep valid user fields; malformed saved fields fall back individually.

        Related fields that would collide are reset as a group. Unknown keys
        are ignored for forward compatibility, not passed to the constructor.
        Explicit save errors raise before any existing file is replaced.
        """
        defaults = asdict(cls())
        result = dict(defaults)
        for name in defaults:
            if name not in supplied:
                continue
            try:
                result[name] = _field_value(name, supplied[name])
            except ValueError:
                if strict:
                    raise
        for names in (("bind_ip", "original_ip", "python_ip"),
                      ("original_label", "python_label")):
            if len({result[name] for name in names}) != len(names):
                if strict:
                    raise ValueError(f"Configuration fields must be distinct: {', '.join(names)}")
                for name in names:
                    result[name] = defaults[name]
        return result

    def save(self) -> None:
        data = self._validated(asdict(self), strict=True)
        path = self.path()
        with _CONFIG_IO_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=path.parent)
            temporary = Path(name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

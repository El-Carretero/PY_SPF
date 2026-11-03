"""Persistent user settings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
import tempfile
from pathlib import Path

from .timing import validate_timing_expectations


@dataclass(slots=True)
class AppConfig:
    mode: str = "simulator"
    pump_mode: str = "empower"
    external_seed_mhz: float = 80.0
    external_seed_tolerance_mhz: float = 1.0
    external_pump_hz: float = 10.0
    remote_host: str = "10.19.70.13"
    remote_port: int = 1024
    local_host: str = "0.0.0.0"
    local_port: int = 1024
    timeout_seconds: float = 2.0
    poll_interval_seconds: float = 1.0
    auto_poll: bool = True
    monitor_hv: bool = False
    log_directory: str = ""

    def __post_init__(self) -> None:
        validate_timing_expectations(self.external_seed_mhz, self.external_seed_tolerance_mhz, self.external_pump_hz)
        if not isinstance(self.mode, str) or self.mode not in {"simulator", "udp"}:
            raise ValueError("Transport mode must be simulator or udp")
        if not isinstance(self.pump_mode, str) or self.pump_mode not in {"empower", "external"}:
            raise ValueError("Pump mode must be empower or external")
        for name in ("remote_host", "local_host"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                raise ValueError(f"{name} must be a nonempty host name or address")
        for name, minimum in (("remote_port", 1), ("local_port", 0)):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= 65535:
                raise ValueError(f"{name} must be an integer from {minimum} to 65535")
        for name, minimum in (("timeout_seconds", 0.0), ("poll_interval_seconds", 0.2)):
            value = getattr(self, name)
            try:
                finite = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError(f"{name} must be a finite number")
            if value <= 0 or value < minimum:
                raise ValueError(f"{name} is below the supported minimum")
        for name in ("auto_poll", "monitor_hv"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be true or false")
        if not isinstance(self.log_directory, str) or "\x00" in self.log_directory:
            raise ValueError("Log directory must be a path string")

    @staticmethod
    def config_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home()))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "spitfire-control" / "config.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        path = path or cls.config_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return cls()
        known = {name for name in cls.__dataclass_fields__}
        if not isinstance(raw, dict):
            return cls()
        try:
            return cls(**{key: value for key, value in raw.items() if key in known})
        except (TypeError, ValueError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        # Fields can also be edited by CLI/UI callers after construction.
        self.__post_init__()
        path = path or self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            # A unique file prevents concurrent app instances sharing .tmp.
            # Keep it beside the destination so replacement remains atomic.
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                             dir=path.parent, prefix=path.name + ".",
                                             suffix=".tmp", delete=False) as stream:
                temp = Path(stream.name)
                json.dump(asdict(self), stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(path)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)


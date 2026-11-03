"""Controller state model and conservative reply decoding."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import re
import math
from typing import Any

from .protocol import Reply


NUMERIC_IDS = {
    1007, 1008, 1009, 1010, 1011, 1012, 1013, 1015, 1018, 1019,
    1021, 1023, 1024, 1025, 1028, 1029, 1030, 1031, 1032, 1033, 1039,
    1040, 1041, 1042, 1043, 1044, 1045, 1046, 1047, 1048, 1049,
    1050, 1051, 1052, 1053, 1054, 1055, 1056, 1057, 1060, 1061,
    1065, 1066, 1067, 1068, 1069, 1077, 1078, 1080, 1084, 1085,
    1086, 1087, 1088, 1089,
}

FIELD_IDS = {
    "diode_current_measured": 1007,
    "output_power": 1008,
    "diode_current_set": 1009,
    "qsw_frequency": 1010,
    "qsw_pulse_width": 1011,
    "qsw_source": 1012,
    "empower_status": 1013,
    "head_status": 1015,
    "tdg_status": 1019,
    "high_voltage_on": 1021,
    "oscillator_frequency": 1024,
    "divisor": 1025,
    "ecu_status": 1028,
    "ecu_health": 1029,
    "crystal_temperature": 1030,
    "humidity": 1031,
    "temperature_set": 1032,
    "ecu_opt_out": 1033,
    "hv1_set": 1040,
    "hv2_set": 1041,
    "hv1_measured": 1042,
    "hv2_measured": 1043,
    "humidity_override": 1044,
    "oscillator_mode": 1050,
    "trigger_mode": 1051,
    "trigger_frequency": 1053,
    "hv1_current": 1055,
    "hv2_current": 1056,
    "motor_speed": 1060,
    "measured_oscillator_frequency": 1065,
    "empower_opt_out": 1068,
    "compressor_opt_out": 1069,
    "lbo_temperature": 1077,
    "tec_temperature": 1084,
    "system_status": 1085,
    "communication_status": 1089,
}


def _number(value: str) -> int | float | str:
    stripped = value.strip()
    try:
        if re.fullmatch(r"[-+]?\d+", stripped):
            return int(stripped)
        if re.fullmatch(r"[-+]?0[xX][0-9a-fA-F]+", stripped):
            sign = -1 if stripped.startswith("-") else 1
            unsigned = stripped.lstrip("+-")
            return sign * int(unsigned, 16)
        number = float(stripped)
        return number if math.isfinite(number) else value
    except ValueError:
        return value


def is_error_reply(value: str) -> bool:
    return bool(re.match(r"^(?:ERR(?:OR)?|NACK|FAIL(?:ED)?)(?:\b|[:;,])", value.strip(), re.I))


@dataclass(frozen=True, slots=True)
class DelayState:
    value: float | None = None
    switch: str | None = None
    bwd: str | None = None
    enable: str | None = None


def decode_delay(value: str) -> DelayState:
    """Keep mode flags and the legacy six-prefix-field numeric value separate.

    _gextHandleReceivedMsg (1045..1049) searches OFF/NBWD/NENA;
    _decodenum at 0x40FE1E extracts the number after six spaces.
    A bare number is also accepted, without inventing mode flags.
    """
    tokens = value.upper().split()
    def flag(choices):
        found = [t for t in tokens if t in choices]
        return found[0] if len(found) == 1 else None
    number = None
    candidate = value.strip() if len(tokens) == 1 else " ".join(tokens[6:])
    if candidate:
        try:
            number = float(candidate.split()[0])
            if not math.isfinite(number):
                number = None
        except ValueError:
            pass
    return DelayState(number, flag({"ON", "OFF"}), flag({"BWD", "NBWD"}), flag({"ENA", "NENA"}))


# The original module decoders use MSB(status) & 8 as communication error.
MODULE_QUERY_IDS = {"EMPOWER": 1013, "TDG": 1019, "TCU": 1028, "COMPRESSOR": 1015}
MODULE_OPTOUT_IDS = {"EMPOWER": 1068, "TCU": 1033, "COMPRESSOR": 1069}
READBACK_ALIASES = {1023: 1039, 1029: 1088, 1057: 1088, 1061: 1021, 1067: 1050, 1058: 1045, 1059: 1046, 1063: 1045, 1064: 1046}


def readback_family(command_id: int) -> set[int]:
    canonical = READBACK_ALIASES.get(command_id, command_id)
    return {canonical} | {alias for alias, target in READBACK_ALIASES.items() if target == canonical}


@dataclass(slots=True)
class DeviceState:
    values: dict[int, Any] = field(default_factory=dict)
    raw_values: dict[int, str] = field(default_factory=dict)
    updated_at: dict[int, datetime] = field(default_factory=dict)
    delays: dict[int, DelayState] = field(default_factory=dict)
    invalid_ids: set[int] = field(default_factory=set)
    pending_readbacks: set[int] = field(default_factory=set)
    fault_words: tuple[int, ...] = ()
    last_reply_at: datetime | None = None
    last_error: str = ""
    connected: bool = False
    transport_open: bool = False
    transport_name: str = "Disconnected"
    armed: bool = False
    stale_after_seconds: float = 5.0
    pump_mode: str = "empower"
    external_seed_mhz: float = 80.0
    external_seed_tolerance_mhz: float = 1.0
    external_pump_hz: float = 10.0

    def copy(self) -> "DeviceState":
        return replace(self, values=dict(self.values), raw_values=dict(self.raw_values),
                       updated_at=dict(self.updated_at), delays=dict(self.delays),
                       invalid_ids=set(self.invalid_ids), pending_readbacks=set(self.pending_readbacks))

    def invalidate(self, command_id: int) -> None:
        """An invalid alias must not leave a cached canonical fact usable."""
        self.invalid_ids.update(readback_family(command_id))

    def apply(self, reply: Reply) -> bool:
        now = datetime.now(timezone.utc)
        cid = reply.command_id
        self.raw_values[cid] = reply.value
        # ACK text is diagnostic data, never a substitute for a query readback.
        if cid >= 2000:
            self.values[cid] = reply.value
            return reply.value.strip().upper() in {"OK", "ACK"}
        if is_error_reply(reply.value) or not reply.value.strip():
            self.invalidate(cid)
            return False
        valid = True
        if cid == 1014:
            tokens = reply.value.split()
            valid = len(tokens) == 4 and all(re.fullmatch(r"\d{1,10}", t) and int(t) <= 0xffffffff for t in tokens)
            if valid:
                self.fault_words = tuple(int(t) for t in tokens)
                self.values[cid] = self.fault_words
        elif 1045 <= cid <= 1049 or cid in {1058, 1059, 1063, 1064}:
            channel = {1058: 1, 1059: 2, 1063: 1, 1064: 2}.get(cid, cid - 1044)
            delay = decode_delay(reply.value)
            self.delays[channel] = delay
            self.values[cid] = delay.value
            valid = delay.value is not None
        elif cid in {1023, 1039, 1066}:
            # XP 1.6.0 uses sscanf("%x") for TDG STBH / STBHFLT.
            raw = reply.value.strip()
            valid = bool(re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]{1,8}", raw))
            if valid:
                self.values[cid] = int(raw, 16)
        elif cid in NUMERIC_IDS:
            number = _number(reply.value)
            if isinstance(number, (float, int)):
                try:
                    valid = math.isfinite(number)
                except (OverflowError, TypeError):
                    valid = False
                if valid and cid in {1013, 1015, 1019, 1028, 1029, 1057, 1088, 1089}:
                    valid = 0 <= number <= 0xffffffff and number == int(number)
                # Legacy readback: nonnegative EMP:QSW:PRF? units are 10 Hz.
                self.values[cid] = number * 10 if cid == 1010 and number >= 0 else number
            elif cid in {1050, 1051, 1067, 1080}:
                modes = {"INT": 0, "EXT": 1} if cid != 1080 else {"CONT": 0, "COUNT": 1, "COUNT 1": 2}
                valid = reply.value.strip().upper() in modes
                self.values[cid] = modes.get(reply.value.strip().upper())
            else:
                valid = False
        else:
            self.values[cid] = reply.value
        if not valid:
            self.invalidate(cid)
            return False
        self.invalid_ids.discard(cid)
        self.pending_readbacks.discard(cid)
        self.updated_at[cid] = now
        self.last_reply_at = now
        if cid in READBACK_ALIASES:
            target = READBACK_ALIASES[cid]
            self.values[target] = self.values[cid]
            self.updated_at[target] = now
            self.invalid_ids.discard(target)
            self.pending_readbacks.discard(target)
        return True

    def value(self, command_id: int, default: Any = None) -> Any:
        if command_id in self.invalid_ids or command_id in self.pending_readbacks:
            return default
        return self.values.get(command_id, default)

    def field(self, name: str, default: Any = None) -> Any:
        return self.value(FIELD_IDS[name], default)

    def link_fresh(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return bool(self.connected and self.last_reply_at is not None and
                    0 <= (now - self.last_reply_at).total_seconds() <= self.stale_after_seconds)

    def is_fresh(self, command_id: int, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        stamp = self.updated_at.get(command_id)
        return bool(self.link_fresh(now) and stamp is not None and
                    command_id not in self.invalid_ids and command_id not in self.pending_readbacks and
                    0 <= (now - stamp).total_seconds() <= self.stale_after_seconds)

    def communication_state(self, name: str) -> str:
        if name == "EMPOWER" and self.pump_mode == "external":
            return "off"
        if not self.transport_open:
            return "off"
        if not self.link_fresh():
            return "fault" if self.last_reply_at is not None else "unknown"
        if name == "MAIN":
            return "ok"
        opt = MODULE_OPTOUT_IDS.get(name)
        if opt is not None and self.value(opt) == 1:
            return "off"
        cid = MODULE_QUERY_IDS[name]
        if not self.is_fresh(cid):
            return "unknown"
        status = self.value(cid)
        if not isinstance(status, (int, float)) or status < 0 or int(status) != status:
            return "unknown"
        return "fault" if int(status) & 0x800 else "ok"

    @property
    def external_opt_out_confirmed(self) -> bool:
        return self.is_fresh(1068) and self.value(1068) == 1

    @property
    def effective_fault_words(self) -> tuple[int, ...]:
        """Empower-only words, excluded from an external-pump configuration.

        Raw replies are retained. XP UIR IDs are zero-based; runtime controls
        are one-based. TDG/TCU/COM faults originate in separate reply handlers.
        """
        if self.pump_mode == "external" or not self.is_fresh(1014):
            return ()
        return self.fault_words

    def fault_state(self, index: int) -> bool | None:
        if index in FAULT_WORD_BITS:
            if self.pump_mode == "external":
                return None
            empower = None
            if self.is_fresh(1014) and len(self.fault_words) == 4:
                word, mask = FAULT_WORD_BITS[index]
                empower = bool(self.fault_words[word] & mask)
            if index == 15:
                comm = bool(int(self.value(1089)) & 4) if self.is_fresh(1089) else None
                return True if empower or comm else (False if empower is False and comm is False else None)
            return empower
        source = MODULE_FAULT_BITS.get(index)
        if source is None or not self.is_fresh(source[0]):
            return None
        return bool(int(self.value(source[0])) & source[1])

    @property
    def faults_known(self) -> bool:
        ids = (1039, 1066, 1088, 1089)
        if self.pump_mode != "external":
            ids += (1014,)
        return all(self.is_fresh(cid) for cid in ids)

    def external_timing_reason(self) -> str:
        """Checks electronic readbacks only, never pump optical timing or phase lock."""
        if self.pump_mode != "external":
            return ""
        for cid, label in ((1050, "Oscillator sync"), (1051, "Amplifier trigger"), (1065, "Measured seed frequency")):
            if not self.is_fresh(cid):
                return f"{label} unavailable or stale."
        if self.value(1050) != 1:
            return "Oscillator sync must be confirmed EXT."
        if self.value(1051) != 1:
            return "Amplifier trigger must be confirmed EXT."
        from .timing import validate_timing_expectations
        try:
            validate_timing_expectations(self.external_seed_mhz, self.external_seed_tolerance_mhz, self.external_pump_hz)
        except ValueError as exc:
            return str(exc)
        measured = self.value(1065)
        if not isinstance(measured, (int, float)) or not math.isfinite(measured) or measured <= 0:
            return "Measured seed frequency must be positive and finite."
        if abs(measured - self.external_seed_mhz) > self.external_seed_tolerance_mhz:
            return f"Measured seed {measured:g} MHz is outside {self.external_seed_mhz:g} +/- {self.external_seed_tolerance_mhz:g} MHz."
        return ""

    def external_enable_reason(self) -> str:
        """Software eligibility only; never a claim of optical synchronization."""
        if self.pump_mode != "external":
            return ""
        if not self.link_fresh():
            return "No recent controller connection."
        if not self.external_opt_out_confirmed:
            return "Empower opt-out is not confirmed by a recent controller readback."
        for cid, label in ((1019, "TDG status"),
                           (1066, "TDG fault status"), (1021, "HV state"),
                           (1087, "TDG fault override"), (1045, "PC1 modes"), (1046, "PC2 modes"),
                           (1039, "TDG BWD status"), (1088, "TCU fault status"), (1089, "Communication status"),
                           (1033, "TCU opt-out"), (1044, "Humidity override"), (1028, "TCU status"),
                           (1015, "Head status"), (1069, "Head opt-out")):
            if not self.is_fresh(cid):
                return f"{label} unavailable or stale."
        timing_reason = self.external_timing_reason()
        if timing_reason:
            return timing_reason
        if int(self.value(1039)) & 0x00330000:
            return "TDG BWD detector or latch reports a fault."
        if self.value(1087) != 0:
            return "TDG fault override must be confirmed OFF."
        if self.value(1033) != 0:
            return "TCU opt-out must be confirmed OFF."
        if self.value(1044) != 0:
            return "Humidity override must be confirmed OFF."
        if self.value(1069) != 0:
            return "Head/compressor opt-out must be confirmed OFF."
        for channel in (1, 2):
            delay = self.delays.get(channel)
            if delay is None or delay.bwd != "BWD" or delay.enable != "ENA":
                return f"PC{channel} BWD and enable gating are not confirmed active."
        for module in ("TDG", "TCU", "COMPRESSOR"):
            if self.communication_state(module) != "ok":
                return f"{module} communication status is not healthy."
        if self.value(1066) != 0:
            return "TDG reports a fault or an unrecognized fault status."
        if int(self.value(1088)) & 0x14:
            return "TCU reports a humidity or TEC overtemperature fault."
        if int(self.value(1089)) & ~0x04:
            return "Main/TDG/TCU communication or an unknown communication bit reports a fault."
        if self.high_voltage is None:
            return "HV state is not recognized."
        return ""

    @property
    def fault_active(self) -> bool:
        if any(self.effective_fault_words):
            return True
        if self.is_fresh(1066) and self.value(1066) != 0:
            return True  # Keep unknown bits in the dedicated fault register.
        if self.is_fresh(1039) and int(self.value(1039)) & 0x00330000:
            return True
        if self.is_fresh(1088) and int(self.value(1088)) & 0x14:
            return True
        if self.is_fresh(1089):
            mask = ~0x04 if self.pump_mode == "external" and self.external_opt_out_confirmed else 0xffffffff
            if int(self.value(1089)) & mask:
                return True
        return False

    @property
    def laser_on(self) -> bool | None:
        if self.pump_mode == "external":
            return None  # External pump emission is not observed by this application.
        value = self.value(1013)
        if self.is_fresh(1013) and isinstance(value, (int, float)) and value >= 0:
            return bool(int(value) & 1)
        return None

    @property
    def high_voltage(self) -> bool | None:
        value = self.value(1021)
        if self.is_fresh(1021) and value in (0, 1):
            return bool(value)
        return None


FAULT_LABELS = (
    "Empower: array open", "Empower: kill switch", "Empower: array overtemperature",
    "Empower: checksum", "Empower: overvoltage", "Empower: driver overtemperature",
    "Empower: overpower", "TDG: key interlock", "TDG: relay", "TDG: system",
    "Main communication", "TDG: user interlock", "Empower: VSWR",
    "Empower: underfrequency", "Empower: protection", "Empower communication",
    "TDG: head interlock", "Empower: keyswitch", "Empower: overcurrent",
    "Empower: Q-switch under-temperature", "TCU: humidity latch",
    "TCU: TEC overtemperature", "Empower: cover", "Empower: water flow",
    "TDG communication", "TCU communication", "Empower: LBO under-temperature",
    "Empower: LBO stability",
)

# Verified against XP 1.6.0 runtime control IDs = UIR stored IDs + 1.
# 1014 EMP:FAULT? contains only Empower fields among the decoded destinations.
FAULT_WORD_BITS = {
    0: (2, 0x01), 1: (1, 0x10), 2: (0, 0x01), 4: (1, 0x08),
    5: (0, 0x02), 6: (0, 0x08), 12: (0, 0x40), 13: (1, 0x02),
    14: (0, 0x10), 15: (2, 0x10), 17: (1, 0x20), 18: (1, 0x04),
    19: (0, 0x20), 22: (1, 0x40), 23: (1, 0x80), 26: (2, 0x02),
    27: (3, 0xffffffff),  # Original uses the complete LBO stability scalar.
}
MODULE_FAULT_BITS = {
    7: (1066, 0x4000), 8: (1066, 0x8000), 9: (1066, 0x0800),
    11: (1066, 0x2000), 16: (1066, 0x1000),
    20: (1088, 0x10), 21: (1088, 0x04),
    10: (1089, 0x01), 24: (1089, 0x02), 25: (1089, 0x08),
}

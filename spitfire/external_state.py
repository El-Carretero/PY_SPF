"""Readback validation for the Empower-independent controller.

Only controller/TDG/TCU/head observations participate in eligibility checks.
The board's EMPOPTOUT readback remains mandatory: it is a board configuration,
not a connection to an Empower pump. No readback sends a device command.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import time

from .decoders import ResponseDecoder
from .protocol import QUERIES

DECIMAL = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
ALIASES = {1023: 1039, 1061: 1021, 1067: 1050, 1058: 1045, 1059: 1046,
           1063: 1045, 1064: 1046, 1029: 1088, 1057: 1088}
STATUS_IDS = {1015, 1019, 1028, 1029, 1057, 1085, 1086, 1088, 1089}
FLAG_IDS = {1021, 1033, 1044, 1061, 1068, 1069, 1087}
NUMBER_IDS = {1018, 1020, 1024, 1025, 1030, 1031, 1032, 1040, 1041,
              1042, 1043, 1053, 1055, 1056, 1060, 1065, 1084}
FAULT_IDS = (1039, 1066, 1088, 1089)
REQUIRED_IDS = (1068, 1019, 1066, 1021, 1087, 1045, 1046, 1039,
                1050, 1051, 1065, 1088, 1089, 1033, 1044, 1028, 1015, 1069)


def _query_supported(tag):
    title = QUERIES.get(tag, "").upper()
    return bool(title) and not title.startswith(("EMP:", "MIL:"))


def _number(payload, units=()):
    match = re.fullmatch(rf"({DECIMAL})\s*([A-Za-z]*)", payload)
    if not match or (match[2] and match[2].upper() not in units):
        raise ValueError("Malformed numeric readback")
    value = float(match[1])
    if not math.isfinite(value):
        raise ValueError("Non-finite readback")
    return value


@dataclass(frozen=True)
class ChannelState:
    channel: int
    on: bool
    bwd: bool
    enabled: bool
    delay: float


def parse_channel(payload, channel):
    # SASC firmware form, plus the existing reconstruction simulator form.
    patterns = (
        rf"DELAY\s+([1-5])\s+(ON|OFF)\s+(BWD|NBWD)\s+(ENA|NENA)\s+({DECIMAL})",
        rf"([1-5])\s+(ON|OFF)\s+(BWD|NBWD)\s+(ENA|NENA)\s+DELAY\s*=\s*({DECIMAL})",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, payload, re.I)
        if match and int(match[1]) == channel:
            delay = _number(match[5])
            if 0 <= delay <= 1000:
                return ChannelState(channel, match[2].upper() == "ON",
                                    match[3].upper() == "BWD",
                                    match[4].upper() == "ENA", delay)
    raise ValueError("Malformed or wrong-channel delay readback")


class ExternalReadbacks:
    """Validated observations with explicit freshness; ACKs never update facts."""
    def __init__(self, *, stale_after=5.0):
        self.stale_after = stale_after
        self.values = {}
        self.raw_values = {}
        self.updated_at = {}
        self.invalid_ids = set()
        self.connected = False
        self.last_reply_at = None

    def clear(self):
        self.values.clear()
        self.raw_values.clear()
        self.updated_at.clear()
        self.invalid_ids.clear()
        self.connected = False
        self.last_reply_at = None

    def invalidate(self, tag):
        canonical = ALIASES.get(tag, tag)
        self.invalid_ids.update({canonical, tag})
        self.invalid_ids.update(alias for alias, target in ALIASES.items() if target == canonical)

    def value(self, tag, default=None):
        return default if tag in self.invalid_ids else self.values.get(tag, default)

    def link_fresh(self, now):
        return bool(self.connected and self.last_reply_at is not None and
                    0 <= now - self.last_reply_at <= self.stale_after)

    def is_fresh(self, tag, now):
        stamp = self.updated_at.get(tag)
        return bool(self.link_fresh(now) and tag not in self.invalid_ids and
                    stamp is not None and 0 <= now - stamp <= self.stale_after)

    def update(self, tag, payload, now):
        if not _query_supported(tag):
            return False
        self.raw_values[tag] = payload
        raw = payload.strip()
        try:
            if not raw or any(c in payload for c in "\r\n\x00") or re.match(r"^(?:ERR(?:OR)?|NACK|FAIL(?:ED)?|NOT CONNECTED)\b", raw, re.I):
                raise ValueError("Missing/error readback")
            if tag in range(1045, 1050) or tag in (1058, 1059, 1063, 1064):
                channel = {1058: 1, 1059: 2, 1063: 1, 1064: 2}.get(tag, tag - 1044)
                value = parse_channel(raw, channel)
            elif tag in (1023, 1039, 1066):
                if not re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]{1,8}", raw):
                    raise ValueError("Malformed hexadecimal status")
                value = int(raw, 16)
            elif tag in STATUS_IDS:
                number = _number(raw)
                if not 0 <= number <= 0xffffffff or number != int(number):
                    raise ValueError("Invalid status word")
                value = int(number)
            elif tag in FLAG_IDS:
                number = _number(raw)
                if number not in (0, 1):
                    raise ValueError("Invalid Boolean readback")
                value = int(number)
            elif tag in (1050, 1051, 1067, 1080):
                compact = " ".join(raw.upper().split())
                choices = {"INT": 0, "EXT": 1} if tag != 1080 else {"CONT": 0, "COUNT": 1, "COUNT 1": 2}
                if compact in choices:
                    value = choices[compact]
                elif compact in {str(v) for v in choices.values()}:
                    value = int(compact)
                else:
                    compound = re.fullmatch(rf"(INT|EXT) (CONT|COUNT(?: 1)?) ({DECIMAL})", compact)
                    if not compound or tag not in (1051, 1080) or _number(compound[3]) < 0:
                        raise ValueError("Invalid source/output mode")
                    value = ({"INT": 0, "EXT": 1}[compound[1]] if tag == 1051 else
                             {"CONT": 0, "COUNT": 1, "COUNT 1": 2}[compound[2]])
            elif tag in NUMBER_IDS:
                units = ("V", "KV") if tag in (1040, 1041, 1042, 1043) else ("MHZ",) if tag == 1065 else ("MA",) if tag in (1055, 1056) else ()
                value = _number(raw, units)
                # The original voltage controls use kV (range 0..4.16).
                # Bare firmware values and explicit KV already have that scale.
                if tag in (1040, 1041, 1042, 1043) and raw.upper().endswith("V") and not raw.upper().endswith("KV"):
                    value /= 1000
            elif tag == 1052:
                match = re.fullmatch(rf"(?:DELAY\s+0|0\s+DELAY\s*=)\s+({DECIMAL})", raw, re.I)
                value = _number(match[1] if match else raw)
            else:
                value = raw
        except (ValueError, OverflowError):
            self.invalidate(tag)
            return False
        self.values[tag] = value
        self.updated_at[tag] = now
        self.invalid_ids.discard(tag)
        self.last_reply_at = now
        self.connected = True
        if tag in ALIASES:
            canonical = ALIASES[tag]
            self.values[canonical] = value
            self.raw_values[canonical] = payload
            self.updated_at[canonical] = now
            self.invalid_ids.discard(canonical)
        return True

    def channel_on(self, channel, now):
        tag = 1044 + channel
        value = self.value(tag)
        return value.on if self.is_fresh(tag, now) and isinstance(value, ChannelState) else None

    def hv_off_reason(self, now):
        if not self.is_fresh(1021, now):
            return "Fresh device HV state is required."
        return "Device HV must be confirmed OFF." if self.value(1021) != 0 else ""

    def fault_reason(self, now):
        if not all(self.is_fresh(tag, now) for tag in FAULT_IDS + (1015, 1019, 1028, 1068)):
            return "Fault status is unavailable or stale."
        for tag, name in ((1015, "Head"), (1019, "TDG"), (1028, "TCU")):
            if self.value(tag) & 0x800:
                return f"{name} communication is unhealthy."
        if self.value(1066) != 0:
            return "TDG fault or interlock is active."
        if self.value(1039) & 0x00334000:
            return "TDG key interlock or BWD fault is active."
        if self.value(1088) & 0x14:
            return "TCU humidity or TEC temperature fault is active."
        # Ignore only the documented Empower communication bit, and only when
        # opt-out is confirmed. Unknown bits stay actionable.
        mask = ~0x04 if self.is_fresh(1068, now) and self.value(1068) == 1 else 0xffffffff
        if self.value(1089) & mask:
            return "Controller/TDG/TCU communication fault is active."
        return ""

    def enable_block_reason(self, now):
        if not self.link_fresh(now):
            return "No recent controller connection."
        for tag in REQUIRED_IDS:
            if not self.is_fresh(tag, now):
                return f"Required readback [{tag}] is unavailable or stale."
        if self.value(1068) != 1:
            return "Controller Empower opt-out must be explicitly configured and confirmed."
        for tag, name in ((1033, "TCU opt-out"), (1069, "Head opt-out"),
                          (1087, "Fault override"), (1044, "Humidity override")):
            if self.value(tag) != 0:
                return f"{name} must be confirmed OFF."
        for tag, name in ((1019, "TDG"), (1028, "TCU"), (1015, "Head")):
            if self.value(tag) & 0x800:
                return f"{name} communication is unhealthy."
        reason = self.fault_reason(now)
        if reason:
            return reason
        if self.value(1050) != 1 or self.value(1051) != 1:
            return "Oscillator and amplifier trigger sources must both be confirmed EXT."
        if self.value(1065) <= 0:
            return "A positive measured seed frequency is required."
        for channel in (1, 2):
            state = self.value(1044 + channel)
            if not isinstance(state, ChannelState) or not state.bwd or not state.enabled:
                return f"PC{channel} BWD and enable gating must be confirmed active."
        return ""

    def gate_reason(self, now, *, require_off=True):
        reason = self.enable_block_reason(now)
        if reason:
            return reason
        if self.value(1021) != 1:
            return "RUN requires device HV already ON; RUN does not enable HV."
        for tag in (1042, 1043):
            if not self.is_fresh(tag, now) or self.value(tag) <= 0:
                return "RUN requires fresh positive measured HV1 and HV2."
        if require_off and any(self.channel_on(ch, now) is not False for ch in (1, 2)):
            return "RUN requires both PC channels confirmed OFF; request STOP first."
        return ""

    def run_block_reason(self, now):
        return self.gate_reason(now)


class ExternalResponseDecoder(ResponseDecoder):
    """Retain board GUI bindings without legacy pump-dependent side effects."""
    def __init__(self, read=None, *, clock=time.monotonic, stale_after=5.0):
        super().__init__(read=read)
        self.clock = clock
        self.readbacks = ExternalReadbacks(stale_after=stale_after)
        self.last_valid = False

    def decode_line(self, line):
        match = re.fullmatch(r"(?:\(\d+,\d+\))?<(\d+)>(.*)", line, re.S)
        if not match:
            self.last_valid = False
            self.next_queries = []
            self.effects = []
            return []
        return self.decode(int(match[1]), match[2])

    def decode(self, query_id, payload):
        self.last_valid = self.readbacks.update(query_id, payload, self.clock())
        self.next_queries = []
        self.effects = []
        if not self.last_valid:
            return []
        value = self.readbacks.value(query_id)
        normalized = payload
        if isinstance(value, ChannelState):
            normalized = f"{value.channel} {'ON' if value.on else 'OFF'} {'BWD' if value.bwd else 'NBWD'} {'ENA' if value.enabled else 'NENA'} DELAY = {value.delay}"
        elif query_id in NUMBER_IDS:
            normalized = str(value)
        elif query_id in (1023, 1039, 1066):
            normalized = format(value, "x")
        elif query_id in (1050, 1051, 1067):
            normalized = "EXT" if value else "INT"
        elif query_id == 1080:
            normalized = {0: "CONT", 1: "COUNT", 2: "COUNT 1"}[value]
        elif query_id == 1052:
            normalized = f"0 DELAY = {value}"
        updates = super().decode(query_id, normalized)
        self.next_queries = []
        self.effects = [(kind, data) for kind, data in self.effects if kind in ("connected", "open_curtain", "hide_ecu")]
        self.state.pop("call_for_reset_c1n2", None)
        if query_id == 1089:
            updates = [u for u in updates if (u.panel_id, u.control_id) != (3, 9)]
        return updates

    def _refresh_rates(self):
        # Do not read panel 9 (Empower PRF). The trigger readback is a controller
        # observation; the external pump's actual optical repetition is unknown.
        trigger = self.readbacks.value(1053)
        divisor = self.readbacks.value(1025)
        if trigger is not None:
            self._set(6, 8, trigger)
            if divisor is not None and divisor > 0:
                # The recovered GUI alternates these controls with INT/EXT.
                # Both show controller-reported rate settings in this version;
                # neither is a measurement of the separate optical pump.
                self._set(6, 6, trigger / divisor)
                self._set(6, 7, trigger / divisor)

    def check_health(self, access_level=0):
        self._updates = []
        self.next_queries = []
        self.effects = []
        reason = self.readbacks.fault_reason(self.clock())
        # The existing TCP FAULTS? contract uses this exact dimmed attribute.
        # Healthy disables the alarm button; unknown/active remains clickable.
        self._set(6, 50, int(not reason), 500)
        self._set(6, 50, "CHECK STATUS" if reason else "TDG / TCU / HEAD OK", 0x281)
        self._set(6, 50, 0xffff00 if reason else 0xc0c0c0, 0x370)
        self._set(6, 29, int(bool(reason)))
        return self._updates.copy()

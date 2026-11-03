"""Decode response fields recovered from the supplied Empower 3.02 executable.

Response offsets include the complete seven-byte header. They deliberately do
not discard any byte before indexing: the state is at offset28. The real FW1.2
capture has30 bytes including its final additive checksum; legacy synthetic
fixtures have29. Device validates the negotiated length/checksum before these
pure field decoders run.
"""
from __future__ import annotations

from .framing import Frame, ProtocolError

# (absolute byte offset, bit, original fault-indicator meaning).
FAULT_BITS = (
    (7, 0x40, "VSWR"),
    (7, 0x20, "Q-switch overtemperature"),
    (7, 0x10, "Driver protective fault"),
    (7, 0x08, "Driver overpower"),
    (7, 0x02, "Driver overtemperature"),
    (7, 0x01, "Array overtemperature"),
    (8, 0x80, "Water flow"),
    (8, 0x40, "Cover interlock"),
    (8, 0x20, "Key switch"),
    (8, 0x08, "Overvoltage"),
    (8, 0x04, "Overcurrent"),
    (8, 0x02, "Underfrequency"),
    (9, 0x10, "Communication"),
    (9, 0x01, "Array overpower"),
    (9, 0x02, "LBO temperature"),
)
STATE_NAMES = {0: "RUN", 1: "STOP", 2: "FAULT", 3: "COUNTDOWN"}
SERVICE_RAW_OFFSETS = {
    "max_current": 7,
    "power_slope": 10,
    "power_intercept": 12,
    "max_power": 14,
    "lbo_high": 16,
    "lbo_low": 18,
}


def _require(raw: bytes, length: int, opcode: int) -> None:
    if len(raw) < length:
        raise ProtocolError(
            f"Response 0x{opcode:02X} requires at least {length} bytes; got {len(raw)}"
        )


def _word(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 2], "big")


def _firmware(value: tuple[int, int] | None) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ProtocolError("Firmware must be a (major, minor) pair")
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in value):
        raise ProtocolError("Firmware components must be unsigned bytes")
    return tuple(value)


def parse_response(
    frame: Frame, firmware: tuple[int, int] | None = None
) -> dict:
    """Return snapshot updates, leaving unknown response opcodes untouched.

    All floats match original GUI conversions. Service power numbers retain the
    original UIR mW labels; their physical scale remains unverified. Raw words
    accompany settings so combined writes need not reconstruct other fields.
    A missing firmware leaves PRF undecoded rather than silently selecting a
    firmware-dependent scale. The caller merges nested ``service`` updates.
    """
    raw = bytes(frame.raw)
    _require(raw, 7, raw[5] if len(raw) > 5 else 0)
    opcode = frame.opcode
    firmware = _firmware(firmware)
    _require(raw, 7, opcode)
    if raw[5] != opcode:
        raise ProtocolError("Frame opcode does not match raw response")

    if opcode in (0x11, 0x12):
        _require(raw, 29, opcode)
        state_value = raw[28]
        raw_words = {
            "current_word": _word(raw, 20),
            "frequency_word": _word(raw, 10),
            "width_word": _word(raw, 12),
        }
        faults = [name for offset, bit, name in FAULT_BITS if raw[offset] & bit]
        # Known non-fault configuration flag: byte 9 bit 7. Preserve other bits
        # separately; their meaning is not established by original indicators.
        unknown = {7: raw[7] & ~0x7B, 8: raw[8] & ~0xEE, 9: raw[9] & ~0x93}
        unknown = {offset: value for offset, value in unknown.items() if value}
        frequency = None
        if firmware is not None:
            frequency = raw_words["frequency_word"] / (10 if firmware == (0, 1) else 100)
        return {
            "state": STATE_NAMES.get(state_value, f"UNKNOWN ({state_value})"),
            "state_code": state_value,
            "emission": (state_value in (0, 3)) if state_value in STATE_NAMES else None,
            "faults": faults,
            "current_set_a": raw_words["current_word"] / 10,
            "current_a": _word(raw, 22) / 10,
            "hours": int.from_bytes(raw[24:28], "big") / 3600,
            "raw_status": raw[7:10].hex(" ").upper(),
            "unknown_status_bits": unknown,
            "_raw_status_fields": raw_words,
            "service": {
                "qswitch_frequency_khz": frequency,
                "qswitch_pulse_width_ns": raw_words["width_word"] * 125,
                "underfrequency_enabled": bool(raw[9] & 0x80),
            },
        }
    if opcode == 0x62:
        _require(raw, 11, opcode)
        return {"firmware": f"{raw[9]}.{raw[10]}", "firmware_tuple": (raw[9], raw[10])}
    if opcode == 0x72:
        _require(raw, 9, opcode)
        return {"power_w": _word(raw, 7) / 100}
    if opcode == 0x1A:
        _require(raw, 13, opcode)
        return {"service": {"lbo_temp_c": _word(raw, 11) / 10}}
    if opcode == 0x69:
        _require(raw, 10, opcode)
        enabled = bool(raw[7] & 1)
        rate = raw[9] / 2
        return {"service": {
            "soft_start": f"Enabled — {rate:g} A/s" if enabled else "Disabled",
            "soft_start_enabled": enabled,
            "soft_start_rate_a_s": rate,
        }}
    if opcode == 0x70:
        _require(raw, 20, opcode)
        words = {name: _word(raw, offset) for name, offset in SERVICE_RAW_OFFSETS.items()}
        return {
            "max_current_a": words["max_current"] / 10,
            "service_units_unverified": True,
            "service": {
                "max_current_a": words["max_current"] / 10,
                "max_power_mw": words["max_power"] / 100,
                "power_slope_mw_v": words["power_slope"] / 100,
                "power_intercept_mw": words["power_intercept"] / 100,
                "lbo_low_c": words["lbo_low"] / 10,
                "lbo_high_c": words["lbo_high"] / 10,
                "_raw_words": words,
                "_raw_reserved": raw[9],
            },
        }
    if opcode == 0x73:
        _require(raw, 10, opcode)
        return {"service": {"underfrequency_enabled": bool(raw[9] & 0x80)}}
    if opcode == 0x75:
        _require(raw, 8, opcode)
        return {"qswitch": raw[7]}
    # 0x71 is an explicit no-op in the original. Unknown ACK opcodes must not
    # mutate state or be mistaken for successful setting readback.
    return {}

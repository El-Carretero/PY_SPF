"""Byte-exact Empower transmit command builders.

Recovered from the supplied GUI 3.02.00; see docs/PROTOCOL.md. These builders
perform no I/O and never retry. Device-specific bounds and authority belong in
the controller. Mutating functions must be invoked only by deliberate actions.
All offsets in this module are absolute zero-based wire frame offsets.
"""
from __future__ import annotations

import math
import struct
from numbers import Integral
from typing import Mapping

from .framing import encode


READ_REQUESTS = {
    "firmware": 0x42,
    "status": 0x02,
    "qswitch": 0x55,
    "lbo": 0x0B,
    "power": 0x52,
}


def _word(value: int, name: str) -> bytes:
    if isinstance(value, bool) or not isinstance(value, Integral) or not 0 <= value <= 65535:
        raise ValueError(f"{name} must be an integer in 0..65535")
    return int(value).to_bytes(2, "big")


def _number(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite nonnegative number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return value


def _f32(value: float) -> float:
    """CVI controls and intermediate setpoints are IEEE binary32 in the EXE."""
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise ValueError("Value exceeds original GUI numeric range") from exc


def query_firmware() -> bytes:
    return encode(0x42)


def query_status() -> bytes:
    return encode(0x02)


def query_qswitch() -> bytes:
    return encode(0x55)


def query_lbo() -> bytes:
    return encode(0x0B)


def query_power() -> bytes:
    return encode(0x52)


def query_softstart() -> bytes:
    """No nonmutating softstart query has been established.

    Opcode 0x09 belongs to the original RESET callback. Keeping this former
    query entry point as an explicit error prevents an accidental reset.
    """
    raise NotImplementedError(
        "No nonmutating softstart query is established. "
        "Opcode 0x09 is the original fault RESET command."
    )


def query_underfrequency() -> bytes:
    """Use status readback; 0x53 sets protection and is not a read."""
    raise NotImplementedError(
        "Read underfrequency protection from the status query. "
        "Opcode 0x53 changes protection; it is not a query or the original RESET command."
    )


def set_run(enabled: bool) -> bytes:
    """Enable/disable diodes. Wire polarity is inverted: 0=ON, 1=OFF."""
    if type(enabled) is not bool:
        raise ValueError("enabled must be a bool")
    return encode(0x08, bytes((2, 0 if enabled else 1)))


def set_qswitch(source: int) -> bytes:
    """Set original enum: 0 CW RF OFF, 1 HOLD OFF, 2 INTERNAL, 3 EXTERNAL."""
    if type(source) is not int or source not in (0, 1, 2, 3):
        raise ValueError("Q-switch source must be 0 (CW RF OFF), 1 (HOLD OFF), 2 (INTERNAL), or 3 (EXTERNAL)")
    return encode(0x51, bytes((2, source)))


def set_operating_words(current_word: int, frequency_word: int, width_word: int) -> bytes:
    """Combined write preserving known raw words for unchanged fields.

    There is no independently established current-only write. The caller must
    obtain frequency/width from a fresh status response before adjusting current.
    """
    data = bytearray(10)  # wire f6..f15; final checksum supplied by encode
    data[0] = 2
    data[2:4] = _word(frequency_word, "frequency_word")
    data[4:6] = _word(width_word, "width_word")
    data[8:10] = _word(current_word, "current_word")
    return encode(0x01, bytes(data))


def set_operating(current_a: float, freq_khz: float, pulse_ns: float,
                  firmware: tuple[int, int]) -> bytes:
    """Build the GUI's combined operating settings write (truncation semantics).

    Current has 0.1 A resolution; pulse width uses 125 ns ticks. Q-switch
    frequency has 0.01 kHz resolution except firmware 0.1 (0.1 kHz).
    """
    if (not isinstance(firmware, tuple) or len(firmware) != 2
            or any(type(part) is not int or not 0 <= part <= 255 for part in firmware)):
        raise ValueError("A known (major, minor) firmware tuple is required")
    current = int(_f32(_f32(_number(current_a, "current_a")) * 10))
    freq = int(_f32(_f32(_number(freq_khz, "freq_khz")) * (10 if firmware == (0, 1) else 100)))
    width = int(_f32(_f32(_number(pulse_ns, "pulse_ns")) / 125))
    return set_operating_words(current, freq, width)


def reset_faults() -> bytes:
    """Original fault RESET command; it carries no protection-setting byte.

    The supplied FW1.2 capture returns opaque 0x18. A subsequent status read
    is needed to observe the resulting state; an ACK alone proves no clearing.
    """
    return encode(0x09)


def set_underfrequency(underfrequency_enabled: bool) -> bytes:
    """Set underfrequency protection via the original checkbox command."""
    if type(underfrequency_enabled) is not bool:
        raise ValueError("underfrequency_enabled must be a bool")
    return encode(0x53, bytes((2, int(underfrequency_enabled))))


def configure_softstart(enabled: bool, step_word: int) -> bytes:
    """Explicit softstart write. GUI startup uses enabled=True, step_word=1.

    Step interpretation is firmware dependent; no engineering unit is invented.
    """
    if type(enabled) is not bool:
        raise ValueError("enabled must be a bool")
    return encode(0x49, bytes((2, int(enabled))) + _word(step_word, "step_word"))


SERVICE_WORD_KEYS = (
    "max_current", "power_slope", "power_intercept", "max_power", "lbo_high", "lbo_low"
)


def _service_packet(device_code: int, words: Mapping[str, int]) -> bytes:
    missing = set(SERVICE_WORD_KEYS) - set(words)
    if missing:
        raise ValueError(f"Missing service words: {', '.join(sorted(missing))}")
    data = (b"\x02" + _word(device_code, "device_code")
            + _word(words["max_current"], "max_current") + b"\x00"
            + b"".join(_word(words[key], key) for key in SERVICE_WORD_KEYS[1:]))
    return encode(0x50, data)


def service_read() -> bytes:
    """Legacy startup service-read bytes (nonmutation is inferred).

    The original clears its unlabelled numeric-string field then issues 0x50.
    Firmware behavior is unavailable, so this inference is recorded explicitly;
    callers should expose that fact before first real connection. No device
    service code is embedded in this package.
    """
    words = {key: 0 for key in SERVICE_WORD_KEYS}
    # Original UIR startup defaults: overtemp 9 C, undertemp 5 C.
    words.update(lbo_high=90, lbo_low=50)
    return _service_packet(0, words)


def set_service_words(device_code: int, words: Mapping[str, int]) -> bytes:
    """Build the original service transaction, including its numeric field.

    The original uses atoi() on an unlabelled string control, so blank sends0.
    Authorization semantics are unconfirmed. Zero is allowed for compatibility,
    but does not establish write acceptance or bypass device-side validation.
    Callers must preserve other fields and verify subsequent service readback.
    """
    _word(device_code, "device_code")
    return _service_packet(device_code, words)


def set_service(device_code: int, *, max_current_a: float, power_slope_mw_v: float,
                power_intercept_mw: float, max_power_mw: float,
                lbo_high_c: float, lbo_low_c: float) -> bytes:
    """Legacy numeric service serializer: truncate BEFORE scaling.

    The original casts floats to integer then multiplies, unlike operating
    current. This intentionally reproduces that quirk. For exact preservation
    of unchanged decimal settings, use set_service_words with raw readbacks.
    Power units follow original UI labels and are not independently calibrated.
    """
    values = {
        "max_current": (max_current_a, 10),
        "power_slope": (power_slope_mw_v, 100),
        "power_intercept": (power_intercept_mw, 100),
        "max_power": (max_power_mw, 100),
        "lbo_high": (lbo_high_c, 10),
        "lbo_low": (lbo_low_c, 10),
    }
    return set_service_words(device_code, {
        key: int(_f32(_number(value, key))) * scale for key, (value, scale) in values.items()
    })

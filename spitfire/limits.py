"""Shared product limits for the internal amplifier trigger-rate input."""
from __future__ import annotations

import math


INTERNAL_TRIGGER_MIN_HZ = 10.0
INTERNAL_TRIGGER_MAX_HZ = 10000.0


def validate_internal_trigger_hz(value) -> float:
    """Validate before CVI float conversion or command serialization."""
    try:
        frequency = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Internal trigger rate must be finite and between 10 and 10000 Hz.") from exc
    if (not math.isfinite(frequency)
            or not INTERNAL_TRIGGER_MIN_HZ <= frequency <= INTERNAL_TRIGGER_MAX_HZ):
        raise ValueError("Internal trigger rate must be finite and between 10 and 10000 Hz.")
    return frequency

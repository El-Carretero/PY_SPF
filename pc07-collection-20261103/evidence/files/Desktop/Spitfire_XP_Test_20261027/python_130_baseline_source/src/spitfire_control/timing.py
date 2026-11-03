"""Validated expectations for external timing; actual pump rate is unobserved."""
from __future__ import annotations
import math

def validate_timing_expectations(seed_mhz: float, tolerance_mhz: float, pump_hz: float) -> None:
    for value, label in ((seed_mhz, "Expected seed MHz"), (tolerance_mhz, "Seed tolerance MHz"), (pump_hz, "Expected pump Hz")):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be a finite positive number")
        try:
            valid = math.isfinite(value) and value > 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"{label} must be a finite positive number")
    if tolerance_mhz >= seed_mhz:
        raise ValueError("Seed tolerance must be smaller than the expected frequency")

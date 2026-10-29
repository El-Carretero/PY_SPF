"""Outbound command policy for the Empower-independent application.

The original command catalogue remains in ``protocol.py`` as evidence, but it
is not an allowlist. All operational requests pass through this module before
queueing and again when their wire message is built. Firmware opt-out is a
controller-board setting; querying it does not contact an Empower subsystem.
"""
from __future__ import annotations

import math
import re

from .protocol import COMMANDS, QUERIES


RESET_COMMAND_IDS = (2049, 2052, 2050)
REQUIRED_READBACKS = (
    1068, 1069, 1033, 1087, 1044, 1019, 1015, 1028, 1039, 1066,
    1088, 1089, 1021, 1042, 1043, 1045, 1046, 1050, 1051, 1065, 1025,
)
POLL_READBACKS = REQUIRED_READBACKS + (1047, 1048, 1049, 1029, 1030, 1031, 1084, 1053)
SERVICE_READBACKS = (1055, 1056)

_NO_ARGUMENT_WRITES = frozenset({
    2009, 2010, 2011, 2012, 2013, 2016, 2017, 2018, 2022, 2023,
    *RESET_COMMAND_IDS,
})
_NUMERIC_WRITES = frozenset({2014, 2015, 2021, 2025, 2026, 2032, 2046})
_STOP_WRITES = frozenset({2013, 2016, 2023})
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def query_allowed(tag: int) -> bool:
    """Only known, non-pump readbacks are available in this application."""
    return type(tag) is int and tag in QUERIES and not QUERIES[tag].upper().startswith(("EMP:", "MIL:"))


def _number(argument: str) -> float:
    if not _NUMBER.fullmatch(argument):
        raise ValueError("A single finite numeric argument is required")
    value = float(argument)
    if not math.isfinite(value):
        raise ValueError("A finite numeric argument is required")
    return value


def validate_request(tag: int, parameter: str = "") -> None:
    """Reject pump/global/raw requests and malformed or unprotected writes.

    This validates the request's structure and static policy. The controller
    additionally checks current readback freshness and operation conditions.
    Parameters retain the original leading-space formatting contract.
    """
    if type(tag) is not int or tag not in QUERIES and tag not in COMMANDS:
        raise ValueError("Unknown command ID")
    if not isinstance(parameter, str):
        raise ValueError("Command parameters must be text")
    if len(parameter) > 128 or any(ord(c) < 32 or ord(c) > 126 for c in parameter):
        raise ValueError("Command parameters must contain only printable ASCII")
    if any(c in parameter for c in ";[],:<>"):
        raise ValueError("Only one structured command is allowed")
    argument = parameter.strip()
    if argument and not parameter.startswith(" "):
        raise ValueError("Command arguments must be separated by a leading space")
    if tag < 2000:
        if not query_allowed(tag):
            raise PermissionError("Pump queries are unavailable in the Empower-independent application")
        if tag == 1026:
            if argument not in {"", "1", "2", "3", "4", "5"}:
                raise ValueError("Delay query channel must be 1..5")
        elif argument:
            raise ValueError("This query does not accept an argument")
        return
    if COMMANDS[tag].upper().startswith(("EMP:", "MIL:")) or tag in {2027, 2028, 2033, 2034, 2054, 2055}:
        raise PermissionError("Pump, global ON/OFF and raw commands are unavailable")
    if tag in _NO_ARGUMENT_WRITES:
        if argument:
            raise ValueError("This command does not accept an argument")
    elif tag in _NUMERIC_WRITES:
        value = _number(argument)
        if tag != 2021 and value < 0:
            raise ValueError("This setting must not be negative")
    elif tag == 2019:
        fields = argument.split()
        if len(fields) != 2 or fields[0] not in {"1", "2", "3", "4", "5"}:
            raise ValueError("Delay command requires a channel from 1..5 and one setting")
        setting = fields[1].upper()
        if setting in {"NBWD", "NENA"}:
            raise PermissionError("BWD and enable gating must remain active")
        if setting not in {"ON", "OFF", "BWD", "ENA"}:
            value = _number(setting)
            if not 0 <= value <= 1000:
                raise ValueError("Delay must be within 0..1000 ns")
    elif tag == 2020:
        value = _number(argument)
        if value < 1 or not value.is_integer():
            raise ValueError("Divisor must be a positive integer")
    elif tag in {2024, 2029, 2035, 2053}:
        if argument != "0":
            raise PermissionError("Head/ECU opt-out and protection overrides cannot be enabled")
    elif tag == 2036:
        if argument != "1":
            raise PermissionError("This application requires Empower opt-out; only value 1 is allowed")
    elif tag in {2030, 2031}:
        if argument.upper() not in {"INT", "EXT"}:
            raise ValueError("Timing source must be INT or EXT")
    elif tag == 2048:
        if " ".join(argument.upper().split()) not in {"CONT", "COUNT", "COUNT 1"}:
            raise ValueError("Output mode must be CONT, COUNT or COUNT 1")
    elif tag == 2051:
        if argument not in {"0", "1"}:
            raise ValueError("Monitor setting must be 0 or 1")
    else:
        raise PermissionError("Command has no Empower-independent policy")


def is_stop_request(tag: int, parameter: str = "") -> bool:
    if not isinstance(parameter, str):
        return False
    return tag in _STOP_WRITES and not parameter.strip() or (
        tag == 2019 and " ".join(parameter.upper().split()) in {f"{channel} OFF" for channel in range(1, 6)}
    )

"""Pump configuration policy, independent of simulator/UDP transport.

No policy fabricates device readbacks or automatically writes firmware options.
EMP:FAULT? is Empower-only; TDG, TCU and communications have separate queries.
"""
from __future__ import annotations

import math

PUMP_MODES = ("empower", "external")
EMPOWER_QUERY_IDS = frozenset((*range(1007, 1015), 1016, 1035, *range(1070, 1079)))
EXTERNAL_BLOCKED_WRITES = frozenset((*range(2000, 2009), 2027, 2028, 2033, 2034,
                                    *range(2037, 2046), 2047, 2050, 2054, 2055))
EXTERNAL_REQUIRED_READS = (1068, 1019, 1066, 1021, 1087, 1045, 1046, 1039, 1050, 1051, 1065, 1088, 1089, 1033, 1044, 1028, 1015, 1069)


def validate_pump_mode(mode: str) -> str:
    if mode not in PUMP_MODES:
        raise ValueError(f"Unknown pump mode: {mode!r}")
    return mode


def query_allowed(command_id: int, mode: str) -> bool:
    validate_pump_mode(mode)
    return command_id < 2000 and (mode != "external" or command_id not in EMPOWER_QUERY_IDS)


def filter_queries(ids, mode: str) -> tuple[int, ...]:
    return tuple(cid for cid in ids if query_allowed(cid, mode))


def validate_profile_command(command_id: int, argument: object | None, mode: str) -> None:
    """Enforced on submission AND at send time, including Programmer commands."""
    validate_pump_mode(mode)
    if mode != "external":
        return
    arg = "" if argument is None else str(argument).strip()
    if any(ord(c) < 32 for c in arg) or ";" in arg:
        raise ValueError("External pump mode accepts one structured command only.")
    if command_id < 2000:
        if not query_allowed(command_id, mode):
            raise PermissionError("Empower is excluded in External Pump mode.")
        if arg and command_id != 1026:
            raise ValueError("This query does not accept an argument.")
        if command_id == 1026 and arg not in {"", "1", "2", "3", "4", "5"}:
            raise ValueError("Delay query channel must be 1..5.")
        return
    if command_id in EXTERNAL_BLOCKED_WRITES:
        raise PermissionError("This pump/global/raw command is unavailable in External Pump mode.")
    no_arg = {2009, 2010, 2011, 2012, 2013, 2016, 2017, 2018, 2022, 2023, 2049, 2052}
    numeric = {2014, 2015, 2021, 2025, 2026, 2032, 2046}
    if command_id in no_arg:
        if arg:
            raise ValueError("This command does not accept an argument.")
    elif command_id in numeric:
        try:
            valid = math.isfinite(float(arg))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("A finite numeric argument is required.")
    elif command_id == 2019:
        fields = arg.split()
        if len(fields) != 2 or fields[0] not in {"1", "2", "3", "4", "5"}:
            raise ValueError("Delay command requires channel 1..5 and one setting.")
        setting = fields[1].upper()
        if setting in {"NBWD", "NENA"}:
            raise PermissionError("External Pump mode retains BWD and enable gating.")
        if setting not in {"ON", "OFF", "BWD", "ENA"}:
            try:
                number = float(setting)
            except ValueError:
                number = float("nan")
            if not math.isfinite(number) or not 0 <= number <= 1000:
                raise ValueError("Delay must be 0..1000 ns or ON/OFF/BWD/ENA.")
    elif command_id == 2020:
        if not arg.isdecimal() or int(arg) < 1:
            raise ValueError("Divisor must be a positive integer.")
    elif command_id in {2024, 2029, 2035, 2053}:
        if arg != "0":
            raise PermissionError("Protection overrides cannot be enabled in External Pump mode.")
    elif command_id in {2030, 2031}:
        if arg.upper() not in {"INT", "EXT"}:
            raise ValueError("Mode must be INT or EXT.")
    elif command_id == 2036:
        if arg not in {"0", "1"}:
            raise ValueError("Empower opt-out must be 0 or 1.")
    elif command_id == 2048:
        if arg.upper() not in {"CONT", "COUNT", "COUNT 1"}:
            raise ValueError("Output mode must be CONT, COUNT, or COUNT 1.")
    elif command_id == 2051:
        if arg not in {"0", "1"}:
            raise ValueError("Monitor must be 0 or 1.")
    else:
        raise PermissionError("Command has no External Pump policy.")


def requires_external_enable_check(command_id: int, argument: object | None) -> bool:
    if command_id in {2017, 2048}:
        return True
    return command_id == 2019 and str(argument).strip().upper().endswith(" ON")


def is_stop_command(command_id: int, argument: object | None = None) -> bool:
    # CH OFF remains usable even when ARM or compatibility has been lost.
    return command_id == 2019 and " ".join(str(argument).upper().split()) in {f"{c} OFF" for c in range(1, 6)}

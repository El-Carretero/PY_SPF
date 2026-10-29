"""Deterministic, stateful virtual Spitfire controller.

This is a protocol twin, not a laser-physics simulator.  By default every
client receives an isolated copy of the same state so the XP and Python GUIs
cannot perturb one another while being compared.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import math
import threading
from typing import Any

from .catalog import COMMANDS
from . import __version__
from .protocol import WireCommand


def _default_values() -> dict[int, Any]:
    identity = f"Spectra-Physics,Spitfire,0,TWIN-{__version__}"
    values: dict[int, Any] = {cid: 0 for cid in range(1000, 1090)}
    values.update({
        1000: identity,
        1001: 0.0, 1002: 0.0, 1003: 0.0,
        1004: 0.0, 1005: 0.0, 1006: 0.0,
        1007: 0.0, 1008: 0.0, 1009: 180.0,
        # Wire unit is 10 Hz; both clients should display 1000 Hz.
        1010: 100.0, 1011: 120.0, 1012: 0,
        1013: 0, 1014: "0 0 0 0", 1015: 0,
        1016: "EMP-TWIN-1.0", 1017: "HED-MOTOR-TWIN", 1018: 100,
        1019: 0, 1020: 0.0, 1021: 0, 1022: 0, 1023: 0,
        1024: 80.0, 1025: 1, 1026: 0, 1027: 0,
        1028: 0, 1029: 0, 1030: 25.0, 1031: 34.0,
        1032: 25.0, 1033: 0, 1034: "HED-TWIN-1.0",
        1035: "EMP-TWIN-1.0", 1036: "TDG-TWIN-1.0",
        1037: "ECU-TWIN-1.0", 1038: identity,
        1039: 0, 1040: 0.65, 1041: 0.65,
        1042: 0.0, 1043: 0.0, 1044: 0,
        1050: 'INT', 1051: 'INT', 1052: 0.0, 1053: 1000.0,
        1054: 0, 1055: 0.0, 1056: 0.0, 1057: 0,
        1060: 100, 1061: 0,
        1062: identity,
        1065: 80.0, 1066: 0, 1067: 0, 1068: 0, 1069: 0,
        1070: "0", 1071: "45.0", 1072: "1.0", 1073: "0.0",
        1074: "100.0", 1075: "55.0", 1076: "15.0", 1077: 43.0,
        1078: 0, 1079: 0, 1080: 0,
        1081: identity,
        1082: identity,
        1083: 0, 1084: 25.2, 1085: 0, 1086: 0,
        1087: 0, 1088: 0, 1089: 0,
    })
    return values


@dataclass(slots=True)
class ResponseProfile:
    """Controlled response variations applied equally to both clients."""

    name: str = "Nominal"
    overrides: dict[int, str] = field(default_factory=dict)
    error_ids: set[int] = field(default_factory=set)
    drop_ids: set[int] = field(default_factory=set)
    delay_ms: dict[int, int] = field(default_factory=dict)
    request_drop_ids: set[int] = field(default_factory=set)
    line_ending: str = "\n"
    malformed_reply_header: bool = False

    def copy(self) -> "ResponseProfile":
        import copy
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("error_ids", "drop_ids", "request_drop_ids"):
            data[key] = sorted(data[key])
        return data


@dataclass(slots=True)
class ClientState:
    values: dict[int, Any] = field(default_factory=_default_values)
    delays: dict[int, dict[str, Any]] = field(default_factory=lambda: {
        channel: {"value": 0.0, "switch": "OFF", "bwd": "BWD", "enable": "ENA"}
        for channel in range(1, 6)
    })

    def clone(self) -> "ClientState":
        return ClientState(dict(self.values), {key: dict(value) for key, value in self.delays.items()})


@dataclass(frozen=True, slots=True)
class DeviceAnswer:
    value: str | None
    delay_ms: int = 0
    dropped: bool = False
    note: str = ""
    validation: str = "VALID"
    modelled: bool = True
    effect: str = "query"


# IDs that name the same logical setting must read the same storage location.
QUERY_ALIASES = {1018: 1060, 1027: 1054, 1039: 1023,
                 1057: 1029, 1088: 1029, 1061: 1021, 1067: 1050}
NUMERIC_WRITES = {2000, 2001, 2002, 2003, 2004, 2007, 2008, 2014, 2015,
                  2020, 2021, 2024, 2025, 2026, 2029, 2032, 2035, 2036,
                  2046, 2047, 2051, 2053}
NO_ARGUMENT_WRITES = {2005, 2006, 2009, 2010, 2011, 2012, 2013, 2016, 2017,
                      2018, 2022, 2023, 2027, 2028, 2044, 2045, 2049, 2050,
                      2052, 2054, 2055}
UNMODELLED_WRITES = {2009, 2010, 2011, 2012, 2013, 2018, 2034, 2045, 2050, 2054, 2055}


class VirtualSpitfire:
    """Thread-safe state model with isolated or shared client state."""

    def __init__(self, *, isolated_clients: bool = True):
        self.isolated_clients = isolated_clients
        self.profile = ResponseProfile()
        self._states: dict[str, ClientState] = {}
        self._shared = ClientState()
        self._lock = threading.RLock()

    def reset(self, client_key: str | None = None) -> None:
        with self._lock:
            if client_key is None:
                self._states.clear()
                self._shared = ClientState()
            else:
                self._states.pop(client_key, None)

    def state_for(self, client_key: str) -> ClientState:
        if not self.isolated_clients:
            return self._shared
        return self._states.setdefault(client_key, ClientState())

    def snapshot(self, client_key: str) -> dict[int, Any]:
        with self._lock:
            state = self.state_for(client_key)
            return {cid: self._query_value(state, cid) for cid in COMMANDS if cid < 2000}

    def get_profile(self) -> ResponseProfile:
        with self._lock:
            return self.profile.copy()

    def set_profile(self, profile: ResponseProfile) -> None:
        with self._lock:
            self.profile = profile.copy()

    @staticmethod
    def _render(value: Any) -> str:
        if isinstance(value, float):
            if not math.isfinite(value):
                return str(value)
            return f"{value:.6f}".rstrip("0").rstrip(".")
        return str(value)

    @staticmethod
    def _number(argument: str) -> float:
        value = float(argument)
        if not math.isfinite(value):
            raise ValueError("non-finite numeric argument")
        return value

    def _query_value(self, state: ClientState, command_id: int) -> str:
        delay_channel = {1045: 1, 1046: 2, 1047: 3, 1048: 4, 1049: 5,
                         1058: 1, 1059: 2, 1063: 1, 1064: 2}.get(command_id)
        if delay_channel is not None:
            item = state.delays[delay_channel]
            # Captured SASC grammar, including the separator after <id>.
            # XP's decoder is sensitive to that leading space.
            return (f" DELAY {delay_channel} {item['switch']} {item['bwd']} {item['enable']} "
                    f"{self._render(item['value'])}")
        value = state.values.get(QUERY_ALIASES.get(command_id, command_id), 0)
        if command_id in {1023,1039,1066} and isinstance(value,int) and value != 0:
            return f"0X{value:08X}"
        return self._render(value)

    def _write(self, state: ClientState, command: WireCommand) -> str:
        cid, arg = command.command_id, command.argument
        numeric_targets = {
            2000: 1001, 2001: 1002, 2002: 1003, 2003: 1009,
            2004: 1010, 2007: 1011, 2008: 1012, 2014: 1060,
            2015: 1020, 2020: 1025, 2021: 1032, 2024: 1033,
            2025: 1040, 2026: 1041, 2029: 1044, 2032: 1053,
            2035: 1069, 2036: 1068, 2046: 1065, 2047: 1078,
            2051: 1086, 2053: 1087,
        }
        try:
            if cid in numeric_targets and arg:
                value = self._number(arg)
                if value.is_integer():
                    value = int(value)
                state.values[numeric_targets[cid]] = value
                if cid == 2046:
                    state.values[1065] = value
            elif cid in {2005, 2027}:
                state.values[1013] = 1
            elif cid in {2006, 2028}:
                state.values[1013] = 0
            elif cid == 2016:
                state.values[1021] = state.values[1061] = 0
                state.values[1042] = state.values[1043] = 0.0
                state.values[1055] = state.values[1056] = 0.0
            elif cid == 2017:
                state.values[1021] = state.values[1061] = 1
                state.values[1042] = state.values[1040]
                state.values[1043] = state.values[1041]
                # Current readbacks remain fixture values; no invented V/I physics.
            elif cid == 2019:
                tokens = arg.split(maxsplit=1)
                if len(tokens) != 2 or int(tokens[0]) not in state.delays:
                    return "ERROR:ARG"
                channel, setting = int(tokens[0]), tokens[1].strip()
                upper = setting.upper()
                if upper in {"ON", "OFF"}:
                    state.delays[channel]["switch"] = upper
                elif upper in {"BWD", "NBWD"}:
                    state.delays[channel]["bwd"] = upper
                elif upper in {"ENA", "NENA"}:
                    state.delays[channel]["enable"] = upper
                else:
                    state.delays[channel]["value"] = self._number(setting)
                    state.values[1044 + channel] = state.delays[channel]["value"]
            elif cid == 2022:
                state.values[1028] = 1
            elif cid == 2023:
                state.values[1028] = 0
            elif cid == 2030:
                state.values[1050] = state.values[1067] = ('EXT' if arg.upper().startswith('EXT') else 'INT')
            elif cid == 2031:
                state.values[1051] = 'EXT' if arg.upper().startswith('EXT') else 'INT'
            elif cid == 2033:
                state.values[1054] = 1 if arg.upper() in {"1", "ON", "BWD"} else 0
            elif 2037 <= cid <= 2043:
                state.values[1070 + (cid - 2037)] = arg
            elif cid == 2048:
                state.values[1080] = {"CONT": 0, "COUNT": 1, "COUNT 1": 2}.get(arg.upper(), 0)
            elif cid == 2044:
                state.values[1014] = "0 0 0 0"
            elif cid == 2049:
                state.values[1029] = 0
            elif cid == 2052:
                state.values[1066] = 0
            # Remaining recovered writes are accepted without inventing a
            # physical effect. Their exact wire traffic is still recorded.
        except (ValueError, OverflowError):
            return "ERROR:ARG"
        return "OK"

    @staticmethod
    def validate_command(command: WireCommand) -> str:
        spec = COMMANDS.get(command.command_id)
        if spec is None:
            return "UNKNOWN_ID"
        if command.base != spec.text:
            return "ID_TEXT_MISMATCH"
        cid, arg = command.command_id, command.argument
        if cid < 2000:
            if cid == 1026 and arg:
                return 'VALID' if arg in {'1', '2', '3', '4', '5'} else 'INVALID_ARGUMENT'
            return "INVALID_ARGUMENT" if arg else "VALID"
        if cid in NO_ARGUMENT_WRITES:
            return "INVALID_ARGUMENT" if arg else "VALID"
        if cid in NUMERIC_WRITES:
            try:
                VirtualSpitfire._number(arg)
            except (ValueError, OverflowError):
                return "INVALID_ARGUMENT"
        elif cid == 2019:
            parts = arg.split(maxsplit=1)
            try:
                if len(parts) != 2 or int(parts[0]) not in range(1, 6):
                    return "INVALID_ARGUMENT"
                if parts[1].upper() not in {"ON", "OFF", "BWD", "NBWD", "ENA", "NENA"}:
                    VirtualSpitfire._number(parts[1])
            except (ValueError, OverflowError):
                return "INVALID_ARGUMENT"
        elif cid in {2030, 2031} and arg.upper() not in {"INT", "EXT", "INTERNAL", "EXTERNAL"}:
            return "INVALID_ARGUMENT"
        elif cid == 2033 and arg.upper() not in {"0", "1", "ON", "OFF", "BWD", "NBWD"}:
            return "INVALID_ARGUMENT"
        elif cid == 2048 and arg.upper() not in {"CONT", "COUNT", "COUNT 1"}:
            return "INVALID_ARGUMENT"
        elif 2037 <= cid <= 2043 and not arg:
            return "INVALID_ARGUMENT"
        return "VALID"

    def answer(self, client_key: str, command: WireCommand,
               profile: ResponseProfile | None = None) -> DeviceAnswer:
        with self._lock:
            profile = profile or self.profile.copy()
            cid = command.command_id
            delay = profile.delay_ms.get(cid, 0)
            validation = self.validate_command(command)
            if validation != "VALID":
                # These are verifier fixture errors, not asserted firmware error strings.
                return DeviceAnswer("ERROR:VALIDATION:" + validation, delay,
                                    note="verifier validation error", validation=validation,
                                    modelled=False, effect="rejected")
            if cid in profile.request_drop_ids:
                return DeviceAnswer(None, delay, True, "request loss; not executed", effect="not_executed")
            state = self.state_for(client_key)
            modelled = cid not in UNMODELLED_WRITES and cid != 1026
            if cid in profile.error_ids:
                value, note, effect = "ERROR:INJECTED", "profile error; not executed", "not_executed"
            elif cid >= 2000:
                value = self._write(state, command)
                note = "synthetic write acknowledgement" if modelled else "acknowledged; effect unmodelled"
                effect = "write_applied" if modelled else "unmodelled"
            else:
                value, note, effect = self._query_value(state, cid), "fixture query", "query"
                if cid == 1026:
                    # Argument construction exists in XP; reply grammar does not.
                    value = self._query_value(state, 1044 + int(command.argument)) if command.argument else '0'
                    note, effect = 'unverified generic channel-query fixture', 'unmodelled_query'
            if cid in profile.overrides and cid not in profile.error_ids:
                value = profile.overrides[cid]
                note += "; response override"
            if cid in profile.drop_ids:
                return DeviceAnswer(None, delay, True, note + "; reply lost after execution",
                                    modelled=modelled, effect=effect)
            return DeviceAnswer(value, delay, False, note, modelled=modelled, effect=effect)

"""Command catalogue recovered from the Spitfire GUI 1.6.0 executable.

The legacy application prepends ``[numeric_id]`` to each controller command.
Commands >= 2000 are writes; commands in the 1000 range are reads.  The small
number of exceptional commands is preserved verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final
from decimal import Decimal, InvalidOperation


class Risk(str, Enum):
    READ = "read"
    CONFIG = "config"
    MOTION = "motion"
    LASER = "laser"
    HIGH_VOLTAGE = "high_voltage"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    id: int
    text: str
    risk: Risk
    description: str = ""

    @property
    def writable(self) -> bool:
        return self.id >= 2000

    @property
    def dangerous(self) -> bool:
        return self.risk in {Risk.MOTION, Risk.LASER, Risk.HIGH_VOLTAGE, Risk.SERVICE}


_QUERIES: Final[dict[int, str]] = {
    1000: "*idn?", 1001: "MIL:DIODE1:CURR?", 1002: "MIL:DIODE2:CURR?",
    1003: "MIL:POW?", 1004: "MIL:READ:DIODE1:CURR?",
    1005: "MIL:READ:DIODE2:CURR?", 1006: "MIL:READ:POW?",
    1007: "EMP:READ:DIODE:CURR?", 1008: "EMP:READ:POW?",
    1009: "EMP:DIODE:CURR?", 1010: "EMP:QSW:PRF?", 1011: "EMP:QSW:PWID?",
    1012: "EMP:QSW:SOURCE?", 1013: "EMP:STB?", 1014: "EMP:FAULT?",
    1015: "HED:STB?", 1016: "EMP:VERSION?", 1017: "HED:MOTOR:*IDN?",
    1018: "HED:MOTOR:SPEED?", 1019: "TDG:STB?", 1020: "TDG:VOLT?",
    1021: "TDG:HV:ON?", 1022: "TDG:STAT:BWD?", 1023: "TDG:STBH?",
    1024: "TDG:OSC:FREQ?", 1025: "TDG:DIV?", 1026: "TDG:DEL",
    1027: "TDG:BWD?", 1028: "ECU:STB?", 1029: "ECU:STBH?",
    1030: "ECU:READTEMP?", 1031: "ECU:HUM?", 1032: "ECU:TEMP?",
    1033: "ECUOPTOUT?", 1034: "HED:VERS?", 1035: "EMP:VERS?",
    1036: "TDG:VERS?", 1037: "ECU:VERS?", 1038: "*IDN?",
    1039: "TDG:STBH?", 1040: "TDG:HV1:VOLT?", 1041: "TDG:HV2:VOLT?",
    1042: "TDG:READ:HV1VOLT?", 1043: "TDG:READ:HV2VOLT?",
    1044: "ECU:HUMOVERRIDE?", 1045: "TDG:DEL1?", 1046: "TDG:DEL2?",
    1047: "TDG:DEL3?", 1048: "TDG:DEL4?", 1049: "TDG:DEL5?",
    1050: "TDG:OSC:MODE?", 1051: "TDG:TRIG:MODE?", 1052: "TDG:DEL0?",
    1053: "TDG:TRIG:FREQ?", 1054: "TDG:BWD?",
    1055: "TDG:READ:HV1CURR?", 1056: "TDG:READ:HV2CURR?",
    1057: "ECU:STBH?", 1058: "TDG:DEL1?", 1059: "TDG:DEL2?",
    1060: "HED:MOTOR:SPEED?", 1061: "TDG:HV:ON?", 1062: "*IDN?",
    1063: "TDG:DEL1?", 1064: "TDG:DEL2?", 1065: "TDG:READ:OSCQUEST?",
    1066: "TDG:STBHFLT?", 1067: "TDG:OSC:MODE?", 1068: "EMPOPTOUT?",
    1069: "HEDOPTOUT?", 1070: "EMP:SECRETMSG1?", 1071: "EMP:SECRETMSG2?",
    1072: "EMP:SECRETMSG3?", 1073: "EMP:SECRETMSG4?",
    1074: "EMP:SECRETMSG5?", 1075: "EMP:SECRETMSG6?",
    1076: "EMP:SECRETMSG7?", 1077: "EMP:LBOTEMP?", 1078: "EMP:LBOBREAK?",
    1079: "TDG:TRIG?", 1080: "TDG:OSC:SETMODE?", 1081: "*IDN?",
    1082: "*IdN?", 1083: "TDG:DELMON?", 1084: "ECU:TECTEMP?",
    1085: "STATUS?", 1086: "MONITOR?", 1087: "TDG:FAULTOVERRIDE?",
    1088: "ECU:STBH?", 1089: "COMSTATUS?",
}

_WRITES: Final[dict[int, tuple[str, Risk]]] = {
    2000: ("MIL:DIODE1:CURR", Risk.SERVICE),
    2001: ("MIL:DIODE2:CURR", Risk.SERVICE),
    2002: ("MIL:READ:POW", Risk.SERVICE),
    2003: ("EMP:DIODE:CURR", Risk.LASER),
    2004: ("EMP:QSW:PRF", Risk.LASER),
    2005: ("EMP:ON", Risk.LASER), 2006: ("EMP:OFF", Risk.LASER),
    2007: ("EMP:QSW:PWID", Risk.LASER), 2008: ("EMP:QSW:SOURCE", Risk.LASER),
    2009: ("HED:MOTOR:REW", Risk.MOTION), 2010: ("HED:MOTOR:FWD", Risk.MOTION),
    2011: ("HED:MOTOR:JOGF", Risk.MOTION), 2012: ("HED:MOTOR:JOGR", Risk.MOTION),
    2013: ("HED:MOTOR:STOP", Risk.MOTION), 2014: ("HED:MOTOR:SPEED", Risk.MOTION),
    2015: ("TDG:VOLT", Risk.HIGH_VOLTAGE), 2016: ("TDG:HV:OFF", Risk.HIGH_VOLTAGE),
    2017: ("TDG:HV:ON", Risk.HIGH_VOLTAGE), 2018: ("TDG:RESBWD", Risk.HIGH_VOLTAGE),
    2019: ("TDG:DEL", Risk.CONFIG), 2020: ("TDG:DIV", Risk.CONFIG),
    2021: ("ECU:TEMP", Risk.CONFIG), 2022: ("ECU:TECON", Risk.CONFIG),
    2023: ("ECU:TECOFF", Risk.CONFIG), 2024: ("ECUOPTOUT", Risk.SERVICE),
    2025: ("TDG:HV1:VOLT", Risk.HIGH_VOLTAGE),
    2026: ("TDG:HV2:VOLT", Risk.HIGH_VOLTAGE),
    2027: ("ON", Risk.LASER), 2028: ("OFF", Risk.LASER),
    2029: ("ECU:HUMOVERRIDE", Risk.SERVICE), 2030: ("TDG:OSC:MODE", Risk.CONFIG),
    2031: ("TDG:TRIG:MODE", Risk.CONFIG), 2032: ("TDG:TRIG:FREQ", Risk.CONFIG),
    2033: ("TDG:BWD", Risk.CONFIG), 2034: ("", Risk.SERVICE),
    2035: ("HEDOPTOUT", Risk.SERVICE), 2036: ("EMPOPTOUT", Risk.SERVICE),
    2037: ("EMP:SECRETMSG1", Risk.SERVICE), 2038: ("EMP:SECRETMSG2", Risk.SERVICE),
    2039: ("EMP:SECRETMSG3", Risk.SERVICE), 2040: ("EMP:SECRETMSG4", Risk.SERVICE),
    2041: ("EMP:SECRETMSG5", Risk.SERVICE), 2042: ("EMP:SECRETMSG6", Risk.SERVICE),
    2043: ("EMP:SECRETMSG7", Risk.SERVICE), 2044: ("EMP:RESETFAULTS", Risk.SERVICE),
    2045: ("EMP:SECRETSCOMT", Risk.SERVICE), 2046: ("TDG:OSC:SETTOFRQ", Risk.CONFIG),
    2047: ("EMP:LBOBREAK", Risk.SERVICE), 2048: ("TDG:OSC:SETMODE", Risk.CONFIG),
    2049: ("ECU:RESETFAULTS", Risk.SERVICE), 2050: ("RESET", Risk.SERVICE),
    2051: ("MONITOR", Risk.CONFIG), 2052: ("TDG:RESFAULT", Risk.SERVICE),
    2053: ("TDG:FAULTOVERRIDE", Risk.SERVICE), 2054: ("RES12", Risk.SERVICE),
    2055: ("CLEAR", Risk.SERVICE),
}


def _describe(command_id: int, text: str) -> str:
    labels = {
        1000: "Controller identity", 1007: "Measured diode current",
        1008: "Measured output power", 1009: "Diode-current setpoint",
        1010: "Q-switch frequency", 1011: "Q-switch pulse width",
        1012: "Q-switch source", 1013: "Empower status byte",
        1014: "Empower fault words", 1015: "Amplifier/head status byte",
        1019: "Timing/delay generator status", 1021: "High-voltage state",
        1029: "Temperature-controller health status", 1030: "Crystal temperature",
        1031: "Humidity", 1032: "Temperature setpoint",
        1039: "TDG extended status", 1042: "Measured HV channel 1 voltage",
        1043: "Measured HV channel 2 voltage", 1055: "Measured HV channel 1 current",
        1056: "Measured HV channel 2 current", 1065: "Measured oscillator frequency",
        1084: "TEC temperature", 1085: "Overall controller status",
        1089: "Subsystem communication status",
    }
    return labels.get(command_id, text)


COMMANDS: Final[dict[int, CommandSpec]] = {
    **{i: CommandSpec(i, text, Risk.READ, _describe(i, text)) for i, text in _QUERIES.items()},
    **{i: CommandSpec(i, text, risk, _describe(i, text)) for i, (text, risk) in _WRITES.items()},
}

INITIAL_QUERY_IDS: Final[tuple[int, ...]] = (
    1000, 1069, 1068, 1087, 1033, 1038,
    1037, 1032, 1057, 1044,
    1034, 1060,
    1086, 1036, 1045, 1046, 1047, 1048, 1049, 1040, 1041,
    1024, 1025, 1052, 1053, 1054, 1067, 1051, 1080,
    1035, 1009, 1010, 1011, 1012, 1071, 1072, 1073, 1074, 1075,
    1076, 2047, 1078, 1062,
)

FAST_POLL_IDS: Final[tuple[int, ...]] = (1015, 1019, 1013, 1028, 1007, 1008, 1029, 1030, 1065, 1031, 1021, 1077, 1084, 1085)
# Crystal temperature, humidity, LBO temperature and TEC temperature.
# Status/fault queries retain their existing polling cadence.
ENVIRONMENT_POLL_IDS: Final[tuple[int, ...]] = (1030, 1031, 1077, 1084)
HV_POLL_IDS: Final[tuple[int, ...]] = (1056, 1055, 1042, 1043)
FAULT_QUERY_IDS: Final[tuple[int, ...]] = (1089, 1088, 1014, 1066, 1057)


def get_command(command_id: int) -> CommandSpec:
    try:
        return COMMANDS[command_id]
    except KeyError as exc:
        raise ValueError(f"Unknown command id: {command_id}") from exc


def format_command(command_id: int, argument: object | None = None) -> str:
    """Create one legacy command line, without its trailing LF."""
    spec = get_command(command_id)
    line = f"[{spec.id}]{spec.text}"
    if argument is not None:
        rendered = str(argument)
        if any(ord(c) < 32 or ord(c) == 127 for c in rendered) or ";" in rendered:
            raise ValueError("A command argument cannot contain separators or control characters")
        rendered = rendered.strip()
        if command_id < 2000 and rendered:
            if command_id != 1026 or rendered not in {"1", "2", "3", "4", "5"}:
                raise ValueError("This query does not accept an argument")
        if rendered:
            line += f" {rendered}"
    return line


def engineering_argument(command_id: int, argument: object | None) -> object | None:
    """GUI engineering units -> wire units. Programmer console stays raw.

    Legacy _slideqswprf at 0x40AD10 divides Hz by float32 10.0.
    HV channel commands use raw kV; the GUI displays and accepts volts.
    Original _SetHVCallback1/2 format raw kV with two decimal places.
    """
    if command_id == 2003 and argument is not None:
        try:
            amps = Decimal(str(argument))
        except InvalidOperation as exc:
            raise ValueError("Diode current must be a number in A") from exc
        if not amps.is_finite() or amps < 0 or amps > 1_000_000:
            raise ValueError("Diode current must be finite, nonnegative and within the software input limit")
        wire = amps * Decimal(10)
        if wire != wire.quantize(Decimal("0.01")):
            raise ValueError("Diode current resolution is 0.001 A")
        return f"{wire:.2f}"
    if command_id in {2025, 2026} and argument is not None:
        try:
            volts = Decimal(str(argument))
        except InvalidOperation as exc:
            raise ValueError("HV voltage must be a number in V") from exc
        if not volts.is_finite() or volts < 0:
            raise ValueError("HV voltage must be finite and nonnegative")
        if volts > 1_000_000:
            raise ValueError("HV voltage exceeds the software input limit")
        return f"{volts / Decimal(1000):.2f}"
    if command_id != 2004 or argument is None:
        return argument
    try:
        hz = Decimal(str(argument))
    except InvalidOperation as exc:
        raise ValueError("Q-switch frequency must be a number in Hz") from exc
    if not hz.is_finite() or hz < 0:
        raise ValueError("Q-switch frequency must be finite and nonnegative")
    wire = hz / Decimal(10)
    if hz > 1_000_000:
        raise ValueError("Q-switch frequency exceeds the software input limit")
    if wire != wire.quantize(Decimal("0.01")):
        raise ValueError("Q-switch frequency resolution is 0.1 Hz")
    return f"{wire:.2f}"


def readback_ids(command_id: int, argument: object | None = None) -> tuple[int, ...]:
    """Queries required after a write, regardless of its ACK/timeout result."""
    if command_id == 2019:
        try:
            channel = int(str(argument).split()[0])
        except (ValueError, IndexError):
            return ()
        return (1044 + channel,) if 1 <= channel <= 5 else ()
    return {
        2000: (1001,), 2001: (1002,), 2003: (1009,), 2004: (1010,),
        2005: (1013,), 2006: (1013,), 2007: (1011,), 2008: (1012,),
        2009: (1015,), 2010: (1015,), 2011: (1015,), 2012: (1015,),
        2013: (1015,), 2014: (1060,), 2015: (1020,),
        2016: (1021,), 2017: (1021,), 2018: (1054, 1066),
        2020: (1025,), 2021: (1032,), 2022: (1028,), 2023: (1028,),
        2024: (1033,), 2025: (1040,), 2026: (1041,),
        2027: (1013, 1021, 1085), 2028: (1013, 1021, 1085),
        2029: (1044,), 2030: (1050,), 2031: (1051,), 2032: (1053,),
        2033: (1054,), 2035: (1069,), 2036: (1068,), 2037: (1070,),
        2038: (1071,), 2039: (1072,), 2040: (1073,), 2041: (1074,),
        2042: (1075,), 2043: (1076,), 2044: (1014,),
        2046: (1065,), 2047: (1078,), 2048: (1080,),
        2049: (1088,), 2050: FAULT_QUERY_IDS, 2051: (1086,),
        2052: (1066, 1039, 1089), 2053: (1087,), 2054: (1045, 1046),
        2055: FAULT_QUERY_IDS,
    }.get(command_id, ())

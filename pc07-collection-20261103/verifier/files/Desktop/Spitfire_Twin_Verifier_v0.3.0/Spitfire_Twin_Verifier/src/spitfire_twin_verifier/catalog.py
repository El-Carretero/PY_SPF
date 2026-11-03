"""Recovered Spitfire GUI 1.6.0 command catalogue.

The strings are interoperability facts recovered from the user-supplied
installer.  They are kept byte-for-byte compatible with the earlier
Spitfire Python Control 1.1.3 project.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

    @property
    def writable(self) -> bool:
        return self.id >= 2000


QUERIES: dict[int, str] = {
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

WRITES: dict[int, tuple[str, Risk]] = {
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

COMMANDS: dict[int, CommandSpec] = {
    **{cid: CommandSpec(cid, text, Risk.READ) for cid, text in QUERIES.items()},
    **{cid: CommandSpec(cid, text, risk) for cid, (text, risk) in WRITES.items()},
}

# Queries that are normally emitted continuously and may be hidden when
# comparing operator actions.
POLL_IDS = {
    1007, 1008, 1013, 1014, 1015, 1019, 1021, 1028, 1029, 1030,
    1031, 1042, 1043, 1055, 1056, 1065, 1066, 1077, 1084, 1085,
    1088, 1089,
}


def split_argument(command_id: int, command: str) -> tuple[str, str]:
    """Return recovered command base and raw argument without guessing."""
    spec = COMMANDS.get(command_id)
    if spec is None:
        return command, ""
    base = spec.text
    if command == base:
        return base, ""
    if base and command.startswith(base) and command[len(base):].startswith(" "):
        return base, command[len(base):].strip()
    return command, ""


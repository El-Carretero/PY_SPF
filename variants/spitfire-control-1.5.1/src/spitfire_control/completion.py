"""Write receipts and independently observed outcomes (never inferred from ACK).

Targets are in DeviceState engineering units. Unknown/service/physical effects
are deliberately left without a target and cannot be called confirmed.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import re

RESET_SEQUENCE = (2044, 2049, 2052, 2050)
RESET_RECHECK_SECONDS = (0.5, 1.5, 3.5, 6.0)
TERMINAL_STATUSES = frozenset({'confirmed', 'observed', 'unverified', 'rejected',
                              'mismatch', 'timeout', 'cancelled'})


@dataclass(frozen=True, slots=True)
class WriteResult:
    token: int
    command_id: int
    argument: object | None
    status: str
    detail: str = ''


@dataclass(frozen=True, slots=True)
class Target:
    value: object
    field: str = ''
    mask: int | None = None

    def matches(self, state, query_id: int) -> bool:
        actual = state.value(query_id)
        if self.field:
            delay = state.delays.get(query_id - 1044)
            actual = getattr(delay, self.field, None) if delay else None
        if self.mask is not None:
            actual = (int(actual) & self.mask) if isinstance(actual, (int, float)) else None
        def numeric(value):
            if isinstance(value, str) and not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value):
                return None
            try:
                number=float(value)
                return number if math.isfinite(number) else None
            except (TypeError, ValueError, OverflowError):
                return None
        expected_number, actual_number = numeric(self.value), numeric(actual)
        if expected_number is not None:
            return actual_number is not None and math.isclose(actual_number, expected_number, rel_tol=1e-6, abs_tol=1e-6)
        if actual is None:
            return False
        return str(actual).upper() == str(self.value).upper() if self.field else str(actual) == str(self.value)


def expected_targets(cid: int, argument: object | None) -> dict[int, Target]:
    arg = '' if argument is None else str(argument).strip()
    numeric = {2000:(1001,1), 2001:(1002,1), 2003:(1009,.1), 2004:(1010,10),
               2007:(1011,1), 2008:(1012,1), 2014:(1060,1), 2015:(1020,1),
               2020:(1025,1), 2021:(1032,1), 2024:(1033,1),
               2025:(1040,1000), 2026:(1041,1000), 2029:(1044,1),
               2032:(1053,1), 2035:(1069,1), 2036:(1068,1),
               2047:(1078,1), 2051:(1086,1), 2053:(1087,1)}
    try:
        if cid in numeric:
            q, scale = numeric[cid]; value = float(arg)*scale
            return {q:Target(value)} if math.isfinite(value) else {}
        if cid in {2030,2031} and arg.upper() in {'INT','EXT'}:
            return {1050+(cid-2030):Target(int(arg.upper()=='EXT'))}
        if cid == 2048 and arg.upper() in {'CONT','COUNT','COUNT 1'}:
            return {1080:Target({'CONT':0,'COUNT':1,'COUNT 1':2}[arg.upper()])}
        if cid in {2016,2017}:
            return {1021:Target(int(cid==2017))}
        if cid in {2005,2006}:
            return {1013:Target(int(cid==2005),mask=1)}
        if cid in {2022,2023}:
            return {1028:Target(int(cid==2022),mask=1)}
        if cid == 2019:
            ch, setting = arg.split(); ch=int(ch); setting=setting.upper()
            if not 1<=ch<=5:return {}
            field = 'switch' if setting in {'ON','OFF'} else 'bwd' if setting in {'BWD','NBWD'} else 'enable' if setting in {'ENA','NENA'} else 'value'
            value = float(setting) if field=='value' else setting.lower() if field=='switch' else setting
            return {1044+ch:Target(value,field=field)}
        if 2037<=cid<=2043 and arg:
            return {1070+cid-2037:Target(arg)}
    except (ValueError,OverflowError):
        pass
    return {}


def permits_empty_receipt(cid: int, argument: object | None) -> bool:
    # A framed, matching-ID empty receipt is distinct from receiving no packet.
    # A target must subsequently match; raw/unmodelled writes are not exempted.
    return cid in RESET_SEQUENCE or bool(expected_targets(cid,argument))

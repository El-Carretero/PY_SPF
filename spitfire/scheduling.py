"""FIFO ordering and connection timing recovered from the original native code.

Sources: _dothewaltz 0x407848; _push_initial_updates 0x407906;
_push_usual_auto_updates 0x407bd5; _check_problem_status 0x406d4f.
Clock is injected for deterministic testing; this module performs no network I/O.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Callable
import time

from .protocol import format_message

INITIAL_PREFIX = (1069, 1068, 1087, 1033, 1038)
INITIAL_ECU = (1037, 1032, 1057)
INITIAL_MIL = (1034, 1060)
INITIAL_TDG = (1086, 1036, 1045, 1046, 1047, 1048, 1049, 1040, 1041,
               1024, 1025, 1052, 1053, 1054, 1067, 1051, 1053, 1080)
INITIAL_EMP = (1035, 1009, 1010, 1011, 1012, 1053, 1071, 1072, 1073,
               1074, 1075, 1076, 2047, 1078)
POLL_VALUES = (1015, 1019, 1013, 1028, 1007, 1008, 1029, 1030, 1065,
               1031, 1021, 1077, 1084, 1085)
SERVICE_POLL_VALUES = (1056, 1055, 1042, 1043)


@dataclass(frozen=True)
class Request:
    tag: int
    parameter: str = ""

    @property
    def message(self) -> str:
        return format_message(self.tag, self.parameter)


class Scheduler:
    """Original priority FIFO pair with at most one outstanding request.

    The binary copied 30 bytes per FIFO entry regardless of string length.
    This port retains complete strings; normal original messages fit that limit.
    Undefined original memory reads for overlong entries are not reproduced.
    """
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.inside: deque[Request] = deque()
        self.outside: deque[Request] = deque()
        self.balance = 0
        self.last_received = clock()
        self.initializing = True
        self.hold = False
        self.access_level = 0
        self.reset_channels_pending = False
        self.pardon_first_time = True
        self.last_sent: Request | None = None
        self.current_parameter = ""

    def clear(self) -> None:
        self.inside.clear()
        self.outside.clear()
        self.balance = 0
        self.last_sent = None

    def push(self, tag: int, parameter: str = "", *, inside: bool = True) -> Request:
        request = Request(tag, parameter)
        if tag >= 2000 or tag == 1026:
            self.current_parameter = parameter
        (self.inside if inside else self.outside).append(request)
        return request

    enqueue = push

    def queue_initial(self) -> None:
        for tag in INITIAL_PREFIX + INITIAL_ECU + INITIAL_MIL + INITIAL_TDG + INITIAL_EMP + (1062,):
            # post2 defaults the board's original Empower opt-out to ON at
            # each successful connection. Keep the original readback directly
            # after the write; only that reply updates the displayed setting.
            # There is deliberately no HV readback prerequisite.
            if tag == 1068:
                self.push(2036, " 1")
            self.push(tag, " 1" if tag == 2047 else "")
        self.initializing = True

    def queue_subsystem_initial(self, subsystem: str) -> None:
        sequences = {"ecu": INITIAL_ECU, "mil": INITIAL_MIL,
                     "tdg": INITIAL_TDG, "emp": INITIAL_EMP}
        for tag in sequences[subsystem.lower()]:
            self.push(tag, " 1" if tag == 2047 else "")

    def queue_poll(self) -> None:
        if self.reset_channels_pending:
            self.push(2054, self.current_parameter, inside=False)
            self.reset_channels_pending = False
        values = (SERVICE_POLL_VALUES if self.access_level > 0 else ()) + POLL_VALUES
        self.push(1039, inside=False)
        for tag in values:
            self.push(tag, inside=False)
            self.push(1039, inside=False)

    def next_request(self, *, auto_poll: bool = True) -> Request | None:
        if self.hold or self.balance:
            return None
        if not self.inside and not self.outside and auto_poll:
            self.queue_poll()
        fifo = self.inside if self.inside else self.outside
        if not fifo:
            return None
        request = fifo.popleft()
        self.balance += 1
        self.last_sent = request
        return request

    def acknowledge(self, tag: int) -> None:
        # The startup identity request is sent without incrementing balance.
        if tag != 1000:
            self.balance = max(0, self.balance - 1)
        self.last_received = self.clock()

    @property
    def inactivity(self) -> float:
        return max(0.0, self.clock() - self.last_received)

    def connection_action(self) -> str | None:
        """Original strict thresholds: >30 s report/reconnect, >10 s reopen."""
        age = self.inactivity
        if age > 30:
            return "reconnect"
        if age > 10:
            return "reopen"
        return None


@dataclass
class StartupAttempts:
    """State for the original three identity queries, each waiting up to 3 s.

    _openandconfigureport tries all three queries even after the first response.
    It queues initial state only when the third attempt received any response.
    """
    attempts: int = 0
    deadline: float = 0.0
    received: bool = False
    complete: bool = False

    def begin(self, now: float) -> Request:
        if self.complete or self.attempts >= 3:
            raise RuntimeError("startup attempts are complete")
        self.attempts += 1
        self.deadline = now + 3.0
        self.received = False
        return Request(1000)

    def mark_received(self) -> None:
        self.received = True

    def should_advance(self, now: float) -> bool:
        return self.received or now >= self.deadline

    def finish_attempt(self) -> bool:
        self.complete = self.attempts >= 3
        return self.complete and self.received

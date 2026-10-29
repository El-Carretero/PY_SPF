"""Empower-independent request queues, polling and connection timing.

The original inside/outside FIFO structure is retained. Initialization and
polling are read-only, and OFF requests have an additional urgent queue.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Callable
import time

from .protocol import format_message
from .external_policy import POLL_READBACKS, SERVICE_READBACKS, is_stop_request, validate_request

INITIAL_PREFIX = (1069, 1068, 1087, 1033, 1038)
INITIAL_ECU = (1037, 1032, 1057)
INITIAL_MIL = (1034, 1060)
INITIAL_TDG = (1086, 1036, 1045, 1046, 1047, 1048, 1049, 1040, 1041,
               1024, 1025, 1052, 1053, 1054, 1050, 1051, 1080,
               1019, 1015, 1028, 1039, 1066, 1088, 1089, 1021,
               1042, 1043, 1065, 1044)
POLL_VALUES = POLL_READBACKS
SERVICE_POLL_VALUES = SERVICE_READBACKS


@dataclass(frozen=True)
class Request:
    tag: int
    parameter: str = ""

    @property
    def message(self) -> str:
        validate_request(self.tag, self.parameter)
        return format_message(self.tag, self.parameter)


class Scheduler:
    """Readback FIFO pair plus urgent OFFs; at most one outstanding request."""
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.inside: deque[Request] = deque()
        self.outside: deque[Request] = deque()
        self.urgent: deque[Request] = deque()
        self.balance = 0
        self.last_received = clock()
        self.initializing = True
        self.hold = False
        self.access_level = 0
        self.reset_channels_pending = False
        self.pardon_first_time = True
        self.last_sent: Request | None = None
        self.last_sent_at: float | None = None
        self.current_parameter = ""

    def clear(self) -> None:
        self.inside.clear()
        self.outside.clear()
        self.urgent.clear()
        self.balance = 0
        self.last_sent = None
        self.last_sent_at = None

    def push(self, tag: int, parameter: str = "", *, inside: bool = True) -> Request:
        validate_request(tag, parameter)
        request = Request(tag, parameter)
        if tag >= 2000 or tag == 1026:
            self.current_parameter = parameter
        (self.inside if inside else self.outside).append(request)
        return request

    enqueue = push

    def cancel_pending_writes(self) -> None:
        """Discard unsent writes while preserving queries and OFF requests."""
        for queue in (self.inside, self.outside, self.urgent):
            retained = [r for r in queue if r.tag < 2000 or is_stop_request(r.tag, r.parameter)]
            queue.clear()
            queue.extend(retained)

    def push_urgent(self, tag: int, parameter: str = "") -> Request:
        validate_request(tag, parameter)
        if not is_stop_request(tag, parameter):
            raise ValueError("Only OFF/STOP requests can use the urgent queue")
        self.cancel_pending_writes()
        key = (tag, " ".join(parameter.upper().split()))
        if self.last_sent is not None and self.balance and (self.last_sent.tag, " ".join(self.last_sent.parameter.upper().split())) == key:
            return self.last_sent
        for request in self.urgent:
            if (request.tag, " ".join(request.parameter.upper().split())) == key:
                return request
        # Move an existing ordinary OFF to urgent rather than duplicate it.
        for queue in (self.inside, self.outside):
            retained = [r for r in queue if (r.tag, " ".join(r.parameter.upper().split())) != key]
            queue.clear()
            queue.extend(retained)
        request = Request(tag, parameter)
        self.urgent.append(request)
        return request

    def queue_stop(self, channels=(1, 2), *, include_hv: bool = False) -> tuple[Request, ...]:
        channels = tuple(channels)
        if any(type(channel) is not int or channel not in range(1, 6) for channel in channels):
            raise ValueError("Stop channels must be integers from 1..5")
        requests = [self.push_urgent(2019, f" {channel} OFF") for channel in channels]
        if include_hv:
            requests.append(self.push_urgent(2016))
        return tuple(requests)

    def abandon_inflight(self) -> Request | None:
        """Release a timed-out request without replaying any write."""
        request = self.last_sent
        self.balance = 0
        self.last_sent = None
        self.last_sent_at = None
        return request

    def queue_initial(self) -> None:
        for tag in INITIAL_PREFIX + INITIAL_ECU + INITIAL_MIL + INITIAL_TDG + (1062,):
            self.push(tag)
        self.initializing = True

    def queue_subsystem_initial(self, subsystem: str) -> None:
        sequences = {"ecu": INITIAL_ECU, "mil": INITIAL_MIL,
                     "tdg": INITIAL_TDG, "emp": ()}
        for tag in sequences[subsystem.lower()]:
            self.push(tag)

    def queue_poll(self) -> None:
        # Legacy STATUS? side effects must never introduce automatic writes.
        self.reset_channels_pending = False
        values = (SERVICE_POLL_VALUES if self.access_level > 0 else ()) + POLL_VALUES
        for tag in values:
            self.push(tag, inside=False)

    def next_request(self, *, auto_poll: bool = True) -> Request | None:
        if self.hold or self.balance:
            return None
        if not self.urgent and not self.inside and not self.outside and auto_poll:
            self.queue_poll()
        fifo = self.urgent if self.urgent else self.inside if self.inside else self.outside
        if not fifo:
            return None
        request = fifo.popleft()
        validate_request(request.tag, request.parameter)
        self.balance += 1
        self.last_sent = request
        self.last_sent_at = self.clock()
        return request

    def acknowledge(self, tag: int) -> bool:
        # Startup identity is sent without a normal outstanding request.
        if self.balance:
            if self.last_sent is None or tag != self.last_sent.tag:
                return False
            self.abandon_inflight()
        elif tag != 1000:
            return False
        self.last_received = self.clock()
        return True

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

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
FAULT_QUERY_TAGS = (1089, 1088, 1014, 1066, 1057) * 2
FAULT_RESET_TAGS = (2044, 2049, 2052, 2050) + FAULT_QUERY_TAGS
BWD_RESET_TAGS = (2018, 1066)


@dataclass(frozen=True)
class Request:
    tag: int
    parameter: str = ""
    request_id: int | None = field(default=None, compare=False)
    queued_monotonic: float | None = field(default=None, compare=False)
    origin: str = field(default="unspecified", compare=False)
    batch_id: str | None = field(default=None, compare=False)

    @property
    def message(self) -> str:
        return format_message(self.tag, self.parameter)


@dataclass
class RequestBatch:
    kind: str
    remaining: set[int]
    refresh_requests: set[int]
    write_generation: int
    timed_out: bool = False
    canceled: bool = False


class Scheduler:
    """Original priority FIFO pair with at most one outstanding request.

    The binary copied 30 bytes per FIFO entry regardless of string length.
    This port retains complete strings; normal original messages fit that limit.
    Undefined original memory reads for overlong entries are not reproduced.
    """
    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 read_only: bool = False, on_event=None) -> None:
        self.clock = clock
        self.read_only = read_only
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
        self.default_optout_write: Request | None = None
        self.on_event = on_event
        self._next_request_id = 0
        self._next_batch_id = 0
        self._write_generation = 0
        self._batches: dict[str, RequestBatch] = {}
        self.suppressed_reset_batches = 0
        self.suppressed_fault_batches = 0
        self.suppressed_bwd_reset_batches = 0

    def _event(self, event, request=None, **fields):
        if self.on_event is None:
            return
        payload = {"event": event, "queue_inside": len(self.inside),
                   "queue_outside": len(self.outside)}
        if request is not None:
            payload.update(request_id=request.request_id, tag=request.tag,
                           queued_monotonic=request.queued_monotonic,
                           origin=request.origin, batch_id=request.batch_id)
        payload.update(fields)
        self.on_event(payload)

    def clear(self, *, reason="cleared") -> None:
        for batch_id, batch in self._batches.items():
            self._event("batch_canceled", batch_id=batch_id, batch_kind=batch.kind,
                        reason=reason, remaining=len(batch.remaining))
        self.inside.clear()
        self.outside.clear()
        self.balance = 0
        self.last_sent = None
        self.default_optout_write = None
        self.reset_channels_pending = False
        self._batches.clear()

    def push(self, tag: int, parameter: str = "", *, inside: bool = True,
             origin: str = "unspecified", batch_id: str | None = None) -> Request:
        self._next_request_id += 1
        request = Request(tag, parameter, self._next_request_id, self.clock(), origin, batch_id)
        if tag >= 2000 or tag == 1026:
            self.current_parameter = parameter
        if tag >= 2000:
            self._write_generation += 1
        (self.inside if inside else self.outside).append(request)
        self._event("queued", request)
        return request

    enqueue = push

    def queue_batch(self, kind: str, entries, *, origin: str) -> list[Request] | None:
        """Coalesce complete operations, preserving every request in each pass.

        A fault refresh can share an existing reset's readback only when no
        write was queued since that readback. A query before a later write can
        never satisfy a refresh requested after that write.
        """
        if kind not in ("fault_reset", "fault_update", "bwd_reset"):
            raise ValueError(f"Unknown request batch {kind}")
        if kind == "fault_update":
            existing = next(((batch_id, batch) for batch_id, batch in self._batches.items()
                             if batch.refresh_requests
                             and batch.write_generation == self._write_generation), None)
        else:
            existing = next(((batch_id, batch) for batch_id, batch in self._batches.items()
                             if batch.kind == kind), None)
        if existing is not None:
            key = {"fault_reset": "suppressed_reset_batches", "fault_update": "suppressed_fault_batches",
                   "bwd_reset": "suppressed_bwd_reset_batches"}[kind]
            setattr(self, key, getattr(self, key) + 1)
            self._event("coalesced", batch_id=existing[0], batch_kind=kind, origin=origin,
                        suppressed=getattr(self, key))
            return None
        self._next_batch_id += 1
        batch_id = f"{kind}:{self._next_batch_id}"
        entries = [(tag, parameter) for tag, parameter in entries]
        requests = []
        try:
            for tag, parameter in entries:
                requests.append(self.push(tag, parameter, origin=origin, batch_id=batch_id))
        except Exception:
            # A partially inserted Reset must not leave orphaned members or a
            # lock that suppresses the next complete operation.
            self.remove_queued(lambda request: request.batch_id == batch_id)
            raise
        if not requests:
            return requests
        refresh_requests = ({request.request_id for request in requests if request.tag < 2000}
                            if kind in ("fault_reset", "fault_update") else set())
        self._batches[batch_id] = RequestBatch(kind, {request.request_id for request in requests},
                                              refresh_requests, self._write_generation)
        self._event("batch_queued", batch_id=batch_id, batch_kind=kind, origin=origin,
                    request_count=len(requests))
        return requests

    def record_sent(self, request: Request, *, retry=False, sent_at=None) -> None:
        now = self.clock() if sent_at is None else sent_at
        self._event("sent", request, retry=retry,
                    wait_seconds=None if request.queued_monotonic is None else
                    max(0, now-request.queued_monotonic))

    def _retire(self, request: Request, outcome: str) -> None:
        batch = self._batches.get(request.batch_id)
        if batch is not None:
            batch.remaining.discard(request.request_id)
            batch.refresh_requests.discard(request.request_id)
            batch.timed_out |= outcome == "timeout"
            batch.canceled |= outcome == "canceled"
        self._event(outcome, request)
        if batch is not None and not batch.remaining:
            del self._batches[request.batch_id]
            result = "canceled" if batch.canceled else "timeout" if batch.timed_out else "completed"
            self._event("batch_completed", request, batch_kind=batch.kind, result=result)

    def finish_current(self, outcome="completed") -> None:
        """Retire one in-flight member, including exhausted retries or blocks."""
        if self.balance and self.last_sent is not None:
            self.balance = 0
            self._retire(self.last_sent, outcome)

    def remove_queued(self, predicate) -> int:
        removed = []
        for queue in (self.inside, self.outside):
            retained = []
            for request in queue:
                (removed if predicate(request) else retained).append(request)
            queue.clear()
            queue.extend(retained)
        for request in removed:
            self._retire(request, "canceled")
        return len(removed)

    def queue_initial(self) -> None:
        for tag in INITIAL_PREFIX + INITIAL_ECU + INITIAL_MIL + INITIAL_TDG + INITIAL_EMP + (1062,):
            # post2 defaults the board's original Empower opt-out to ON at
            # each successful connection. Keep the original readback directly
            # after the write; only that reply updates the displayed setting.
            # There is deliberately no HV readback prerequisite.
            if tag == 1068 and not self.read_only:
                self.default_optout_write = self.push(2036, " 1", origin="initialization")
            if self.read_only and tag >= 2000:
                continue
            self.push(tag, " 1" if tag == 2047 else "", origin="initialization")
        self.initializing = True

    def queue_subsystem_initial(self, subsystem: str) -> None:
        sequences = {"ecu": INITIAL_ECU, "mil": INITIAL_MIL,
                     "tdg": INITIAL_TDG, "emp": INITIAL_EMP}
        for tag in sequences[subsystem.lower()]:
            if self.read_only and tag >= 2000:
                continue
            self.push(tag, " 1" if tag == 2047 else "", origin=f"{subsystem}_initialization")

    def queue_poll(self) -> None:
        if self.reset_channels_pending:
            if not self.read_only:
                self.push(2054, self.current_parameter, inside=False, origin="status_reset")
            self.reset_channels_pending = False
        values = (SERVICE_POLL_VALUES if self.access_level > 0 else ()) + POLL_VALUES
        self.push(1039, inside=False, origin="poll")
        for tag in values:
            self.push(tag, inside=False, origin="poll")
            self.push(1039, inside=False, origin="poll")

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

    def acknowledge(self, tag: int) -> bool:
        """Only the outstanding tag can complete a request.

        Tags identify query types, not unique transactions: a delayed reply to
        a repeated *same* tag cannot be distinguished by this wire protocol.
        """
        if not self.balance or self.last_sent is None or self.last_sent.tag != tag:
            return False
        self.finish_current()
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
        return Request(1000, queued_monotonic=now, origin="startup")

    def mark_received(self) -> None:
        self.received = True

    def should_advance(self, now: float) -> bool:
        return self.received or now >= self.deadline

    def finish_attempt(self) -> bool:
        self.complete = self.attempts >= 3
        return self.complete and self.received

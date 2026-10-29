"""Asynchronous scheduler with send-time authorization and readback monitoring."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import csv
import math
import heapq
import json
from pathlib import Path
import queue
import threading
import time
from typing import Literal

from .commands import (ENVIRONMENT_POLL_IDS, FAST_POLL_IDS, FAULT_QUERY_IDS, HV_POLL_IDS,
                       INITIAL_QUERY_IDS, format_command, get_command, readback_ids)
from .profiles import (EXTERNAL_REQUIRED_READS, filter_queries, is_stop_command,
                       requires_external_enable_check, validate_profile_command, validate_pump_mode)
from .protocol import Reply, encode_datagram
from .state import DeviceState, is_error_reply
from .timing import validate_timing_expectations
from .transport import BaseTransport, TransportError, CommandCancelled
from .completion import (WriteResult, Target, expected_targets, permits_empty_receipt,
                         RESET_SEQUENCE, RESET_RECHECK_SECONDS, TERMINAL_STATUSES)

STOP_COMMAND_IDS = frozenset({2006, 2013, 2016, 2023, 2028})
HEARTBEAT_QUERY_ID = 1000  # Known read-only *idn? controller query.
HEARTBEAT_INTERVAL_SECONDS = 1.0
# These read-only facts remain monitored when optional telemetry is disabled.
OUTPUT_MONITOR_QUERY_IDS = (1021, 1042, 1043, 1039, 1045, 1046)

@dataclass(frozen=True, slots=True)
class PCOutputStatus:
    action: str = ""
    status: str = "idle"
    detail: str = "No PC output command requested"
    tokens: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ControllerEvent:
    kind: Literal["state", "log", "error", "connection", "command", "output"]
    message: str = ""
    state: DeviceState | None = None
    reply: Reply | None = None
    result: WriteResult | None = None
    output: PCOutputStatus | None = None

@dataclass(frozen=True, slots=True)
class PendingCommand:
    command_id: int
    argument: object | None
    origin: str
    generation: int = 0
    token: int = 0
    batch: str = ""


@dataclass(slots=True)
class WriteWatch:
    request: PendingCommand
    pending: set[int]
    targets: dict[int, Target]
    deadline: float
    not_before: float = 0.0
    observed: dict[int, object] = field(default_factory=dict)

class AuditLog:
    def __init__(self, directory: str = ""):
        base = Path(directory).expanduser() if directory else Path.cwd() / "logs"
        self.path = base / f"spitfire_audit_{datetime.now():%Y%m%d}.csv"
        self._lock = threading.Lock()

    def write(self, direction: str, command_id: int, text: str, result: str) -> None:
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                new = not self.path.exists()
                with self.path.open("a", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    if new:
                        writer.writerow(("utc_time", "direction", "command_id", "text", "result"))
                    writer.writerow((datetime.now(timezone.utc).isoformat(), direction, command_id, text, result))
        except OSError:
            pass  # An unavailable audit file must not block OFF.

class LaserController:
    def __init__(self, transport: BaseTransport, *, timeout: float = 2.0,
                 poll_interval: float = 1.0, auto_poll: bool = True,
                 monitor_hv: bool = False, log_directory: str = "",
                 pump_mode: str = "empower", external_seed_mhz: float = 80.0,
                 external_seed_tolerance_mhz: float = 1.0, external_pump_hz: float = 10.0):
        validate_timing_expectations(external_seed_mhz, external_seed_tolerance_mhz, external_pump_hz)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be finite and positive")
        if not math.isfinite(poll_interval) or poll_interval < 0.2:
            raise ValueError("Poll interval must be finite and at least 0.2 seconds")
        self._pump_mode = validate_pump_mode(pump_mode)
        self.transport = transport
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.auto_poll = auto_poll
        self.monitor_hv = monitor_hv
        self.events: queue.Queue[ControllerEvent] = queue.Queue()
        self._commands: deque[PendingCommand] = deque()
        self._urgent: deque[PendingCommand] = deque()
        self._condition = threading.Condition(threading.RLock())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._generation = 0
        self._state = DeviceState(transport_name=transport.name, pump_mode=pump_mode,
                                 external_seed_mhz=external_seed_mhz,
                                 external_seed_tolerance_mhz=external_seed_tolerance_mhz,
                                 external_pump_hz=external_pump_hz,
                                 stale_after_seconds=max(5.0, 3 * poll_interval, 2 * timeout))
        self._audit = AuditLog(log_directory)
        self._poll_index = 0
        self._next_poll_at = 0.0
        self._poll_configuration: tuple[float, bool] | None = None
        self._last_read_monotonic: float | None = None
        self._token = 0
        self._results: dict[int, WriteResult] = {}
        self._watch: dict[int, WriteWatch] = {}
        self._delayed: list[tuple[float, int, int]] = []
        self._readback_serial = 0
        self._audit_pending = queue.SimpleQueue()
        self._pc_output = PCOutputStatus()
        self._pc_run_steps: deque[str] = deque()
        self._pc_abort_reason = ""
        self._reset_snapshot_token: int | None = None

    def _record_audit(self, *row) -> None:
        # Submission/send guards must not hold the controller lock during disk I/O.
        self._audit_pending.put(row)

    def _flush_audit(self) -> None:
        while True:
            try:
                row = self._audit_pending.get_nowait()
            except queue.Empty:
                return
            self._audit.write(*row)

    @property
    def command_results(self) -> tuple[WriteResult, ...]:
        with self._condition:
            return tuple(self._results.values())

    def _result(self, request: PendingCommand, status: str, detail: str = "") -> None:
        if not request.token or request.command_id < 2000:
            return
        result = WriteResult(request.token, request.command_id, request.argument, status, detail)
        self._results[request.token] = result
        self.events.put(ControllerEvent("command", f"#{request.token} [{request.command_id}] {status}: {detail}", result=result))
        self._record_audit(status.upper(), request.command_id,
                          format_command(request.command_id, request.argument), f"#{request.token} {detail}")
        if status in TERMINAL_STATUSES:
            self._watch.pop(request.token, None)
        if request.token == self._reset_snapshot_token and status in TERMINAL_STATUSES:
            self._record_audit("RESET_AFTER", request.command_id, self._output_snapshot(), status + ": " + detail)
            self._reset_snapshot_token = None
        # Keep pending requests plus a bounded history. The CSV retains all entries.
        completed = [k for k,v in self._results.items() if v.status in TERMINAL_STATUSES]
        for key in completed[:-256]:
            self._results.pop(key, None)

    def _observe(self, reply: Reply, valid: bool) -> None:
        now = time.monotonic()
        for token, watch in list(self._watch.items()):
            if token not in self._watch or reply.command_id not in watch.pending:
                continue
            if now < watch.not_before:
                continue
            if not valid:
                self._result(watch.request, "unverified", f"Readback [{reply.command_id}] unavailable; write outcome unknown")
                self._cancel_pending_writes_locked("A write readback is unavailable")
                continue
            watch.observed[reply.command_id] = self._state.value(reply.command_id)
            target = watch.targets.get(reply.command_id)
            if target is not None and not target.matches(self._state, reply.command_id):
                detail = f"[{reply.command_id}] expected {target.value!r}; observed {self._state.value(reply.command_id)!r}"
                self._record_audit("READBACK_MISMATCH", watch.request.command_id,
                                  format_command(watch.request.command_id, watch.request.argument), detail)
                self._result(watch.request, "mismatch", detail)
                self._state.last_error = "Write readback mismatch: " + detail
                self._cancel_pending_writes_locked(self._state.last_error)
                continue
            watch.pending.discard(reply.command_id)
            if not watch.pending:
                status = "confirmed" if watch.targets else "observed"
                detail = ("Target readback matched" if watch.targets else
                          "State read back; this does not assert fault clearance or physical operation")
                self._result(watch.request, status, detail + f"; {watch.observed}")

    def _expire_watches(self, now: float) -> None:
        expired = [watch for watch in self._watch.values() if now >= watch.deadline]
        for watch in expired:
            self._result(watch.request, "unverified", "Readback confirmation deadline expired")
        if expired:
            self._cancel_pending_writes_locked("Readback confirmation deadline expired")

    def clear_faults(self) -> tuple[int, ...]:
        """Explicit operator action, never called by connect/reconnect/polling."""
        with self._condition:
            if any(r.command_id == 2050 and r.status not in TERMINAL_STATUSES for r in self._results.values()):
                raise ValueError("Fault reset is already pending; wait for its readback result")
            tokens = self.submit_batch([(cid, None) for cid in RESET_SEQUENCE], origin="Clear Faults", batch="reset")
            self._record_audit("RESET_BEFORE", 2050, self._output_snapshot(), "Cached readbacks; timestamps/freshness included")
            self._reset_snapshot_token = tokens[-1]
            return tokens

    def _output_snapshot(self) -> str:
        return json.dumps({str(cid): {
            "raw": self._state.raw_values.get(cid),
            "fresh": self._state.is_fresh(cid),
            "updated_at": self._state.updated_at[cid].isoformat() if cid in self._state.updated_at else None,
        } for cid in OUTPUT_MONITOR_QUERY_IDS + (1066,)}, ensure_ascii=False)

    @property
    def pc_output_status(self) -> PCOutputStatus:
        with self._condition:
            return self._pc_output

    def _set_pc_output(self, action: str, status: str, detail: str, tokens=()) -> None:
        self._pc_output = PCOutputStatus(action, status, detail, tuple(tokens))
        message = f"PC1/PC2 {action} {status}: {detail}"
        self.events.put(ControllerEvent("output", message, state=self._state.copy(), output=self._pc_output))
        self._record_audit("PC_OUTPUT", 2019, message, str(tuple(tokens)))

    def _pc_run_reason(self) -> str:
        reason = self._state.external_enable_reason()
        if reason:
            return reason
        if self._state.key_interlock is not False:
            return "RUN requires a fresh, clear current Key interlock readback."
        if self._state.high_voltage is not True:
            return "RUN requires a fresh device HV ON readback; RUN does not turn HV on."
        for cid in (1042, 1043):
            value = self._state.value(cid)
            if (not self._state.is_fresh(cid) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0):
                return "RUN requires fresh, positive measured HV1 and HV2 readings."
        return ""

    def run_pc_outputs(self) -> None:
        """External PC pair only. No pump, HV-enable, reset, or auto-resume command."""
        with self._condition:
            if self.pump_mode != "external":
                raise ValueError("PC-pair RUN is available in External pump mode only")
            if self._pc_output.status in {"pending", "stopping"}:
                raise ValueError("PC output operation is already pending")
            if any(r.status not in TERMINAL_STATUSES for r in self._results.values()):
                raise ValueError("Wait for pending writes to complete before RUN")
            reason = self._pc_run_reason()
            if reason:
                raise PermissionError(reason)
            if any(self._state.pc_output(ch) != "OFF" for ch in (1, 2)):
                raise PermissionError("RUN requires both PC channels confirmed OFF; request STOP first")
            self._pc_abort_reason = ""
            # Explicit application sequence: extraction CH2 before injection CH1.
            # Original GUI has separate channel buttons; no combined order is inferred.
            self._pc_run_steps = deque(("1 ON",))
            token = self.submit(2019, "2 ON", "External RUN", batch="pc-run")
            self._set_pc_output("RUN", "pending", "Waiting for PC2 ON readback", (token,))

    def _queue_pc_off(self, *, failed_run: bool, reason: str) -> None:
        self._pc_run_steps.clear()
        # Clear active RUN before OFF cancels outstanding writes.
        self._set_pc_output("RUN" if failed_run else "STOP", "stopping", reason)
        self._pc_abort_reason = ""
        tokens = tuple(self.submit(2019, f"{ch} OFF", "RUN cleanup" if failed_run else "External STOP")
                       for ch in (1, 2))
        self._set_pc_output("RUN" if failed_run else "STOP", "stopping", reason, tokens)

    def stop_pc_outputs(self) -> None:
        """Both OFF requests are urgent, independent, and need no fresh readbacks."""
        with self._condition:
            if self.pump_mode != "external":
                raise ValueError("PC-pair STOP is available in External pump mode only")
            if self._stop.is_set():
                raise PermissionError("Controller is stopped; reconnect before STOP")
            if self._pc_output.status == "stopping":
                return  # Coalesce repeated clicks; never postpone the existing OFFs.
            self._queue_pc_off(failed_run=False, reason="Both PC OFF requests queued; confirmation pending")

    def _advance_pc_output_locked(self) -> None:
        operation = self._pc_output
        if operation.status not in {"pending", "stopping"}:
            return
        if self._stop.is_set():
            self._pc_run_steps.clear()
            self._set_pc_output(operation.action, "unverified", "Disconnected; PC output state is unknown", operation.tokens)
            return
        results = [self._results.get(token) for token in operation.tokens]
        if operation.status == "pending":
            failure = self._pc_abort_reason
            last = results[-1] if results else None
            if last and last.status in TERMINAL_STATUSES and last.status != "confirmed":
                failure = failure or last.detail or last.status
            if failure:
                self._queue_pc_off(failed_run=True, reason="RUN aborted: " + failure)
            elif last and last.status == "confirmed":
                if self._pc_run_steps:
                    try:
                        argument = self._pc_run_steps.popleft()
                        reason = self._pc_run_reason()
                        if reason:
                            raise PermissionError(reason)
                        token = self.submit(2019, argument, "External RUN", batch="pc-run")
                        self._set_pc_output("RUN", "pending", "PC2 ON confirmed; waiting for PC1 ON readback", operation.tokens + (token,))
                    except (ValueError, PermissionError) as exc:
                        self._queue_pc_off(failed_run=True, reason="RUN aborted: " + str(exc))
                elif self._pc_run_reason():
                    self._queue_pc_off(failed_run=True, reason="RUN aborted: " + self._pc_run_reason())
                elif all(self._state.pc_output(ch) == "ON" for ch in (1, 2)):
                    self._set_pc_output("RUN", "confirmed", "PC1 and PC2 ON readbacks confirmed; beam output is not measured", operation.tokens)
                else:
                    self._queue_pc_off(failed_run=True, reason="RUN aborted: channel readbacks no longer confirm both ON")
        elif results and all(r is not None and r.status in TERMINAL_STATUSES for r in results):
            off = all(r.status == "confirmed" for r in results) and all(self._state.pc_output(ch) == "OFF" for ch in (1, 2))
            status = ("failed" if operation.action == "RUN" else "confirmed") if off else "unverified"
            detail = operation.detail + ("; both PC OFF readbacks confirmed" if off else "; PC OFF not fully confirmed; check equipment")
            self._set_pc_output(operation.action, status, detail, operation.tokens)

    def submit_batch(self, commands, *, origin: str = "GUI", batch: str = "settings") -> tuple[int, ...]:
        commands = tuple(commands)
        if not commands:
            raise ValueError("An empty command batch is not allowed")
        with self._condition:
            # Preflight the complete group before queuing any member.
            for cid, argument in commands:
                if cid < 2000 or cid in STOP_COMMAND_IDS or is_stop_command(cid, argument):
                    raise ValueError("Batches accept non-stop writes only; OFF remains urgent")
                self._validate_submission(cid, argument)
            return tuple(self.submit(cid, argument, origin, batch=batch) for cid, argument in commands)

    @property
    def pump_mode(self) -> str:
        return self._pump_mode

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def state(self) -> DeviceState:
        with self._condition:
            return self._state.copy()

    def start(self) -> None:
        with self._condition:
            if self.running:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="spitfire-controller", daemon=True)
            self._thread.start()

    def _cancel_pending_writes_locked(self, reason: str) -> None:
        self.events.put(ControllerEvent("log", "Pending writes cancelled: " + reason))
        if self._pc_output.status == "pending":
            self._pc_abort_reason = reason
        self._generation += 1
        # Already dequeued commands are also invalidated by their generation.
        kept = deque()
        for request in self._commands:
            if request.command_id < 2000:
                kept.append(request)
            else:
                self._record_audit("CANCEL", request.command_id,
                                  format_command(request.command_id, request.argument), reason)
                self._result(request, "cancelled", reason)
        self._commands = kept

    def stop(self) -> None:
        with self._condition:
            self._stop.set()
            self._advance_pc_output_locked()
            self._cancel_pending_writes_locked("Controller stopped.")
            self._commands.clear()
            self._delayed.clear()
            for watch in list(self._watch.values()):
                self._result(watch.request, "unverified", "Controller stopped before confirmation")
            for request in self._urgent:
                self._result(request, "cancelled", "Controller stopped before transmission")
            self._urgent.clear()
            self._condition.notify_all()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=self.timeout + 0.5)
        self.transport.close()
        with self._condition:
            self._state.connected = self._state.transport_open = False
            if not thread or not thread.is_alive():
                self._thread = None
            self._emit_state()
        self._flush_audit()

    def _validate_submission(self, command_id: int, argument: object | None, *, pc_sequence: bool = False) -> None:
        spec = get_command(command_id)
        validate_profile_command(command_id, argument, self.pump_mode)
        encode_datagram([format_command(command_id, argument)])
        if self._stop.is_set():
            raise PermissionError("Controller is stopped; reconnect before submitting commands.")
        self._check_external_write(command_id, argument)
        safe = command_id in STOP_COMMAND_IDS or is_stop_command(command_id, argument)
        if spec.writable and not safe and self._pc_output.status in {"pending", "stopping"} and not pc_sequence:
            raise PermissionError("Wait for PC RUN/STOP confirmation before other writes")
        if spec.writable and not safe and self.transport.name != "Simulator" and not self._state.link_fresh():
            raise PermissionError("A recent controller readback is required before hardware writes.")

    def submit(self, command_id: int, argument: object | None = None, origin: str = "GUI", *, batch: str = "") -> int:
        with self._condition:
            self._validate_submission(command_id, argument, pc_sequence=batch == "pc-run")
            self._token += 1
            if command_id in STOP_COMMAND_IDS or is_stop_command(command_id, argument):
                # OFF is urgent and invalidates all queued energy/motion writes.
                self._cancel_pending_writes_locked(f"OFF/STOP requested [{command_id}].")
                request = PendingCommand(command_id, argument, origin, self._generation, self._token, batch)
                self._urgent.append(request)
                self._emit_state()
            else:
                request = PendingCommand(command_id, argument, origin, self._generation, self._token, batch)
                self._commands.append(request)
            self._result(request, "queued", origin)
            self._condition.notify_all()
            return request.token

    def query_now(self, command_ids: tuple[int, ...] | list[int]) -> None:
        if any(get_command(cid).writable for cid in command_ids):
            raise ValueError("query_now accepts read commands only")
        for cid in filter_queries(command_ids, self.pump_mode):
            self.submit(cid, origin="manual refresh")

    def _emit_state(self, reply: Reply | None = None) -> None:
        self.events.put(ControllerEvent("state", state=self._state.copy(), reply=reply))

    def _queue_readbacks(self, ids: tuple[int, ...]) -> None:
        for cid in reversed(filter_queries(ids, self.pump_mode)):
            self._commands.appendleft(PendingCommand(cid, None, "write readback", self._generation))

    def _execute(self, request: PendingCommand) -> None:
        try:
            self._execute_inner(request)
        finally:
            with self._condition:
                self._advance_pc_output_locked()
            self._flush_audit()

    def _execute_inner(self, request: PendingCommand) -> None:
        line = format_command(request.command_id, request.argument)
        checks = filter_queries(readback_ids(request.command_id, request.argument), self.pump_mode)
        if request.command_id == 2050:
            checks = tuple(dict.fromkeys(checks + OUTPUT_MONITOR_QUERY_IDS))
        writable = request.command_id >= 2000

        def guarded_send(send) -> None:
            # The authorization check and actual send share this lock. Never
            # hold it while waiting for a network reply or while writing logs.
            with self._condition:
                if self._stop.is_set():
                    raise CommandCancelled("Controller stopped")
                try:
                    validate_profile_command(request.command_id, request.argument, self.pump_mode)
                    self._check_external_write(request.command_id, request.argument)
                    if request.batch == "pc-run":
                        reason = self._pc_run_reason()
                        if reason:
                            raise PermissionError(reason)
                except (PermissionError, ValueError) as exc:
                    raise CommandCancelled(str(exc)) from exc
                safe = request.command_id in STOP_COMMAND_IDS or is_stop_command(request.command_id, request.argument)
                if writable and not safe:
                    if request.generation != self._generation:
                        raise CommandCancelled("Command cancelled after OFF, disconnect or an earlier failure")
                    if self.transport.name != "Simulator" and not self._state.link_fresh():
                        raise CommandCancelled("Controller readback is no longer fresh")
                if writable:
                    self._state.pending_readbacks.update(checks)
                send()
                if writable:
                    self._result(request, "sent", "Datagram sent; awaiting matching receipt")
                    self._emit_state()
            self.events.put(ControllerEvent("log", f"TX {line}"))
            self._record_audit("TX", request.command_id, line, request.origin)

        try:
            replies = self.transport.exchange(line, self.timeout, send_guard=guarded_send)
            replies = [r for r in replies if r.command_id == request.command_id]
            if not replies:
                raise TransportError("No matching-ID response received")
            if len({r.value for r in replies}) != 1:
                raise TransportError("Conflicting duplicate responses; outcome unknown")
            replies = replies[:1]
        except CommandCancelled as exc:
            self._record_audit("CANCEL", request.command_id, line, str(exc))
            with self._condition:
                self._result(request, "cancelled", str(exc))
            self.events.put(ControllerEvent("log", f"CANCEL {line}: {exc}"))
            return
        except TransportError as exc:
            with self._condition:
                self._state.last_error = str(exc)
                if request.command_id < 2000:
                    self._state.invalidate(request.command_id)
                self._state.connected = False
                self._cancel_pending_writes_locked(f"Communication failure: {exc}")
                if writable:
                    self._result(request, "timeout", "Communication failure; application unknown; no automatic write retry")
                    self._queue_readbacks(checks)
                self.events.put(ControllerEvent("error", str(exc), state=self._state.copy()))
            self._record_audit("ERROR", request.command_id, line, str(exc))
            return
        with self._condition:
            for reply in replies:
                valid = self._state.apply(reply)
                device_error = is_error_reply(reply.value)
                empty_receipt = (writable and not reply.value.strip()
                                 and permits_empty_receipt(request.command_id, request.argument))
                accepted = valid or empty_receipt
                self._record_audit("RX", reply.command_id, reply.raw_line, "")
                if device_error or not accepted:
                    kind = "DEVICE_ERROR" if device_error else "INVALID_REPLY" if not reply.value.strip() else "PARSE_ERROR"
                    message = f"Controller reply [{reply.command_id}]: {reply.value or '(empty)'}"
                    reason = ("Empty response payload; no state value or acknowledgement was received." if not reply.value.strip() else
                              "Controller returned an ERR/NACK/FAIL response." if device_error else
                              "Unrecognized acknowledgement; expected OK or ACK, or a supported empty receipt." if writable else
                              "Response format or value was rejected by the state decoder.")
                    self._record_audit(kind, reply.command_id, reply.raw_line, reason)
                    self._state.last_error = message
                    if writable:
                        self._result(request, "rejected", message)
                        self._cancel_pending_writes_locked(message)
                    elif self.pump_mode == "external" and reply.command_id in EXTERNAL_REQUIRED_READS:
                        kept = deque()
                        for queued in self._commands:
                            if requires_external_enable_check(queued.command_id, queued.argument):
                                reason = "Output request cancelled: required readback unavailable"
                                self._record_audit("CANCEL", queued.command_id, format_command(queued.command_id, queued.argument), reason)
                                self._result(queued, "cancelled", reason)
                            else:
                                kept.append(queued)
                        self._commands = kept
                    self.events.put(ControllerEvent("error", message, state=self._state.copy(), reply=reply))
                elif not writable:
                    recovering = not self._state.connected
                    self._state.connected = True
                    if recovering:
                        self._state.last_error = ""
                    self._last_read_monotonic = time.monotonic()
                else:
                    if empty_receipt:
                        self._record_audit("UNCONFIRMED_WRITE", request.command_id, reply.raw_line,
                                          "Matching empty receipt; application must be checked by readback")
                    self._result(request, "receipt" if empty_receipt else "acknowledged",
                                 "Response received; not proof of application")
                    now = time.monotonic()
                    not_before = now + RESET_RECHECK_SECONDS[-1] if request.command_id == 2050 else 0.0
                    if checks and request.token:
                        self._watch[request.token] = WriteWatch(
                            request, set(checks), expected_targets(request.command_id, request.argument),
                            now + max(15.0, RESET_RECHECK_SECONDS[-1] + len(checks)*self.timeout + 5), not_before)
                    elif request.token:
                        self._result(request, "unverified", "Receipt only; no applicable readback in this pump profile")
                    if request.command_id == 2050:
                        for delay in RESET_RECHECK_SECONDS:
                            for cid in filter_queries(FAULT_QUERY_IDS + OUTPUT_MONITOR_QUERY_IDS, self.pump_mode):
                                self._readback_serial += 1
                                heapq.heappush(self._delayed, (now+delay, self._readback_serial, cid))
                if not writable:
                    self._observe(reply, valid and not device_error)
                self._emit_state(reply)  # ACK/receipt alone never changes measurements.
                self.events.put(ControllerEvent("log", f"RX {reply.raw_line}"))
            if writable and not (request.batch == "reset" and request.command_id != 2050):
                self._queue_readbacks(checks)
            self._condition.notify_all()

    def _check_external_write(self, command_id: int, argument: object | None) -> None:
        if self.pump_mode != "external" or command_id < 2000:
            return
        if command_id in {2018, 2020, 2030, 2031, 2032, 2036, 2046} and self._state.high_voltage is not False:
            raise PermissionError("A recent HV OFF readback is required before timing-source/divisor changes or opt-out.")
        if requires_external_enable_check(command_id, argument):
            reason = self._state.external_enable_reason()
            if reason:
                raise PermissionError(reason)

    def _initial_ids(self) -> tuple[int, ...]:
        ids = filter_queries(tuple(dict.fromkeys(OUTPUT_MONITOR_QUERY_IDS + INITIAL_QUERY_IDS)), self.pump_mode)
        if self.pump_mode == "external":
            # HV/compatibility/fault facts are needed even before normal polling.
            return tuple(dict.fromkeys((1000,) + EXTERNAL_REQUIRED_READS + ids))
        return ids

    def _poll_ids(self) -> tuple[int, ...]:
        return filter_queries(FAST_POLL_IDS + FAULT_QUERY_IDS +
                              (HV_POLL_IDS if self.monitor_hv else ()), self.pump_mode)

    def _next_automatic_poll(self, now: float) -> PendingCommand | None:
        """Keep the existing poll slots; skip environment reads every other cycle.

        A skipped slot still consumes its time, so other queries do not speed
        up. After a pause there is no catch-up burst. Called under _condition.
        """
        if not self.auto_poll:
            self._poll_configuration = None
            return None
        configuration = (self.poll_interval, self.monitor_hv)
        if configuration != self._poll_configuration:
            self._poll_index = 0
            self._next_poll_at = now
            self._poll_configuration = configuration
        if now < self._next_poll_at:
            return None
        ids = self._poll_ids()
        cycle, slot = divmod(self._poll_index, len(ids))
        cid = ids[slot]
        self._poll_index += 1
        self._next_poll_at = now + self.poll_interval / len(ids)
        if cid in ENVIRONMENT_POLL_IDS and cycle % 2:
            return None
        return PendingCommand(cid, None, "automatic poll")

    def _run(self) -> None:
        try:
            self.transport.connect()
            with self._condition:
                self._state.transport_open = True
                self._state.connected = False
                self.events.put(ControllerEvent("connection", "Transport open; waiting for controller reply", state=self._state.copy()))
            initial = iter(self._initial_ids())
            output_checks = tuple(dict.fromkeys((EXTERNAL_REQUIRED_READS if self.pump_mode == "external" else ()) + OUTPUT_MONITOR_QUERY_IDS))
            next_external_check = time.monotonic() + min(0.2, 2.0 / len(output_checks))
            external_check_index = 0
            next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS
            self._poll_configuration = None
            while not self._stop.is_set():
                with self._condition:
                    now = time.monotonic()
                    self._state.stale_after_seconds = max(5.0, 3 * self.poll_interval, 2 * self.timeout)
                    if self._state.connected and self._last_read_monotonic is not None and now - self._last_read_monotonic > self._state.stale_after_seconds:
                        self._state.connected = False
                        self._state.last_error = "Controller readback is stale"
                        self._cancel_pending_writes_locked("Controller readback is stale.")
                        self._emit_state()
                    self._expire_watches(now)
                    self._advance_pc_output_locked()
                    request = None
                    if self._urgent:
                        request = self._urgent.popleft()
                    elif self._commands and self._commands[0].batch == "reset":
                        request = self._commands.popleft()
                    elif self._delayed and self._delayed[0][0] <= now:
                        _, _, cid = heapq.heappop(self._delayed)
                        request = PendingCommand(cid, None, "delayed fault readback")
                    elif now >= next_heartbeat:
                        # Independent of Automatic polling and ordinary queue
                        # traffic. OFF/STOP always retain first priority.
                        request = PendingCommand(HEARTBEAT_QUERY_ID, None, "connection heartbeat")
                    elif now >= next_external_check:
                        cid = output_checks[external_check_index % len(output_checks)]
                        external_check_index += 1
                        request = PendingCommand(cid, None, "output status monitor")
                    elif self._commands:
                        request = self._commands.popleft()
                    else:
                        cid = next(initial, None)
                        if cid is not None:
                            request = PendingCommand(cid, None, "initialization")
                        else:
                            request = self._next_automatic_poll(now)
                    if request is None:
                        self._condition.wait(0.05)
                if request is not None:
                    self._execute(request)
                    if request.origin == "output status monitor":
                        next_external_check = time.monotonic() + min(0.2, 2.0 / len(output_checks))
                    if request.origin == "connection heartbeat":
                        # Also pace failed checks, allowing queued commands to
                        # run between attempts after a full response timeout.
                        next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL_SECONDS
        except (TransportError, OSError, ValueError) as exc:
            with self._condition:
                self._state.last_error = str(exc)
                self.events.put(ControllerEvent("error", str(exc), state=self._state.copy()))
        finally:
            self.transport.close()
            with self._condition:
                self._stop.set()
                self._advance_pc_output_locked()
                self._state.connected = self._state.transport_open = False
                self._cancel_pending_writes_locked(self._state.last_error or "Disconnected.")
                for watch in list(self._watch.values()):
                    self._result(watch.request, "unverified", "Disconnected before confirmation")
                self._delayed.clear()
                self.events.put(ControllerEvent("connection", "Disconnected", state=self._state.copy()))
            self._flush_audit()

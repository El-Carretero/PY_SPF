"""Asynchronous scheduler with send-time authorization and readback monitoring."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import math
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

SAFE_WHEN_DISARMED = frozenset({2006, 2013, 2016, 2023, 2028})
HEARTBEAT_QUERY_ID = 1000  # Known read-only *idn? controller query.
HEARTBEAT_INTERVAL_SECONDS = 1.0

@dataclass(frozen=True, slots=True)
class ControllerEvent:
    kind: Literal["state", "log", "error", "connection"]
    message: str = ""
    state: DeviceState | None = None
    reply: Reply | None = None

@dataclass(frozen=True, slots=True)
class PendingCommand:
    command_id: int
    argument: object | None
    origin: str
    generation: int = 0

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
        self._armed = False
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

    def _disarm_locked(self) -> None:
        self._armed = self._state.armed = False
        self._generation += 1
        # Already dequeued commands are also invalidated by their generation.
        self._commands = deque(r for r in self._commands if r.command_id < 2000)

    def stop(self) -> None:
        with self._condition:
            self._stop.set()
            self._disarm_locked()
            self._commands.clear()
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

    def arm(self, enabled: bool) -> None:
        with self._condition:
            if enabled:
                if self.transport.name != "Simulator" and not self._state.link_fresh():
                    raise PermissionError("A recent valid controller readback is required before ARM.")
                self._armed = self._state.armed = True
            else:
                self._disarm_locked()
            self._emit_state()
            self._condition.notify_all()

    def submit(self, command_id: int, argument: object | None = None, origin: str = "GUI") -> None:
        spec = get_command(command_id)
        validate_profile_command(command_id, argument, self.pump_mode)
        encode_datagram([format_command(command_id, argument)])
        with self._condition:
            if self._stop.is_set():
                raise PermissionError("Controller is stopped; reconnect before submitting commands.")
            self._check_external_write(command_id, argument)
            if command_id in SAFE_WHEN_DISARMED or is_stop_command(command_id, argument):
                # OFF is urgent and invalidates all queued energy/motion writes.
                self._disarm_locked()
                self._urgent.append(PendingCommand(command_id, argument, origin, self._generation))
                self._emit_state()
            else:
                if spec.writable and self.transport.name != "Simulator":
                    if not self._armed or not self._state.link_fresh():
                        raise PermissionError("Hardware writes are locked. Connect and ARM first.")
                self._commands.append(PendingCommand(command_id, argument, origin, self._generation))
            self._condition.notify_all()

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
        line = format_command(request.command_id, request.argument)
        checks = filter_queries(readback_ids(request.command_id, request.argument), self.pump_mode)
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
                except (PermissionError, ValueError) as exc:
                    raise CommandCancelled(str(exc)) from exc
                safe = request.command_id in SAFE_WHEN_DISARMED or is_stop_command(request.command_id, request.argument)
                if writable and not safe:
                    if request.generation != self._generation:
                        raise CommandCancelled("Command cancelled by DISARM/OFF")
                    if self.transport.name != "Simulator" and (not self._armed or not self._state.link_fresh()):
                        raise CommandCancelled("Hardware authorization no longer valid")
                if writable:
                    self._state.pending_readbacks.update(checks)
                send()
                if writable:
                    self._emit_state()
            self.events.put(ControllerEvent("log", f"TX {line}"))
            self._audit.write("TX", request.command_id, line, request.origin)

        try:
            replies = self.transport.exchange(line, self.timeout, send_guard=guarded_send)
        except CommandCancelled as exc:
            self._audit.write("CANCEL", request.command_id, line, str(exc))
            self.events.put(ControllerEvent("log", f"CANCEL {line}: {exc}"))
            return
        except TransportError as exc:
            with self._condition:
                self._state.last_error = str(exc)
                if request.command_id < 2000:
                    self._state.invalidate(request.command_id)
                self._state.connected = False
                self._disarm_locked()
                if writable:
                    self._queue_readbacks(checks)
                self.events.put(ControllerEvent("error", str(exc), state=self._state.copy()))
            self._audit.write("ERROR", request.command_id, line, str(exc))
            return
        with self._condition:
            for reply in replies:
                valid = self._state.apply(reply)
                if is_error_reply(reply.value) or not valid:
                    message = f"Controller reply [{reply.command_id}]: {reply.value or '(empty)'}"
                    self._state.last_error = message
                    if writable or (self.pump_mode == "external" and reply.command_id in EXTERNAL_REQUIRED_READS):
                        self._disarm_locked()
                    self.events.put(ControllerEvent("error", message, state=self._state.copy(), reply=reply))
                elif reply.command_id < 2000:
                    recovering = not self._state.connected
                    self._state.connected = True
                    if recovering:
                        self._state.last_error = ""
                    self._last_read_monotonic = time.monotonic()
                    self._emit_state(reply)
                else:
                    self._emit_state(reply)  # ACK alone never changes measured state.
                self.events.put(ControllerEvent("log", f"RX {reply.raw_line}"))
            if writable:
                self._queue_readbacks(checks)
            self._condition.notify_all()
        for reply in replies:
            self._audit.write("RX", reply.command_id, reply.raw_line, "")

    def _check_external_write(self, command_id: int, argument: object | None) -> None:
        if self.pump_mode != "external" or command_id < 2000:
            return
        if command_id in {2018, 2020, 2030, 2031, 2032, 2036, 2046, 2049, 2052} and self._state.high_voltage is not False:
            raise PermissionError("A recent HV OFF readback is required before timing-source/divisor changes, opt-out or fault-latch reset.")
        if requires_external_enable_check(command_id, argument):
            reason = self._state.external_enable_reason()
            if reason:
                raise PermissionError(reason)

    def _initial_ids(self) -> tuple[int, ...]:
        ids = filter_queries(INITIAL_QUERY_IDS, self.pump_mode)
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
            next_external_check = time.monotonic() + min(0.2, 2.0 / len(EXTERNAL_REQUIRED_READS))
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
                        self._disarm_locked()
                        self._emit_state()
                    request = None
                    if self._urgent:
                        request = self._urgent.popleft()
                    elif now >= next_heartbeat:
                        # Independent of Automatic polling and ordinary queue
                        # traffic. OFF/STOP always retain first priority.
                        request = PendingCommand(HEARTBEAT_QUERY_ID, None, "connection heartbeat")
                    elif self.pump_mode == "external" and now >= next_external_check:
                        cid = EXTERNAL_REQUIRED_READS[external_check_index % len(EXTERNAL_REQUIRED_READS)]
                        external_check_index += 1
                        request = PendingCommand(cid, None, "external compatibility monitor")
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
                    if request.origin == "external compatibility monitor":
                        next_external_check = time.monotonic() + min(0.2, 2.0 / len(EXTERNAL_REQUIRED_READS))
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
                self._state.connected = self._state.transport_open = False
                self._disarm_locked()
                self.events.put(ControllerEvent("connection", "Disconnected", state=self._state.copy()))

"""Ordered request processing with nonblocking, per-client reply scheduling."""
from __future__ import annotations
import heapq
import copy
import json
import select
import socket
import threading
import time
from typing import Mapping

from .model import VirtualSpitfire
from .protocol import COMMAND_HEADER, ProtocolError, REPLY_HEADER, decode_commands, encode_replies
from .records import CaptureStore

class ServerError(RuntimeError):
    pass

class VirtualDeviceServer:
    def __init__(self, bind_ip: str, bind_port: int, device: VirtualSpitfire,
                 capture: CaptureStore, client_labels: Mapping[str, str] | None = None):
        self.bind_ip, self.bind_port = bind_ip, int(bind_port)
        self.device, self.capture = device, capture
        self.client_labels = dict(client_labels or {})
        self._socket = None
        self._thread = None
        self._stop = threading.Event()
        self._gate = threading.RLock()
        self._scheduled = []
        self._last_due = {}
        self._scenario_spec = None
        self._scenario_clock = 'manual'
        self._scenario_clients = {}
        self._scenario_manual_ms = 0.0

    def set_scenario(self, scenario, *, clock='manual') -> None:
        """Attach a synthetic scenario; only change it between stopped sessions.

        Realtime epochs start on each logical client's first request. This is
        a replayable stimulus, not a real-time electrical signal generator.
        """
        if clock not in {'manual', 'realtime'}:
            raise ValueError('scenario clock must be manual or realtime')
        from .scenarios import load_scenario
        spec = load_scenario(scenario) if scenario is not None else None
        with self._gate:
            if self.running:
                raise ServerError('Stop the server before changing scenario; then start a new session')
            self._scenario_spec = copy.deepcopy(spec)
            self._scenario_clock = clock
            self._scenario_clients.clear()
            self._scenario_manual_ms = 0.0

    def advance_scenario(self, time_ms, client_key=None) -> None:
        """Advance manual virtual time without sending any external commands."""
        import math
        if (isinstance(time_ms, bool) or not isinstance(time_ms, (int, float))
                or not 0 <= time_ms <= 86_400_000 or not math.isfinite(time_ms)):
            raise ValueError('time_ms must be finite')
        with self._gate:
            if self._scenario_spec is None or self._scenario_clock != 'manual':
                raise ServerError('A manual scenario must be attached first')
            if time_ms < self._scenario_manual_ms:
                raise ValueError('Scenario time cannot go backwards; reset the session')
            if client_key is None:
                if any(engine.snapshot()['time_ms'] > time_ms for engine, _ in self._scenario_clients.values()):
                    raise ValueError('One client is already ahead; no client was advanced')
                for engine, _ in self._scenario_clients.values():
                    engine.advance_to(time_ms)
                self._scenario_manual_ms = float(time_ms)
            else:
                engine, _ = self._get_scenario_client(client_key)
                engine.advance_to(time_ms)

    def _get_scenario_client(self, key):
        if key not in self._scenario_clients:
            from .scenarios import ScenarioEngine
            engine = ScenarioEngine(self._scenario_spec)
            engine.advance_to(self._scenario_manual_ms)
            self._scenario_clients[key] = (engine, time.perf_counter())
        return self._scenario_clients[key]

    def _scenario_profile(self, key, profile):
        if self._scenario_spec is None:
            return profile, {}
        engine, epoch = self._get_scenario_client(key)
        if self._scenario_clock == 'realtime':
            engine.advance_to(max(0.0, (time.perf_counter() - epoch) * 1000.0))
        effects = engine.wire_effects()
        profile = profile.copy()
        for field in ('overrides', 'delay_ms'):
            getattr(profile, field).update({int(k): v for k, v in effects.get(field, {}).items()})
        for field in ('drop_ids', 'error_ids', 'request_drop_ids'):
            getattr(profile, field).update(effects.get(field, []))
        return profile, engine.snapshot()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def local_address(self):
        with self._gate:
            return self._socket.getsockname() if self._socket is not None else None

    def _session_metadata(self):
        self.capture.set_metadata(virtual_device=f"{self.bind_ip}:{self.bind_port}",
                                  client_labels=self.client_labels,
                                  isolated_client_state=self.device.isolated_clients,
                                  response_profile=self.device.get_profile().to_dict())
        self.capture.set_metadata(live_scenario=copy.deepcopy(self._scenario_spec),
                                  scenario_clock=self._scenario_clock,
                                  scenario_scope='synthetic stimulus; client GUI and physical behavior unverified',
                                  xp_runtime_validation='UNVERIFIED', physical_validation='UNVERIFIED')

    def start(self) -> None:
        if self.running:
            return
        if not 0 <= self.bind_port <= 65535:
            raise ServerError("UDP port must be in 0..65535")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((self.bind_ip, self.bind_port))
            sock.setblocking(False)
        except OSError as exc:
            sock.close()
            raise ServerError(f"Cannot bind {self.bind_ip}:{self.bind_port}: {exc}") from exc
        with self._gate:
            self._socket = sock
            self._stop.clear()
            self._session_metadata()
            self.capture.message("INFO", f"Virtual Spitfire listening on {sock.getsockname()}")
            self._thread = threading.Thread(target=self._serve, name="spitfire-udp-server", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        with self._gate:
            while self._scheduled:
                _, _, work = heapq.heappop(self._scheduled)
                self._deliver(work, stopped=True)
            self._last_due.clear()
            if self._socket is not None:
                self._socket.close()
                self._socket = None
            self._thread = None
            self.capture.message("INFO", "Virtual Spitfire stopped")

    def set_profile(self, profile) -> None:
        with self._gate, self.capture.locked():
            self.device.set_profile(profile)
            self.capture.set_metadata(response_profile=profile.to_dict())
            self.capture.message("PROFILE", "response conditions updated", details=profile.to_dict())

    def reset_session(self) -> None:
        """Cancel old responses and buffered requests before resetting state/evidence."""
        with self._gate, self.capture.locked():
            cancelled = len(self._scheduled)
            self._scheduled.clear()
            self._last_due.clear()
            drained = 0
            if self._socket is not None:
                # Bounded drain; remote traffic arriving after the boundary belongs to the new run.
                for _ in range(4096):
                    try:
                        self._socket.recvfrom(65535)
                        drained += 1
                    except (BlockingIOError, OSError):
                        break
            self.device.reset()
            self._scenario_clients.clear()
            self._scenario_manual_ms = 0.0
            self.capture.clear()
            self._session_metadata()
            self.capture.message("SESSION", "New session; device state reset",
                                 details={"cancelled_replies": cancelled, "drained_datagrams": drained})

    def _identity(self, sender):
        endpoint = f"{sender[0]}:{sender[1]}"
        label = self.client_labels.get(endpoint) or self.client_labels.get(sender[0])
        # A logical client keeps its state when reconnecting with a different source port.
        return label or endpoint, label or f"Unassigned {endpoint}"

    def _serve(self) -> None:
        try:
            while not self._stop.is_set():
                with self._gate:
                    sock = self._socket
                    wait = max(0.0, min(.05, self._scheduled[0][0] - time.perf_counter())) if self._scheduled else .05
                if sock is None:
                    break
                readable, _, _ = select.select([sock], [], [], wait)
                with self._gate, self.capture.locked():
                    if self._stop.is_set():
                        break
                    if readable:
                        try:
                            data, sender = sock.recvfrom(65535)
                        except BlockingIOError:
                            pass
                        else:
                            received = time.perf_counter()
                            self._process(data, (str(sender[0]), int(sender[1])), received)
                    now = time.perf_counter()
                    while self._scheduled and self._scheduled[0][0] <= now:
                        _, _, work = heapq.heappop(self._scheduled)
                        self._deliver(work)
        except Exception as exc:
            self.capture.message("ERROR", f"Server acquisition stopped: {type(exc).__name__}: {exc}")
            self._stop.set()

    def _process(self, data, sender, received):
        timestamp = self.capture.now()
        sid = self.capture.session_id
        seq = self.capture.next_datagram_sequence()
        key, label = self._identity(sender)
        if label.startswith("Unassigned "):
            self.capture.message("UNASSIGNED", "Unassigned client packet", source_ip=sender[0],
                                 source_port=sender[1], client_label=label, raw_hex=data.hex(" "))
        try:
            commands = decode_commands(data)
        except ProtocolError as exc:
            self.capture.message("PROTOCOL", str(exc), source_ip=sender[0], source_port=sender[1],
                                 client_label=label, raw_hex=data.hex(" "),
                                 details={"datagram_sequence": seq})
            return
        profile, scenario_state = self._scenario_profile(key, self.device.get_profile())
        answers = [self.device.answer(key, command, profile) for command in commands]
        delay = max((answer.delay_ms for answer in answers), default=0)
        due = max(received + delay / 1000, self._last_due.get(key, received))
        self._last_due[key] = due
        lines = [line for line in data[len(COMMAND_HEADER):].splitlines(keepends=True) if line.strip()]
        work = dict(sid=sid, seq=seq, data=data, sender=sender, key=key, label=label,
                    received=received, timestamp=timestamp, commands=commands, answers=answers,
                    profile=profile, scenario=(self._scenario_spec.get('id', self._scenario_spec.get('name', 'scenario'))
                        if self._scenario_spec else self.capture.scenario), lines=lines,
                    scenario_state=scenario_state,
                    processing_ms=(time.perf_counter() - received) * 1000, delay=delay)
        self.capture.begin_pending(seq, datagram_sequence=seq, client_label=label,
                                   received_utc=timestamp, command_ids=[c.command_id for c in commands])
        heapq.heappush(self._scheduled, (due, seq, work))

    def _deliver(self, work, *, stopped=False):
        w = work
        if w['sid'] != self.capture.session_id:
            return
        commands, answers, profile = w['commands'], w['answers'], w['profile']
        replies = [(c.command_id, a.value) for c, a in zip(commands, answers) if not a.dropped and a.value is not None]
        response, sent = b"", ""
        status = "STOPPED" if stopped else ("REPLIED" if replies else "DROPPED")
        header = b"Spectra-Physics:BROKEN_ECLIPSE:" if profile.malformed_reply_header else REPLY_HEADER
        if replies and not stopped:
            try:
                response = encode_replies(replies, line_ending=profile.line_ending, header=header)
                self._socket.sendto(response, w['sender'])
                sent = self.capture.now()
            except (OSError, ProtocolError) as exc:
                status = "SEND_ERROR"
                self.capture.message("ERROR", str(exc), source_ip=w['sender'][0],
                                     source_port=w['sender'][1], client_label=w['label'])
        elapsed = (time.perf_counter() - w['received']) * 1000
        with self.capture.locked():
            for index, (command, answer) in enumerate(zip(commands, answers), 1):
                request_line = w['lines'][index - 1]
                ending = "CRLF" if request_line.endswith(b"\r\n") else ("LF" if request_line.endswith(b"\n") else "NONE")
                reply_line = (f"<{command.command_id}>{answer.value}" + profile.line_ending).encode("ascii", "backslashreplace") if not answer.dropped else b""
                self.capture.add_transaction(
                    datagram_sequence=w['seq'], timestamp_utc=w['timestamp'],
                    client_key=w['key'], client_label=w['label'], source_ip=w['sender'][0],
                    source_port=w['sender'][1], command_index=index, command_id=command.command_id,
                    command=command.command, base=command.base, argument=command.argument,
                    request_hex=w['data'].hex(" "), response_value=answer.value,
                    response_hex=response.hex(" "), latency_ms=elapsed,
                    status="STOPPED" if stopped else ("DROPPED" if answer.dropped else status),
                    note=answer.note, session_id=w['sid'], sent_utc=sent if not answer.dropped else "",
                    processing_ms=w['processing_ms'], configured_delay_ms=w['delay'],
                    validation=answer.validation, modelled=answer.modelled, effect=answer.effect,
                    profile_json=json.dumps(profile.to_dict(), sort_keys=True), scenario=w['scenario'],
                    scenario_time_ms=w['scenario_state'].get('time_ms'),
                    scenario_phase=w['scenario_state'].get('processed_events', w['scenario_state'].get('phase', 0)),
                    scenario_state_json=json.dumps(w['scenario_state'], sort_keys=True),
                    request_line_hex=request_line.hex(" "), reply_line_hex=reply_line.hex(" ") if response else "",
                    request_framing="CMD_ECLIPSE/" + ending,
                    reply_framing=(header.decode('ascii') + repr(profile.line_ending)) if response and not answer.dropped else "",
                )
            self.capture.finish_pending(w['seq'])

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()

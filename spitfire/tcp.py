"""Single-client local TCP status server recovered from Spitfire GUI 1.6.0.

The four commands read GUI control values; they do not forward commands to the
laser. Native evidence: _TCP_Parse 0x412724, _ServerTCPCB 0x406227,
_InitServer 0x405f08 and _Write_to_TCP_Server 0x40668c.
"""
from __future__ import annotations

import select
import socket
import struct
import threading
from collections.abc import Callable, Mapping
from typing import Any

DEFAULT_TCP_PORT = 1001
ATTR_DIMMED = 500
IDENTITY_FIELDS = ((4, 16), (4, 6), (4, 7), (4, 5), (4, 4), (4, 3))
TDG_FIELDS = ((6, 43), (6, 42), (5, 42), (5, 41), (6, 41))
TEMP_FIELDS = ((9, 8), (9, 2), (8, 15), (9, 9))
# The last active indicator wins; order is the original instruction order.
TEMP_STATUS_INDICATORS = ((6, 29), (6, 31), (6, 24), (6, 25), (6, 22))


def _float32(value: Any) -> float:
    return struct.unpack('<f', struct.pack('<f', float(value)))[0]


def trim_request(data: str | bytes) -> str:
    """Original C-string parsing: one CR first, then one LF (not strip()).

    Consequently a conventional CRLF suffix leaves a CR and does not match any
    command; LFCR removes both. Spaces and case remain significant.
    """
    if isinstance(data, bytes):
        data = data.decode('latin1')
    data = data.split('\0', 1)[0]
    if data.endswith('\r'):
        data = data[:-1]
    if data.endswith('\n'):
        data = data[:-1]
    return data


class TCPBridge:
    """Pure request parser plus an explicitly started single-client TCP server.

    ``read_value(panel_id, control_id)`` and ``read_attribute(panel, control,
    attribute)`` read a thread-safe snapshot of application state. Both can also
    be tuple-keyed mappings. ``on_event(kind, payload)`` may mirror server-panel
    log and connection state. This module never imports Qt or starts on import.

    start() binds all interfaces as the native RegisterTCPServer did. Pass
    host='127.0.0.1' for a local-only listener. Server receive calls parse each
    raw chunk of at most 255 bytes independently, matching the original callback
    rather than adding a new line-framing protocol.
    """
    def __init__(
        self,
        read_value: Callable[[int, int], Any] | Mapping[tuple[int, int], Any],
        read_attribute: Callable[[int, int, int], Any] | Mapping[tuple[int, int, int], Any] | None = None,
        state: dict[str, Any] | None = None,
        on_event: Callable[[str, Any], None] | None = None,
    ) -> None:
        self.read_value = read_value if callable(read_value) else lambda p, c: read_value.get((p, c), 0)
        if callable(read_attribute):
            self.read_attribute = read_attribute
        elif read_attribute is not None:
            self.read_attribute = lambda p, c, a: read_attribute.get((p, c, a), 0)
        else:
            self.read_attribute = lambda p, c, a: 0
        self.state = state if state is not None else {}
        self.on_event = on_event
        self.last_error: str | None = None
        self._listener: socket.socket | None = None
        self._client: socket.socket | None = None
        self._peer: tuple[str, int] | None = None
        self._address: tuple[str, int] | None = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _emit(self, kind: str, payload: Any = None) -> None:
        if self.on_event is not None:
            try:
                self.on_event(kind, payload)
            except Exception as exc:
                # A GUI notification failure must not strand an open listener.
                self.last_error = str(exc)

    def _number(self, panel: int, control: int) -> float:
        return _float32(self.read_value(panel, control))

    def handle_data(self, data: str | bytes) -> bytes:
        """Return the exact local query response, or b'' for an unknown query."""
        command = trim_request(data)
        if command == 'FAULTS?':
            active = int(self.read_attribute(6, 50, ATTR_DIMMED) == 0)
            result = f'{active}\n'
        elif command == '*IDN?':
            fields = [str(self.read_value(*key)) for key in IDENTITY_FIELDS]
            result = 'Spectra-Physics, Spitfire, 0, ' + ' / '.join(fields) + '\n'
        elif command == 'TDG_STATUS?':
            values = [self._number(*key) for key in TDG_FIELDS]
            bwd_enabled = int(self.read_attribute(6, 5, ATTR_DIMMED) == 0)
            frequency = self._number(5, 7)
            result = ', '.join(f'{value:.3f}' for value in values)
            result += f', {bwd_enabled}, {frequency:.0f}\n'
        elif command == 'TEMP_STATUS?':
            values = [self._number(*key) for key in TEMP_FIELDS]
            # Native local_488 is uninitialized if every indicator is off. A
            # deterministic 0 is used for that undefined native edge case.
            status = 0
            for code, key in enumerate(TEMP_STATUS_INDICATORS):
                if self.read_value(*key):
                    status = code
            result = ', '.join(f'{value:.3f}' for value in values) + f', {status}\n'
        else:
            return b''
        return result.encode('latin1', errors='replace')

    # Explicit parser alias for hosts that supply their own event loop/socket.
    parse = handle_data

    @property
    def running(self) -> bool:
        return self._listener is not None and not self._stop.is_set()

    @property
    def connected(self) -> bool:
        return self._client is not None

    @property
    def address(self) -> tuple[str, int] | None:
        return self._address

    @property
    def peer(self) -> tuple[str, int] | None:
        return self._peer

    def start(self, host: str = '0.0.0.0', port: int = DEFAULT_TCP_PORT) -> tuple[str, int]:
        """Open the listener. Port=0 selects an ephemeral port for local tests."""
        with self._lock:
            if self._listener is not None:
                assert self._address is not None
                return self._address
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((host, port))
                listener.listen()
                listener.setblocking(False)
            except BaseException:
                listener.close()
                raise
            self._listener = listener
            self._address = listener.getsockname()
            self._stop.clear()
            self.last_error = None
            self._thread = threading.Thread(target=self._serve, name='Spitfire TCP status', daemon=True)
            self._thread.start()
        self._emit('listening', self._address)
        return self._address

    def _disconnect(self, expected: socket.socket | None = None) -> None:
        with self._lock:
            if expected is not None and expected is not self._client:
                return
            client, peer = self._client, self._peer
            self._client, self._peer = None, None
            if client is not None:
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                client.close()
        if client is not None:
            self._emit('disconnected', peer)

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            listener, self._listener = self._listener, None
            if listener is not None:
                listener.close()
        self._disconnect()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.5)
        self._emit('stopped')

    close = stop

    def _write(self, data: bytes, expected: socket.socket | None = None) -> bool:
        with self._lock:
            client = self._client
            if client is None or (expected is not None and expected is not client):
                return False
            try:
                client.sendall(data)
            except OSError as exc:
                self.last_error = str(exc)
                self._emit('error', self.last_error)
                self._disconnect(client)
                return False
        self._emit('transmitted', data.decode('latin1'))
        return True

    def send_text(self, text: str) -> bool:
        """Server-panel Transmit button: append exactly one LF and write."""
        return self._write((text + '\n').encode('latin1', errors='replace'))

    def _serve(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                listener, client = self._listener, self._client
            if listener is None:
                return
            sockets = [listener] + ([client] if client is not None else [])
            try:
                readable, _, _ = select.select(sockets, [], [], 0.05)
            except (OSError, ValueError):
                if self._stop.is_set():
                    return
                continue
            if listener in readable:
                try:
                    incoming, peer = listener.accept()
                    incoming.settimeout(2.0)
                except OSError:
                    continue
                with self._lock:
                    refuse = self._client is not None
                    if not refuse:
                        self._client, self._peer = incoming, peer
                if refuse:
                    incoming.close()
                    self._emit('refused', peer)
                else:
                    self._emit('connected', peer)
            if client is not None and client in readable:
                try:
                    data = client.recv(255)
                except (OSError, socket.timeout) as exc:
                    self.last_error = str(exc)
                    self._emit('error', self.last_error)
                    self._disconnect(client)
                    continue
                if not data:
                    self._disconnect(client)
                    continue
                self._emit('received', data.decode('latin1').split('\0', 1)[0])
                try:
                    result = self.handle_data(data)
                except Exception as exc:
                    self.last_error = str(exc)
                    self._emit('error', self.last_error)
                    continue
                if result:
                    self._write(result, client)

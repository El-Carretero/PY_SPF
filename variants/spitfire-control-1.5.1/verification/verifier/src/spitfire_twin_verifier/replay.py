"""Passive exact-datagram replay on IPv4 loopback only.

Recorded requests are NEVER transmitted. A local test client must send the exact
next request before its recorded response is returned. Packet contents/order,
not original elapsed timing, are replayed. Mismatches fail closed.
"""
from __future__ import annotations

from collections import defaultdict, deque
import ipaddress
import socket
import threading

from .evidence import EvidenceError
from .protocol import decode_commands, ProtocolError
from .records import CaptureSnapshot


def _packets(snapshot, client_label):
    if not isinstance(snapshot, CaptureSnapshot) or snapshot.pending:
        raise EvidenceError('Replay requires a complete CaptureSnapshot with no pending datagrams')
    items = [item for item in snapshot.transactions if item.client_label == client_label]
    if not items:
        raise EvidenceError('Selected client has no captured transactions')
    if any(message.level in {'ERROR', 'PROTOCOL'} and message.client_label in {'', client_label}
           for message in snapshot.messages):
        raise EvidenceError('Capture has acquisition/protocol errors; ordered replay would be incomplete')
    grouped = defaultdict(list)
    for item in items:
        if item.status not in {'REPLIED', 'DROPPED'}:
            raise EvidenceError('Only replied or intentionally dropped transactions can be replayed')
        grouped[item.datagram_sequence].append(item)
    packets = []
    for sequence, rows in sorted(grouped.items()):
        rows.sort(key=lambda item: item.command_index)
        if len({item.request_hex for item in rows}) != 1 or len({item.response_hex for item in rows}) != 1:
            raise EvidenceError('Inconsistent duplicate raw datagram evidence')
        if len({item.client_key for item in rows}) != 1:
            raise EvidenceError('One datagram cannot belong to several client identities')
        try:
            request, response = bytes.fromhex(rows[0].request_hex), bytes.fromhex(rows[0].response_hex)
            commands = decode_commands(request)
        except (ValueError, ProtocolError) as exc:
            raise EvidenceError(f'Invalid raw request in datagram {sequence}') from exc
        if len(request) > 65507 or len(response) > 65507:
            raise EvidenceError('Raw datagram exceeds UDP payload size')
        if [item.command_index for item in rows] != list(range(1, len(commands)+1)):
            raise EvidenceError('Incomplete command records for a captured datagram')
        if any(item.command_id != command.command_id or item.command != command.command
               for item, command in zip(rows, commands)):
            raise EvidenceError('Parsed transaction does not match its raw request')
        if any(item.status == 'REPLIED' for item in rows) and not response:
            raise EvidenceError('Replied datagram is missing raw response bytes')
        if all(item.status == 'DROPPED' for item in rows) and response:
            raise EvidenceError('Fully dropped datagram must not contain sent response bytes')
        packets.append((request, response, sequence))
    return packets


class ReplayServer:
    def __init__(self, snapshot, client_label, *, bind_ip='127.0.0.1', bind_port=0):
        try:
            address = ipaddress.IPv4Address(bind_ip)
        except (ValueError, TypeError) as exc:
            raise EvidenceError('Replay bind must be a literal IPv4 loopback address') from exc
        if not address.is_loopback:
            raise EvidenceError('Replay is restricted to loopback; physical-network binding is prohibited')
        if isinstance(bind_port, bool) or not isinstance(bind_port, int) or not 0 <= bind_port <= 65535:
            raise EvidenceError('Invalid replay port')
        self._packets = _packets(snapshot, client_label)
        self.bind_ip, self.bind_port = str(address), bind_port
        self.client_label = client_label
        self._socket = self._thread = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._cursor = 0
        self._peer = None
        self._events = deque(maxlen=10000)
        self._mismatches = self._rejected_peers = 0

    @property
    def local_address(self):
        return self._socket.getsockname() if self._socket else None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def status(self):
        with self._lock:
            return {'kind': 'exact_datagram_fixture_replay', 'matched_datagrams': self._cursor,
                    'total_datagrams': len(self._packets), 'mismatches': self._mismatches,
                    'rejected_peers': self._rejected_peers, 'complete': self._cursor == len(self._packets),
                    'client_label': self.client_label, 'events': list(self._events),
                    'original_runtime_validation': 'UNVERIFIED', 'physical_validation': 'UNVERIFIED',
                    'scope': 'Recorded raw reply bytes/order only; timing and original GUI behaviour are not reproduced'}

    def start(self):
        if self.running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((self.bind_ip, self.bind_port))
            sock.settimeout(.05)
        except OSError:
            sock.close()
            raise
        self._socket = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name='spitfire-passive-replay', daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop.is_set():
            try:
                data, peer = self._socket.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                if not ipaddress.ip_address(peer[0]).is_loopback or (self._peer is not None and peer != self._peer):
                    self._rejected_peers += 1
                    self._events.append({'status': 'PEER_REJECTED'})
                    continue
                if self._cursor >= len(self._packets):
                    self._mismatches += 1
                    self._events.append({'status': 'EXTRA_REQUEST'})
                    continue
                request, response, sequence = self._packets[self._cursor]
                if data != request:
                    self._mismatches += 1
                    self._events.append({'status': 'REQUEST_MISMATCH', 'expected_datagram_sequence': sequence})
                    continue
                self._peer = peer
                if response:
                    try:
                        self._socket.sendto(response, peer)
                    except OSError as exc:
                        self._events.append({'status': 'SEND_ERROR', 'message': str(exc)})
                        self._stop.set()
                        break
                self._cursor += 1
                self._events.append({'status': 'REPLIED' if response else 'DROPPED',
                                     'recorded_datagram_sequence': sequence})

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()

"""Safe loopback demonstration used by the GUI and self-test."""

from __future__ import annotations

import socket
import time

from .model import VirtualSpitfire
from .protocol import decode_replies, encode_commands
from .records import CaptureStore
from .server import VirtualDeviceServer


DEMO_LINES = [
    "[1000]*idn?",
    "[1009]EMP:DIODE:CURR?",
    "[1010]EMP:QSW:PRF?",
    "[2004]EMP:QSW:PRF 125.00",
    "[1010]EMP:QSW:PRF?",
    "[2019]TDG:DEL 1 12.5",
    "[1045]TDG:DEL1?",
    "[2006]EMP:OFF",
    "[1013]EMP:STB?",
]


def _client() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    return sock


def _send(sock: socket.socket, target: tuple[str, int], lines: list[str]) -> None:
    sock.sendto(encode_commands(lines), target)
    data, sender = sock.recvfrom(4096)
    if sender != target:
        raise RuntimeError(f"unexpected demo reply endpoint: {sender}")
    replies = decode_replies(data)
    if len(replies) != len(lines):
        raise RuntimeError("demo reply count mismatch")


def run_loopback_demo(capture: CaptureStore, original_label: str, python_label: str) -> VirtualSpitfire:
    """Generate equivalent traffic with different UDP batching strategies."""
    left, right = _client(), _client()
    try:
        labels = {
            f"127.0.0.1:{left.getsockname()[1]}": original_label,
            f"127.0.0.1:{right.getsockname()[1]}": python_label,
        }
        device = VirtualSpitfire(isolated_clients=True)
        with VirtualDeviceServer("127.0.0.1", 0, device, capture, labels) as server:
            target = server.local_address
            if target is None:
                raise RuntimeError("demo server did not bind")
            # Legacy-style batching versus Python one-command exchanges.
            _send(left, target, DEMO_LINES[:3])
            for line in DEMO_LINES[3:]:
                _send(left, target, [line])
            for line in DEMO_LINES:
                _send(right, target, [line])
            deadline = time.monotonic() + 2.0
            while len(capture.transactions()) < len(DEMO_LINES) * 2 and time.monotonic() < deadline:
                time.sleep(0.01)
        return device
    finally:
        left.close()
        right.close()

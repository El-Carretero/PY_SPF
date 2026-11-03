"""Wire codec for the Spectra-Physics ECLIPSE UDP protocol."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


COMMAND_HEADER = b"Spectra-Physics:CMD_ECLIPSE,"
REPLY_MARKER = "REPLY_ECLIPSE"
MAX_DATAGRAM = 1400
_REPLY_RE = re.compile(r"^\s*<(?P<id>\d+)>\s?(?P<value>.*)$")
_COMMAND_RE = re.compile(r"^\[(?P<id>\d+)](?P<command>.*)$")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Reply:
    command_id: int
    value: str
    raw_line: str


@dataclass(frozen=True, slots=True)
class WireCommand:
    command_id: int
    command: str


def encode_datagram(lines: Iterable[str]) -> bytes:
    clean: list[str] = []
    for line in lines:
        line = line.rstrip("\r\n")
        if not line:
            continue
        if "\r" in line or "\n" in line:
            raise ProtocolError("A command must occupy exactly one line")
        if not _COMMAND_RE.match(line):
            raise ProtocolError(f"Malformed command line: {line!r}")
        clean.append(line)
    if not clean:
        raise ProtocolError("Cannot encode an empty command datagram")
    try:
        encoded_lines = ("\n".join(clean) + "\n").encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise ProtocolError("The legacy controller protocol accepts ASCII only") from exc
    payload = COMMAND_HEADER + encoded_lines
    if len(payload) > MAX_DATAGRAM:
        raise ProtocolError(f"Datagram is {len(payload)} bytes; legacy maximum is {MAX_DATAGRAM}")
    return payload


def split_datagrams(lines: Iterable[str]) -> list[bytes]:
    """Pack lines into legacy-compatible datagrams without crossing 1400 bytes."""
    packets: list[bytes] = []
    current: list[str] = []
    for line in lines:
        candidate = current + [line]
        try:
            encode_datagram(candidate)
        except ProtocolError as exc:
            if "legacy maximum" not in str(exc) or not current:
                raise
            packets.append(encode_datagram(current))
            current = [line]
            encode_datagram(current)
        else:
            current = candidate
    if current:
        packets.append(encode_datagram(current))
    return packets


def decode_command_datagram(data: bytes | str) -> list[WireCommand]:
    """Decode client packets; primarily used by the deterministic simulator."""
    text = data.decode("ascii", "replace") if isinstance(data, bytes) else data
    if not text.startswith(COMMAND_HEADER.decode("ascii")):
        raise ProtocolError("Missing Spectra-Physics CMD_ECLIPSE header")
    body = text[len(COMMAND_HEADER):]
    result: list[WireCommand] = []
    for raw in body.splitlines():
        if not raw.strip():
            continue
        match = _COMMAND_RE.match(raw)
        if not match:
            raise ProtocolError(f"Malformed command line: {raw!r}")
        result.append(WireCommand(int(match.group("id")), match.group("command")))
    return result


def decode_reply_datagram(data: bytes | str) -> list[Reply]:
    """Decode ``<id>value`` reply lines from an ECLIPSE reply packet.

    The 1.6.0 receiver ignores the manufacturer text before the first colon,
    requires ``REPLY_ECLIPSE`` after it, and starts data after the next colon.
    That permissive behaviour is retained for controller compatibility.
    """
    text = data.decode("ascii", "replace") if isinstance(data, bytes) else data
    first = text.find(":")
    if first < 0:
        raise ProtocolError("Reply contains no header separator")
    marker_start = first + 1
    if not text.startswith(REPLY_MARKER, marker_start):
        raise ProtocolError("Reply is not an ECLIPSE reply")
    second = text.find(":", marker_start)
    if second < 0:
        raise ProtocolError("Reply contains no payload separator")
    result: list[Reply] = []
    for raw in text[second + 1 :].splitlines():
        if not raw.strip():
            continue
        match = _REPLY_RE.match(raw)
        if not match:
            raise ProtocolError(f"Malformed reply line: {raw!r}")
        result.append(Reply(int(match.group("id")), match.group("value").strip(), raw))
    return result


def encode_reply(replies: Iterable[tuple[int, object]]) -> bytes:
    lines = [f"<{command_id}>{value}" for command_id, value in replies]
    return ("Spectra-Physics:REPLY_ECLIPSE:" + "\n".join(lines) + "\n").encode("ascii")

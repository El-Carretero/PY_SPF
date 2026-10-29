"""ECLIPSE UDP wire codec used by both legacy and Python clients."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from .catalog import split_argument


COMMAND_HEADER = b"Spectra-Physics:CMD_ECLIPSE,"
REPLY_HEADER = b"Spectra-Physics:REPLY_ECLIPSE:"
MAX_DATAGRAM = 1400
_COMMAND_RE = re.compile(r"^\[(?P<id>\d+)](?P<command>.*)$")
_REPLY_RE = re.compile(r"^\s*<(?P<id>\d+)>\s?(?P<value>.*)$")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WireCommand:
    command_id: int
    command: str
    base: str
    argument: str
    raw_line: str


@dataclass(frozen=True, slots=True)
class WireReply:
    command_id: int
    value: str
    raw_line: str


def decode_commands(data: bytes) -> list[WireCommand]:
    if len(data) > MAX_DATAGRAM:
        raise ProtocolError(f"datagram exceeds recovered {MAX_DATAGRAM}-byte limit")
    if not data.startswith(COMMAND_HEADER):
        raise ProtocolError("missing Spectra-Physics:CMD_ECLIPSE, header")
    try:
        text = data[len(COMMAND_HEADER):].decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise ProtocolError("command datagram is not ASCII") from exc
    result: list[WireCommand] = []
    for raw in text.split("\n"):
        if raw.endswith("\r"):
            raw = raw[:-1]
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
            raise ProtocolError("unsupported control character in command")
        if not raw.strip():
            continue
        match = _COMMAND_RE.fullmatch(raw)
        if not match:
            raise ProtocolError(f"malformed command line: {raw!r}")
        command_id = int(match.group("id"))
        command = match.group("command")
        base, argument = split_argument(command_id, command)
        result.append(WireCommand(command_id, command, base, argument, raw))
    if not result:
        raise ProtocolError("command datagram has no command lines")
    return result


def encode_commands(lines: Iterable[str]) -> bytes:
    body = "\n".join(line.rstrip("\r\n") for line in lines) + "\n"
    try:
        packet = COMMAND_HEADER + body.encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise ProtocolError("commands must be ASCII") from exc
    if len(packet) > MAX_DATAGRAM:
        raise ProtocolError(f"datagram exceeds recovered {MAX_DATAGRAM}-byte limit")
    decode_commands(packet)
    return packet


def encode_replies(replies: Iterable[tuple[int, object]], *, line_ending: str = "\n",
                   header: bytes = REPLY_HEADER) -> bytes:
    lines = [f"<{command_id}>{value}" for command_id, value in replies]
    try:
        return header + (line_ending.join(lines) + line_ending).encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise ProtocolError("reply values must be ASCII") from exc


def decode_replies(data: bytes) -> list[WireReply]:
    try:
        text = data.decode("ascii", "strict")
    except UnicodeDecodeError as exc:
        raise ProtocolError("reply datagram is not ASCII") from exc
    if not data.startswith(REPLY_HEADER):
        raise ProtocolError("missing exact Spectra-Physics:REPLY_ECLIPSE: header")
    first = text.find(":")
    if first < 0 or not text.startswith("REPLY_ECLIPSE", first + 1):
        raise ProtocolError("missing REPLY_ECLIPSE marker")
    second = text.find(":", first + 1)
    if second < 0:
        raise ProtocolError("reply has no payload separator")
    result: list[WireReply] = []
    for raw in text[second + 1:].splitlines():
        if not raw.strip():
            continue
        match = _REPLY_RE.fullmatch(raw)
        if not match:
            raise ProtocolError(f"malformed reply line: {raw!r}")
        result.append(WireReply(int(match.group("id")), match.group("value").strip(), raw))
    return result

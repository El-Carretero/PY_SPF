"""Empower binary framing recovered from the supplied 3.02.00 executable.

See docs/PROTOCOL.md for evidence and limits. No ASCII command substitution.
"""
from dataclasses import dataclass

SYNC = b"\x10\x02"


class ProtocolError(Exception):
    pass


@dataclass(frozen=True)
class Frame:
    raw: bytes

    @property
    def opcode(self) -> int:
        return self.raw[5]

    @property
    def payload(self) -> bytes:
        """Response body including the trailer, if any.

        The device layer negotiates RX validation from the firmware response.
        For a known TX frame, explicitly omit its checksum when needed.
        """
        return self.raw[6:]


def encode(opcode: int, payload: bytes = b"\x02") -> bytes:
    length = 7 + len(payload)
    if not 0 <= opcode <= 255 or not 8 <= length <= 255:
        raise ValueError("Invalid opcode or packet length")
    body = SYNC + b"\x00\x00" + bytes((length, opcode)) + payload
    return body + bytes((sum(body) & 0xFF,))


def decode(raw: bytes, *, verify_checksum: bool = True) -> Frame:
    if len(raw) < 8 or raw[:2] != SYNC or raw[4] != len(raw):
        raise ProtocolError("Invalid packet header or length")
    if verify_checksum and (sum(raw[:-1]) & 0xFF) != raw[-1]:
        raise ProtocolError("Packet checksum mismatch")
    return Frame(bytes(raw))


class FrameBuffer:
    """Incremental decoder; retains fragments and resynchronizes after noise."""
    def __init__(self, *, verify_checksum=False):
        self.buffer = bytearray()
        self.rejected = 0
        # Static EXE analysis did not settle RX checksum format. Device learns
        # the captured checksummed layout from the initial firmware response;
        # it validates checksum and complete payload length before decoding.
        self.verify_checksum = verify_checksum

    def feed(self, chunk: bytes) -> list[Frame]:
        self.buffer.extend(chunk)
        frames = []
        while self.buffer:
            index = self.buffer.find(SYNC)
            if index < 0:
                self.buffer[:] = b"\x10" if self.buffer[-1:] == b"\x10" else b""
                break
            if index:
                del self.buffer[:index]
            if len(self.buffer) < 5:
                break
            length = self.buffer[4]
            if length < 8:
                self.rejected += 1
                del self.buffer[0]
                continue
            if len(self.buffer) < length:
                break
            raw = bytes(self.buffer[:length])
            try:
                frame = decode(raw, verify_checksum=self.verify_checksum)
            except ProtocolError:
                self.rejected += 1
                del self.buffer[0]
                continue
            del self.buffer[:length]
            frames.append(frame)
        return frames

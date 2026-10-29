"""Protocol recovered statically from Spitfire GUI 1.6.0 (2005 native PE).

No connection is opened by importing this module. The original active path is
ASCII UDP; CRC helpers below belong to the binary's separate legacy functions.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import socket

DEFAULT_ADDRESS = "10.19.70.13"
DEFAULT_PORT = 1024
PACKET_PREFIX = b"Spectra-Physics:CMD_ECLIPSE,"
MAX_PACKET_SIZE = 1400
QUERIES = {1000: '*idn?', 1001: 'MIL:DIODE1:CURR?', 1002: 'MIL:DIODE2:CURR?', 1003: 'MIL:POW?', 1004: 'MIL:READ:DIODE1:CURR?', 1005: 'MIL:READ:DIODE2:CURR?', 1006: 'MIL:READ:POW?', 1007: 'EMP:READ:DIODE:CURR?', 1008: 'EMP:READ:POW?', 1009: 'EMP:DIODE:CURR?', 1010: 'EMP:QSW:PRF?', 1011: 'EMP:QSW:PWID?', 1012: 'EMP:QSW:SOURCE?', 1013: 'EMP:STB?', 1014: 'EMP:FAULT?', 1015: 'HED:STB?', 1016: 'EMP:VERSION?', 1017: 'HED:MOTOR:*IDN?', 1018: 'HED:MOTOR:SPEED?', 1019: 'TDG:STB?', 1020: 'TDG:VOLT?', 1021: 'TDG:HV:ON?', 1022: 'TDG:STAT:BWD?', 1023: 'TDG:STBH?', 1024: 'TDG:OSC:FREQ?', 1025: 'TDG:DIV?', 1026: 'TDG:DEL', 1027: 'TDG:BWD?', 1028: 'ECU:STB?', 1029: 'ECU:STBH?', 1030: 'ECU:READTEMP?', 1031: 'ECU:HUM?', 1032: 'ECU:TEMP?', 1033: 'ECUOPTOUT?', 1034: 'HED:VERS?', 1035: 'EMP:VERS?', 1036: 'TDG:VERS?', 1037: 'ECU:VERS?', 1038: '*IDN?', 1039: 'TDG:STBH?', 1040: 'TDG:HV1:VOLT?', 1041: 'TDG:HV2:VOLT?', 1042: 'TDG:READ:HV1VOLT?', 1043: 'TDG:READ:HV2VOLT?', 1044: 'ECU:HUMOVERRIDE?', 1045: 'TDG:DEL1?', 1046: 'TDG:DEL2?', 1047: 'TDG:DEL3?', 1048: 'TDG:DEL4?', 1049: 'TDG:DEL5?', 1050: 'TDG:OSC:MODE?', 1051: 'TDG:TRIG:MODE?', 1052: 'TDG:DEL0?', 1053: 'TDG:TRIG:FREQ?', 1054: 'TDG:BWD?', 1055: 'TDG:READ:HV1CURR?', 1056: 'TDG:READ:HV2CURR?', 1057: 'ECU:STBH?', 1058: 'TDG:DEL1?', 1059: 'TDG:DEL2?', 1060: 'HED:MOTOR:SPEED?', 1061: 'TDG:HV:ON?', 1062: '*IDN?', 1063: 'TDG:DEL1?', 1064: 'TDG:DEL2?', 1065: 'TDG:READ:OSCQUEST?', 1066: 'TDG:STBHFLT?', 1067: 'TDG:OSC:MODE?', 1068: 'EMPOPTOUT?', 1069: 'HEDOPTOUT?', 1070: 'EMP:SECRETMSG1?', 1071: 'EMP:SECRETMSG2?', 1072: 'EMP:SECRETMSG3?', 1073: 'EMP:SECRETMSG4?', 1074: 'EMP:SECRETMSG5?', 1075: 'EMP:SECRETMSG6?', 1076: 'EMP:SECRETMSG7?', 1077: 'EMP:LBOTEMP?', 1078: 'EMP:LBOBREAK?', 1079: 'TDG:TRIG?', 1080: 'TDG:OSC:SETMODE?', 1081: '*IDN?', 1082: '*IdN?', 1083: 'TDG:DELMON?', 1084: 'ECU:TECTEMP?', 1085: 'STATUS?', 1086: 'MONITOR?', 1087: 'TDG:FAULTOVERRIDE?', 1088: 'ECU:STBH?', 1089: 'COMSTATUS?'}
COMMANDS = {2000: 'MIL:DIODE1:CURR', 2001: 'MIL:DIODE2:CURR', 2002: 'MIL:READ:POW', 2003: 'EMP:DIODE:CURR', 2004: 'EMP:QSW:PRF', 2005: 'EMP:ON', 2006: 'EMP:OFF', 2007: 'EMP:QSW:PWID', 2008: 'EMP:QSW:SOURCE', 2009: 'HED:MOTOR:REW', 2010: 'HED:MOTOR:FWD', 2011: 'HED:MOTOR:JOGF', 2012: 'HED:MOTOR:JOGR', 2013: 'HED:MOTOR:STOP', 2014: 'HED:MOTOR:SPEED', 2015: 'TDG:VOLT', 2016: 'TDG:HV:OFF', 2017: 'TDG:HV:ON', 2018: 'TDG:RESBWD', 2019: 'TDG:DEL', 2020: 'TDG:DIV', 2021: 'ECU:TEMP', 2022: 'ECU:TECON', 2023: 'ECU:TECOFF', 2024: 'ECUOPTOUT', 2025: 'TDG:HV1:VOLT', 2026: 'TDG:HV2:VOLT', 2027: 'ON', 2028: 'OFF', 2029: 'ECU:HUMOVERRIDE', 2030: 'TDG:OSC:MODE', 2031: 'TDG:TRIG:MODE', 2032: 'TDG:TRIG:FREQ', 2033: 'TDG:BWD', 2034: '', 2035: 'HEDOPTOUT', 2036: 'EMPOPTOUT', 2037: 'EMP:SECRETMSG1', 2038: 'EMP:SECRETMSG2', 2039: 'EMP:SECRETMSG3', 2040: 'EMP:SECRETMSG4', 2041: 'EMP:SECRETMSG5', 2042: 'EMP:SECRETMSG6', 2043: 'EMP:SECRETMSG7', 2044: 'EMP:RESETFAULTS', 2045: 'EMP:SECRETSCOMT', 2046: 'TDG:OSC:SETTOFRQ', 2047: 'EMP:LBOBREAK', 2048: 'TDG:OSC:SETMODE', 2049: 'ECU:RESETFAULTS', 2050: 'RESET', 2051: 'MONITOR', 2052: 'TDG:RESFAULT', 2053: 'TDG:FAULTOVERRIDE', 2054: 'RES12', 2055: 'CLEAR'}
INITIAL_SEQUENCES = {'_push_initial_updates': [1069, 1068, 1087, 1033, 1038, 1062], '_push_initial_updates_ecu': [1037, 1032, 1057], '_push_initial_updates_mil': [1034, 1060], '_push_initial_updates_tdg': [1086, 1036, 1045, 1046, 1047, 1048, 1049, 1040, 1041, 1024, 1025, 1052, 1053, 1054, 1067, 1051, 1053, 1080], '_push_initial_updates_emp': [1035, 1009, 1010, 1011, 1012, 1053, 1071, 1072, 1073, 1074, 1075, 1076, 2047, 1078], '_push_usual_auto_updates': [2054, 1039, 1056, 1039, 1055, 1039, 1042, 1039, 1043, 1039, 1015, 1039, 1019, 1039, 1013, 1039, 1028, 1039, 1007, 1039, 1008, 1039, 1029, 1039, 1030, 1039, 1065, 1039, 1031, 1039, 1021, 1039, 1077, 1039, 1084, 1039, 1085, 1039]}

def format_message(tag: int, parameter: str = "") -> str:
    """Reproduce _update_string, including its parameter spacing contract.

    `parameter` is already formatted by the callback (usually begins with space).
    Neither CR nor LF is appended here. _WriteToUDP appends the LF separator.
    """
    title = (QUERIES if tag < 2000 else COMMANDS)[tag]
    return f"[{tag}]{title}" + (parameter if tag >= 2000 or tag == 1026 else "")


class PacketBuffer:
    """_WriteToUDP batching plus _UDP_Refresh, without performing socket I/O."""
    def __init__(self) -> None:
        self.pending = b""

    def append(self, message: str) -> list[bytes]:
        data = message.encode("ascii")
        if len(data) > MAX_PACKET_SIZE:
            return []  # original silently ignores an individual oversized string
        flushed = []
        if len(self.pending) + len(data) > MAX_PACKET_SIZE:
            flushed.append(self.pending)
            self.pending = b""
        if not self.pending:
            self.pending = PACKET_PREFIX
        self.pending += data + b"\n"
        return flushed

    def flush(self) -> bytes | None:
        if not self.pending:
            return None
        result, self.pending = self.pending, b""
        return result


@dataclass(frozen=True)
class ReplyLine:
    packet: int
    line: int
    body: str
    decorated: str


def parse_datagram(data: bytes, packet_number: int = 1) -> list[ReplyLine]:
    """Reproduce _UDP_Analyze_Received_Packet / _Add_String_Answer_from_Command.

    Matching ignores the text before the first colon and accepts any suffix
    following REPLY_ECLIPSE, as the original strncmp does. A second colon marks
    the body. Empty lines are ignored; CR, LF and NUL are line boundaries.
    """
    data = data.rstrip(b"\r\n").split(b"\0", 1)[0]
    first = data.find(b":")
    if first < 0 or not data[first + 1:].startswith(b"REPLY_ECLIPSE"):
        return []
    start = first + 1
    second = data.find(b":", start)
    if second >= 0:
        start = second + 1
    body = data[start:]
    lines = []
    # C strlen bounds the loop; an embedded NUL has already terminated data.
    for line in body.replace(b"\r", b"\n").split(b"\n"):
        if not line:
            continue
        number = len(lines) + 1
        prefix = f"({packet_number},{number})"
        text = line[:max(0, 198 - len(prefix))].decode("latin1")
        lines.append(ReplyLine(packet_number, number, text, prefix + text))
    return lines


class QueueScheduler:
    """Original two FIFOs: inside queue has priority; one in-flight message."""
    def __init__(self) -> None:
        self.inside: deque[str] = deque()
        self.outside: deque[str] = deque()
        self.balance = 0

    def push(self, tag: int, parameter: str = "", *, inside: bool = False) -> None:
        # Original queue copies exactly 30 bytes; preserve normal short strings.
        message = format_message(tag, parameter)
        (self.inside if inside else self.outside).append(message[:30])

    def next_message(self) -> str | None:
        if self.balance:
            return None
        queue = self.inside if self.inside else self.outside
        if not queue:
            return None
        self.balance += 1
        return queue.popleft()

    def acknowledge(self) -> None:
        self.balance = max(0, self.balance - 1)


def crc16(data: bytes, initial: int = 0) -> int:
    """_CalculateBlockCRC16: non-reflected polynomial 0x1021, no final XOR."""
    crc = initial & 0xffff
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    return crc


def calc_crc16_c_string(data: bytes, initial: int = 0) -> int:
    """_CalcCrc16: same polynomial, stops at first NUL; signed-short result."""
    crc = crc16(data.split(b"\0", 1)[0], initial)
    return crc - 0x10000 if crc & 0x8000 else crc


def crc32(data: bytes, initial: int = 0) -> int:
    """_CalculateBlockCRC32: reflected 0xEDB88320, no initial/final XOR."""
    crc = initial & 0xffffffff
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xedb88320 if crc & 1 else 0)
    return crc


class UDPTransport:
    """Explicitly opened UDP transport, corresponding to the original socket.

    Caller owns connection decisions, queue scheduling, retries and decoding.
    No physical device commands are sent without an explicit send call.
    """
    def __init__(self, address: str = DEFAULT_ADDRESS, port: int = DEFAULT_PORT,
                 bind_port: int = DEFAULT_PORT, timeout: float = 1.0) -> None:
        self.address, self.port = address, port
        self.bind_port, self.timeout = bind_port, timeout
        self.socket: socket.socket | None = None
        self.packet_counter = 0
        self.expected_peer: tuple[str, int] | None = None

    def open(self) -> None:
        self.expected_peer = (socket.gethostbyname(self.address), self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", self.bind_port))
        sock.settimeout(self.timeout)
        self.socket = sock

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def send_packet(self, packet: bytes) -> None:
        if self.socket is None:
            raise RuntimeError("UDP transport is not open")
        self.socket.sendto(packet, self.expected_peer or (self.address, self.port))

    def discard_pending(self) -> None:
        """Drain replies queued before the next request, not its proof.

        IDs identify commands, not transactions. A same-ID datagram delayed
        until after the new request cannot be distinguished by this protocol.
        """
        if self.socket is None:
            return
        timeout = self.socket.gettimeout()
        self.socket.setblocking(False)
        try:
            for _ in range(256):
                try:
                    self.socket.recvfrom(1495)
                except BlockingIOError:
                    return
            raise OSError('Receive queue did not drain; refusing a new request')
        finally:
            self.socket.settimeout(timeout)

    def receive(self) -> list[ReplyLine]:
        if self.socket is None:
            raise RuntimeError("UDP transport is not open")
        try:
            data, sender = self.socket.recvfrom(1495)
        except (socket.timeout, BlockingIOError):
            return []
        if self.expected_peer is not None and sender != self.expected_peer:
            return []
        self.packet_counter += 1
        return parse_datagram(data, self.packet_counter)

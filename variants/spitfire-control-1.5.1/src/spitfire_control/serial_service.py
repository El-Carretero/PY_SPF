"""Raw RS-232 transport used only by the explicit service terminal.

This module intentionally does not know about the ECLIPSE/UDP protocol.  It
opens a serial port and moves bytes exactly as requested by the operator.
Keeping it separate prevents service-terminal traffic from being mixed with
normal laser-controller commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import queue
import re
import threading
from typing import Any, Callable, Iterable

try:  # A friendly runtime error is preferable to preventing the GUI starting.
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - exercised on installations without it
    serial = None  # type: ignore[assignment]
    list_ports = None  # type: ignore[assignment]


class SerialServiceError(RuntimeError):
    """An operator-facing serial-service error."""


@dataclass(frozen=True, slots=True)
class SerialSettings:
    port: str
    baudrate: int = 19_200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1.0
    timeout: float = 0.10
    write_timeout: float = 1.0
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False
    dtr: bool = False
    rts: bool = False

    def validate(self) -> None:
        if not self.port.strip():
            raise SerialServiceError("Serial port를 선택하십시오.")
        if not 50 <= self.baudrate <= 4_000_000:
            raise SerialServiceError("Baud rate 범위는 50–4,000,000입니다.")
        if self.bytesize not in (5, 6, 7, 8):
            raise SerialServiceError("Data bits는 5, 6, 7, 8 중 하나여야 합니다.")
        if self.parity.upper() not in ("N", "E", "O", "M", "S"):
            raise SerialServiceError("지원하지 않는 parity입니다.")
        if self.stopbits not in (1.0, 1.5, 2.0):
            raise SerialServiceError("Stop bits는 1, 1.5, 2 중 하나여야 합니다.")
        if not 0 <= self.timeout <= 10 or not 0 < self.write_timeout <= 30:
            raise SerialServiceError("Timeout 값을 확인하십시오.")


@dataclass(frozen=True, slots=True)
class SerialEvent:
    kind: str
    timestamp: datetime
    data: bytes = b""
    message: str = ""


_TERMINATORS = {
    "NONE": b"",
    "CR": b"\r",
    "LF": b"\n",
    "CRLF": b"\r\n",
}


def parse_hex_bytes(value: str) -> bytes:
    """Parse either a contiguous hex string or whitespace/comma byte tokens."""

    text = value.strip()
    if not text:
        return b""
    normalized = re.sub(r"0[xX]", "", text)
    if re.search(r"[\s,;:_-]", normalized):
        tokens = [part for part in re.split(r"[\s,;:_-]+", normalized) if part]
        if any(len(token) > 2 for token in tokens):
            raise SerialServiceError("HEX token은 한 byte(00–FF)여야 합니다.")
        normalized = "".join(token.zfill(2) for token in tokens)
    else:
        normalized = normalized.replace(" ", "")
    if len(normalized) % 2:
        raise SerialServiceError("HEX 입력은 짝수 개의 16진수 문자여야 합니다.")
    if not re.fullmatch(r"[0-9a-fA-F]*", normalized):
        raise SerialServiceError("HEX 입력에는 0–9, A–F만 사용할 수 있습니다.")
    return bytes.fromhex(normalized)


def encode_transmission(value: str, mode: str = "ASCII", terminator: str = "NONE") -> bytes:
    """Encode a terminal entry without adding any implicit protocol framing."""

    normalized_mode = mode.strip().upper()
    try:
        suffix = _TERMINATORS[terminator.strip().upper()]
    except KeyError as exc:
        raise SerialServiceError("지원하지 않는 line ending입니다.") from exc
    if normalized_mode == "HEX":
        payload = parse_hex_bytes(value)
    elif normalized_mode == "ASCII":
        try:
            payload = value.encode("ascii", errors="strict")
        except UnicodeEncodeError as exc:
            raise SerialServiceError("ASCII 모드에서는 영문/숫자 문자를 사용하십시오. 임의 byte는 HEX 모드를 사용하십시오.") from exc
    else:
        raise SerialServiceError("전송 형식은 ASCII 또는 HEX여야 합니다.")
    return payload + suffix


def available_serial_ports() -> list[str]:
    """Return stable, naturally sorted serial device names."""

    if list_ports is None:
        return []
    ports = {item.device for item in list_ports.comports() if getattr(item, "device", "")}

    def key(name: str) -> tuple[str, int, str]:
        match = re.match(r"^(.*?)(\d+)$", name)
        return (match.group(1).lower(), int(match.group(2)), name) if match else (name.lower(), -1, name)

    return sorted(ports, key=key)


class RawSerialSession:
    """Threaded byte stream with a queue safe for Tk's main loop."""

    def __init__(
        self,
        *,
        serial_factory: Callable[..., Any] | None = None,
        port_provider: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self.events: queue.Queue[SerialEvent] = queue.Queue()
        self._serial_factory = serial_factory
        self._port_provider = port_provider
        self._serial: Any | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        handle = self._serial
        return bool(handle is not None and getattr(handle, "is_open", True))

    def list_ports(self) -> list[str]:
        if self._port_provider is not None:
            return list(self._port_provider())
        return available_serial_ports()

    def connect(self, settings: SerialSettings) -> None:
        settings.validate()
        self.close()
        self._stop.clear()
        handle = None
        try:
            handle = self._open(settings)
            if getattr(handle, "is_open", False):
                raise SerialServiceError("Serial factory must return an unopened handle")
            # Configure requested control lines before opening the port. Opening
            # pySerial first can briefly assert its default DTR/RTS states.
            handle.dtr = settings.dtr
            handle.rts = settings.rts
            handle.open()
        except Exception as exc:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
            raise SerialServiceError(f"{settings.port} 열기 실패: {exc}") from exc
        self._serial = handle
        self.events.put(self._event("status", message=f"CONNECTED {settings.port} @ {settings.baudrate} {settings.bytesize}{settings.parity}{settings.stopbits:g}"))
        self._reader = threading.Thread(target=self._reader_loop, args=(handle,), name="spitfire-rs232-reader", daemon=True)
        self._reader.start()

    def _open(self, settings: SerialSettings) -> Any:
        """Construct an unopened port; injected test factories share this contract."""
        kwargs = {
            "port": settings.port,
            "baudrate": settings.baudrate,
            "bytesize": settings.bytesize,
            "parity": settings.parity.upper(),
            "stopbits": settings.stopbits,
            "timeout": settings.timeout,
            "write_timeout": settings.write_timeout,
            "xonxoff": settings.xonxoff,
            "rtscts": settings.rtscts,
            "dsrdtr": settings.dsrdtr,
        }
        if self._serial_factory is not None:
            return self._serial_factory(**kwargs)
        if serial is None:
            raise SerialServiceError("pyserial이 설치되지 않았습니다. release/vendor의 pyserial wheel을 설치하십시오.")
        port = kwargs.pop("port")
        return serial.serial_for_url(port, do_not_open=True, **kwargs)

    def send(self, data: bytes) -> int:
        if not data:
            raise SerialServiceError("전송할 byte가 없습니다.")
        handle = self._serial
        if handle is None or not self.connected:
            raise SerialServiceError("Serial port가 연결되지 않았습니다.")
        try:
            with self._write_lock:
                written = int(handle.write(data))
        except Exception as exc:
            raise SerialServiceError(f"Serial write 실패: {exc}") from exc
        if written != len(data):
            raise SerialServiceError(f"Serial write가 일부만 완료되었습니다 ({written}/{len(data)} bytes).")
        self.events.put(self._event("tx", data=data))
        return written

    def set_control_lines(self, *, dtr: bool, rts: bool) -> None:
        handle = self._serial
        if handle is None or not self.connected:
            return
        try:
            handle.dtr = bool(dtr)
            handle.rts = bool(rts)
        except Exception as exc:
            raise SerialServiceError(f"DTR/RTS 변경 실패: {exc}") from exc

    def close(self) -> None:
        self._stop.set()
        handle, self._serial = self._serial, None
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        reader, self._reader = self._reader, None
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=1.0)
        if handle is not None:
            self.events.put(self._event("status", message="DISCONNECTED"))

    def _reader_loop(self, handle: Any) -> None:
        while not self._stop.is_set() and self._serial is handle:
            try:
                waiting = int(getattr(handle, "in_waiting", 0) or 0)
                data = handle.read(min(max(waiting, 1), 4096))
            except Exception as exc:
                if not self._stop.is_set():
                    self.events.put(self._event("error", message=f"Serial read 실패: {exc}"))
                if self._serial is handle:
                    self._serial = None
                try:
                    handle.close()
                except Exception:
                    pass
                return
            if data:
                self.events.put(self._event("rx", data=bytes(data)))

    @staticmethod
    def _event(kind: str, *, data: bytes = b"", message: str = "") -> SerialEvent:
        return SerialEvent(kind=kind, timestamp=datetime.now(timezone.utc), data=data, message=message)

    def __enter__(self) -> "RawSerialSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

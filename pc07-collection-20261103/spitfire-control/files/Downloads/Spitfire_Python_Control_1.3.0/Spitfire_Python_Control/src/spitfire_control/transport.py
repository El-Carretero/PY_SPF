"""Real UDP and deterministic simulator transports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
import random
import socket
import threading
import time
from typing import Callable

from .commands import COMMANDS
from .protocol import ProtocolError, Reply, decode_command_datagram, decode_reply_datagram, encode_datagram, encode_reply


class TransportError(RuntimeError):
    pass


class CommandCancelled(TransportError):
    """Authorization was withdrawn before any bytes were sent."""


SendGuard = Callable[[Callable[[], None]], None]


class BaseTransport(ABC):
    name = "transport"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def exchange(self, command_line: str, timeout: float, *, send_guard: SendGuard | None = None) -> list[Reply]: ...


@dataclass(slots=True)
class UdpSettings:
    remote_host: str = "10.19.70.13"
    remote_port: int = 1024
    local_host: str = "0.0.0.0"
    local_port: int = 1024


class UdpTransport(BaseTransport):
    name = "UDP hardware"

    def __init__(self, settings: UdpSettings):
        self.settings = settings
        self._socket: socket.socket | None = None
        self._remote: tuple[str, int] | None = None

    def connect(self) -> None:
        if self._socket is not None:
            return
        if not 1 <= int(self.settings.remote_port) <= 65535:
            raise TransportError("Remote UDP port must be between 1 and 65535")
        if not 0 <= int(self.settings.local_port) <= 65535:
            raise TransportError("Local UDP port must be between 0 and 65535")
        sock = None
        try:
            remote_ip = socket.gethostbyname(self.settings.remote_host)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Refuse instrument receive-port sharing on Windows, including
            # another process that explicitly requested address reuse.
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((self.settings.local_host, int(self.settings.local_port)))
            self._remote = (remote_ip, int(self.settings.remote_port))
            self._socket = sock
        except OSError as exc:
            if sock is not None:
                sock.close()
            self.close()
            raise TransportError(f"Cannot open UDP transport: {exc}") from exc

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            finally:
                self._socket = None
                self._remote = None

    def exchange(self, command_line: str, timeout: float, *, send_guard: SendGuard | None = None) -> list[Reply]:
        sock, remote = self._socket, self._remote
        if sock is None or remote is None:
            raise TransportError("UDP transport is not connected")
        try:
            packet = encode_datagram([command_line])
        except ProtocolError as exc:
            raise TransportError(str(exc)) from exc
        expected = int(command_line[1 : command_line.index("]")])
        deadline = time.monotonic() + timeout
        try:
            send = lambda: sock.sendto(packet, remote)
            if send_guard is None:
                send()
            else:
                send_guard(send)
            collected: list[Reply] = []
            while time.monotonic() < deadline:
                sock.settimeout(max(0.01, deadline - time.monotonic()))
                data, sender = sock.recvfrom(2048)
                if sender != remote:
                    continue
                try:
                    replies = decode_reply_datagram(data)
                except ProtocolError:
                    # Shared instrument networks can contain discovery traffic;
                    # ignore packets that are not valid ECLIPSE replies.
                    continue
                # A one-command exchange only admits that command's reply.
                collected.extend(reply for reply in replies if reply.command_id == expected)
                if any(reply.command_id == expected for reply in replies):
                    return collected
        except socket.timeout as exc:
            raise TransportError(f"Timed out waiting for reply to command {expected}") from exc
        except OSError as exc:
            raise TransportError(str(exc)) from exc
        raise TransportError(f"Timed out waiting for reply to command {expected}")


class SimulatorTransport(BaseTransport):
    """A stateful simulator for UI development and operator training.

    It intentionally models nominal behaviour rather than laser physics. No
    network socket, serial server, TTL signal or optical pulse is produced.

    The optional missing-device and unsupported-command scenarios are synthetic
    test fixtures, not a specification of any TDG firmware. Injected faults are
    active sources: a reset cannot erase them until the test removes the source.
    """

    name = "Simulator"

    def __init__(self, seed: int = 160, *, empower_present: bool = True,
                 opt_out_supported: bool = True, mixed_faults_supported: bool = True,
                 empower_faults_supported: bool | None = None):
        self.empower_present = empower_present
        self.opt_out_supported = opt_out_supported
        # Retain the old constructor spelling for test-client compatibility.
        # Command 1014 is Empower-only, not a mixed system-fault query.
        self.empower_faults_supported = (mixed_faults_supported if empower_faults_supported is None
                                        else empower_faults_supported)
        self.command_history: list[tuple[int, str]] = []
        self._active_empower_faults = (0, 0, 0, 0)
        self._active_tdg_fault = 0
        self._active_tcu_fault = 0
        self._active_comm_status = 0
        self._seed_frequency_mhz = 80.0
        self._osc_reference_mhz = 80.0
        self._connected = False
        self._lock = threading.Lock()
        self._rng = random.Random(seed)
        self._started = time.monotonic()
        self._delay_modes = {
            channel: {"value": 0.0, "switch": "off", "bwd": "BWD", "enable": "ENA"}
            for channel in range(1, 6)
        }
        self._values: dict[int, object] = {
            1000: "Spectra-Physics,Spitfire,0,SIM-1.0",
            1007: 0.0, 1008: 0.0, 1009: 18.0, 1010: 100.0,
            1011: 120.0, 1012: 0, 1013: 0, 1014: "0 0 0 0",
            1015: 0, 1018: 100, 1019: 0, 1021: 0, 1024: 80.0,
            1025: 1, 1028: 0, 1029: 0, 1030: 25.0, 1031: 34.0,
            1032: 25.0, 1033: 0, 1034: "HED-SIM-1.0", 1035: "EMP-SIM-1.0",
            1036: "TDG-SIM-1.0", 1037: "ECU-SIM-1.0",
            1038: "Spectra-Physics,Spitfire,0,SIM-1.0", 1039: 0,
            1040: 650.0, 1041: 650.0, 1042: 0.0, 1043: 0.0,
            1044: 0, 1045: 0.0, 1046: 0.0, 1047: 0.0, 1048: 0.0,
            1049: 0.0, 1050: 0, 1051: 0, 1052: 0.0, 1053: 1000.0,
            1054: 0, 1055: 0.0, 1056: 0.0, 1057: 0, 1060: 100,
            1061: 0, 1062: "Spectra-Physics,Spitfire,0,SIM-1.0",
            1065: 80.0, 1066: 0, 1067: 0, 1068: 0, 1069: 0,
            1070: "0", 1071: "45.0", 1072: "1.0", 1073: "0.0",
            1074: "100.0", 1075: "55.0", 1076: "15.0", 1077: 43.0,
            1078: 0, 1080: 0, 1081: "SIM", 1082: "SIM", 1083: 0,
            1084: 25.2, 1085: 0, 1086: 0, 1087: 0, 1088: 0, 1089: 0,
        }

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False

    @property
    def mixed_faults_supported(self) -> bool:
        """Compatibility alias; it controls only the Empower fault query."""
        return self.empower_faults_supported

    @mixed_faults_supported.setter
    def mixed_faults_supported(self, value: bool) -> None:
        self.empower_faults_supported = value

    def inject_empower_faults(self, words: tuple[int, ...] | list[int]) -> None:
        """Replace active Empower-only fault words; missing hardware stays absent."""
        words = tuple(words)
        if len(words) != 4 or any(type(word) is not int or word < 0 for word in words):
            raise ValueError("Empower faults require four nonnegative integer words")
        with self._lock:
            self._active_empower_faults = words
            self._values[1014] = " ".join(str(word) for word in words)

    def inject_mixed_faults(self, words: tuple[int, ...] | list[int]) -> None:
        """Deprecated compatibility alias for inject_empower_faults()."""
        self.inject_empower_faults(words)

    @staticmethod
    def _validate_fault_value(value: int, name: str) -> None:
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")

    def inject_tdg_fault(self, value: int) -> None:
        """Replace the active synthetic TDG fault source (1066)."""
        self._validate_fault_value(value, "TDG fault")
        with self._lock:
            self._active_tdg_fault = value
            self._values[1066] = value

    def inject_tcu_fault(self, value: int) -> None:
        """Replace the active synthetic TCU fault source (1057 / 1088)."""
        self._validate_fault_value(value, "TCU fault")
        with self._lock:
            self._active_tcu_fault = value
            self._values[1057] = self._values[1088] = value

    def inject_comm_status(self, value: int) -> None:
        """Replace COMSTATUS; a reset is not evidence of restored communication."""
        self._validate_fault_value(value, "Communication status")
        with self._lock:
            self._active_comm_status = value
            self._values[1089] = value

    def inject_tdg_status(self, value: int) -> None:
        """Replace the raw synthetic TDG health/BWD status (1039)."""
        self._validate_fault_value(value, "TDG status")
        with self._lock:
            self._values[1039] = value

    def set_seed_frequency(self, mhz: float) -> None:
        """Set observed seed-frequency fixture; zero represents no seed clock.

        This test input is independent of software oscillator-reference writes.
        A stable value makes missing-signal and acceptance-boundary tests exact.
        """
        try:
            value = float(mhz)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Seed frequency must be finite and nonnegative") from exc
        if isinstance(mhz, bool) or not math.isfinite(value) or value < 0:
            raise ValueError("Seed frequency must be finite and nonnegative")
        with self._lock:
            self._seed_frequency_mhz = value
            self._values[1065] = value

    def _scenario_error(self, command_id: int) -> str | None:
        if command_id in {1068, 2036} and not self.opt_out_supported:
            return "ERR EMPOPTOUT unsupported (simulated firmware)"
        spec = COMMANDS[command_id]
        empower_only = spec.text.startswith("EMP:") or command_id in {2027, 2028}
        if not self.empower_present and empower_only:
            return "ERR Empower not present (simulation)"
        if command_id == 1014 and not self.empower_faults_supported:
            return "ERR Empower fault query unavailable (simulated firmware)"
        return None

    def _reset_faults(self, command_id: int) -> None:
        # Synthetic, separately owned diagnostic sources. EMP:FAULT? contains
        # only Empower words; neither a TCU nor a TDG reset may touch them.
        # The XP decoder's known Empower masks are retained here. Unmapped bits
        # stay visible, and active injected sources survive every reset.
        if command_id in {2044, 2050, 2055}:
            masks = (0x7B, 0xFE, 0x13, 0xFFFFFFFF)
            words = tuple(int(word) for word in str(self._values[1014]).split())
            self._values[1014] = " ".join(
                str((word & ~mask) | active)
                for word, mask, active in zip(words, masks, self._active_empower_faults)
            )
        if command_id in {2052, 2050, 2055}:
            self._values[1066] = self._active_tdg_fault
        if command_id in {2049, 2050, 2055}:
            self._values[1057] = self._values[1088] = self._active_tcu_fault
        # Communication status is observational. Do not clear it on any reset.

    def _tick(self) -> None:
        laser = self.empower_present and bool(self._values[1013])
        hv = bool(self._values[1021])
        target_current = float(self._values[1009]) if laser else 0.0
        current = float(self._values[1007])
        self._values[1007] = current + (target_current - current) * 0.22
        self._values[1008] = max(0.0, float(self._values[1007]) * (0.41 if laser else 0.0))
        target_hv1 = float(self._values[1040]) if hv else 0.0
        target_hv2 = float(self._values[1041]) if hv else 0.0
        self._values[1042] = float(self._values[1042]) + (target_hv1 - float(self._values[1042])) * 0.3
        self._values[1043] = float(self._values[1043]) + (target_hv2 - float(self._values[1043])) * 0.3
        self._values[1055] = (float(self._values[1042]) / 1000.0) if hv else 0.0
        self._values[1056] = (float(self._values[1043]) / 1000.0) if hv else 0.0
        elapsed = time.monotonic() - self._started
        set_temp = float(self._values[1032])
        self._values[1030] = set_temp + math.sin(elapsed / 8.0) * 0.08
        self._values[1084] = set_temp + 0.2 + math.sin(elapsed / 10.0) * 0.05
        self._values[1031] = 34.0 + math.sin(elapsed / 13.0) * 0.3
        self._values[1065] = self._seed_frequency_mhz

    @staticmethod
    def _argument(command: str, base: str) -> str:
        return command[len(base):].strip()

    def _set_numeric(self, query_id: int, value: str) -> None:
        try:
            self._values[query_id] = float(value)
        except ValueError as exc:
            raise TransportError(f"Simulator rejected non-numeric argument: {value!r}") from exc

    def _apply_write(self, command_id: int, command: str) -> str:
        base = COMMANDS[command_id].text
        arg = self._argument(command, base)
        numeric_targets = {
            2003: 1009, 2004: 1010, 2007: 1011, 2008: 1012,
            2014: 1060, 2020: 1025, 2021: 1032, 2025: 1040,
            2026: 1041, 2032: 1053,
        }
        if command_id in numeric_targets:
            self._set_numeric(numeric_targets[command_id], arg)
        elif command_id in {2005, 2027}:
            self._values[1013] = 1
        elif command_id in {2006, 2028}:
            self._values[1013] = 0
        elif command_id == 2017:
            self._values[1021] = self._values[1061] = 1
        elif command_id == 2016:
            self._values[1021] = self._values[1061] = 0
        elif command_id == 2019:
            tokens = arg.split()
            if len(tokens) >= 2:
                try:
                    channel = int(tokens[0])
                except ValueError as exc:
                    raise TransportError(f"Invalid delay channel: {tokens[0]!r}") from exc
                if channel not in self._delay_modes:
                    raise TransportError(f"Delay channel must be 1..5, got {channel}")
                setting = " ".join(tokens[1:])
                upper = setting.upper()
                if upper in {"ON", "OFF"}:
                    self._delay_modes[channel]["switch"] = upper.lower()
                elif upper in {"BWD", "NBWD"}:
                    self._delay_modes[channel]["bwd"] = upper
                elif upper in {"ENA", "NENA"}:
                    self._delay_modes[channel]["enable"] = upper
                else:
                    try:
                        self._delay_modes[channel]["value"] = float(setting)
                        self._values[1044 + channel] = float(setting)
                    except ValueError as exc:
                        raise TransportError(f"Invalid channel setting: {setting!r}") from exc
        elif command_id == 2022:
            self._values[1028] = 1
        elif command_id == 2023:
            self._values[1028] = 0
        elif command_id == 2024:
            self._values[1033] = int(float(arg))
        elif command_id == 2029:
            self._values[1044] = int(float(arg))
        elif command_id == 2030:
            self._values[1050] = 1 if arg.upper().startswith("EXT") else 0
            self._values[1067] = self._values[1050]
        elif command_id == 2031:
            self._values[1051] = 1 if arg.upper().startswith("EXT") else 0
        elif command_id == 2035:
            self._values[1069] = int(float(arg))
        elif command_id == 2036:
            if arg not in {"0", "1"}:
                raise TransportError("Simulator opt-out requires 0 or 1")
            self._values[1068] = int(arg)
        elif command_id == 2047:
            self._values[1078] = int(float(arg))
        elif command_id == 2048:
            self._values[1080] = {"CONT": 0, "COUNT": 1, "COUNT 1": 2}.get(arg.upper(), 0)
        elif command_id == 2046:
            # A reference-setting command cannot create a measured optical signal.
            self._osc_reference_mhz = float(arg)
        elif 2038 <= command_id <= 2043:
            self._set_numeric(1069 + (command_id - 2038) + 2, arg)
        elif command_id == 2045:
            pass
        elif command_id in {2044, 2049, 2050, 2052, 2055}:
            self._reset_faults(command_id)
        elif command_id == 2053:
            self._values[1087] = int(float(arg))
        return "OK"

    def exchange(self, command_line: str, timeout: float, *, send_guard: SendGuard | None = None) -> list[Reply]:
        del timeout
        if not self._connected:
            raise TransportError("Simulator is not connected")
        decoded = decode_command_datagram(encode_datagram([command_line]))[0]
        result: list[Reply] = []

        def perform() -> None:
            with self._lock:
                self.command_history.append((decoded.command_id, decoded.command))
                self._tick()
                error = self._scenario_error(decoded.command_id)
                if error is not None:
                    value = error
                elif decoded.command_id >= 2000:
                    value = self._apply_write(decoded.command_id, decoded.command)
                elif 1045 <= decoded.command_id <= 1049:
                    channel = self._delay_modes[decoded.command_id - 1044]
                    # Synthetic six-prefix-field fixture for the legacy parser;
                    # not a captured controller reply or a firmware specification.
                    value = (f"{channel['switch'].upper()} {channel['bwd']} "
                             f"{channel['enable']} DELAY VALUE = {channel['value']:.2f}")
                else:
                    value = self._values.get(decoded.command_id, "0")
                    if decoded.command_id in {1039, 1066}:
                        value = f"{int(value):X}"
                    elif isinstance(value, float):
                        value = f"{value:.6f}".rstrip("0").rstrip(".")
                result.extend(decode_reply_datagram(encode_reply([(decoded.command_id, value)])))
        try:
            if send_guard is None:
                perform()
            else:
                send_guard(perform)
            return result
        except TransportError:
            raise
        except (ProtocolError, ValueError, KeyError) as exc:
            raise TransportError(f"Simulator rejected command: {exc}") from exc

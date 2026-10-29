"""Deterministic development board with no Empower device attached.

This simulator is a test fixture, not evidence of actual firmware behavior.
It uses the recovered wire format so application and protocol can be exercised.
"""
from __future__ import annotations
from collections import deque
import re
from .protocol import COMMANDS, QUERIES, PACKET_PREFIX, parse_datagram


class SimulatedTransport:
    def __init__(self):
        self.pending = deque()
        self.socket = None
        self.packet_counter = 0
        self.sent_packets = []
        self.values = {
            "*IDN?": "Spectra-Physics, Spitfire, 0, 1.6.0",
            "HED:STB?": "0", "HED:MOTOR:SPEED?": "30",
            "TDG:STB?": "0", "TDG:STBH?": "0", "TDG:STBHFLT?": "0",
            "TDG:HV1:VOLT?": "3.3", "TDG:HV2:VOLT?": "3.1",
            "TDG:READ:HV1VOLT?": "0", "TDG:READ:HV2VOLT?": "0",
            "TDG:READ:HV1CURR?": "0.00", "TDG:READ:HV2CURR?": "0.00",
            "TDG:HV:ON?": "0", "TDG:OSC:FREQ?": "10",
            "TDG:READ:OSCQUEST?": "80 MHZ", "TDG:DIV?": "1",
            "TDG:TRIG:FREQ?": "10", "TDG:OSC:MODE?": "EXT",
            "TDG:TRIG:MODE?": "EXT", "TDG:OSC:SETMODE?": "CONT",
            "TDG:BWD?": "POS SING", "ECU:STB?": "0", "ECU:STBH?": "0",
            "ECU:TEMP?": "20.00", "ECU:READTEMP?": "20.00",
            "ECU:TECTEMP?": "20.00", "ECU:HUM?": "15.00",
            "ECU:HUMOVERRIDE?": "0", "ECUOPTOUT?": "0",
            "HEDOPTOUT?": "0", "EMPOPTOUT?": "1", "STATUS?": "0", "MONITOR?": "0",
            "TDG:FAULTOVERRIDE?": "0", "COMSTATUS?": "4",
        }
        for ch in range(6):
            self.values[f"TDG:DEL{ch}?"] = f"DELAY {ch} OFF BWD ENA {ch * 100:.2f}"
        self.values["TDG:DEL0?"] = "0 DELAY = 0.00"
        for name in ("HED", "TDG", "ECU"):
            self.values[name + ":VERS?"] = f"Spectra-Physics, {name}, 1.00, 1.00"

    def open(self):
        pass

    def close(self):
        self.pending.clear()

    def discard_pending(self):
        self.pending.clear()

    def send_packet(self, packet: bytes):
        self.sent_packets.append(packet)
        if not packet.startswith(PACKET_PREFIX):
            return
        responses = []
        for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines():
            m = re.match(r"\[(\d+)\](.*)", line)
            if not m:
                continue
            tag = int(m[1])
            if tag < 2000:
                title = QUERIES.get(tag, "").upper()
                # An absent pump cannot supply data to make the app initialize.
                if title.startswith(("EMP:", "MIL:")):
                    continue
                if tag == 1026:
                    channel = m[2][len(title):].strip()
                    title = f"TDG:DEL{channel}?"
                payload = self.values.get(title, "0")
            else:
                title = COMMANDS.get(tag, "")
                parameter = m[2][len(title):].strip()
                if title.startswith(("EMP:", "MIL:")) or tag in (2027, 2028, 2034):
                    payload = "ERROR unsupported without Empower"
                else:
                    payload = "0" if self._command(tag, title, parameter) else "ERROR unsupported command"
            responses.append(f"<{tag}>{payload}")
        if responses:
            self.pending.append(("Spectra-Physics:REPLY_ECLIPSE:" + "\n".join(responses) + "\n").encode("ascii"))

    def _command(self, tag, title, parameter):
        if tag == 2019:
            parts = parameter.split()
            if len(parts) != 2 or parts[0] not in {"1", "2", "3", "4", "5"}:
                return False
            channel = int(parts[0])
            key = f"TDG:DEL{channel}?"
            current = self.values[key].split()
            setting = parts[1].upper()
            if setting in ("ON", "OFF"):
                current[2] = setting
            elif setting in ("BWD", "NBWD"):
                current[3] = setting
            elif setting in ("ENA", "NENA"):
                current[4] = setting
            else:
                try:
                    current[5] = str(float(setting))
                except ValueError:
                    return False
            self.values[key] = " ".join(current)
        elif tag in (2016, 2017):
            self.values["TDG:HV:ON?"] = str(tag == 2017 and 1 or 0)
            for ch in (1, 2):
                self.values[f"TDG:READ:HV{ch}VOLT?"] = self.values[f"TDG:HV{ch}:VOLT?"] if tag == 2017 else "0"
        elif tag in (2022, 2023):
            value = int(self.values["ECU:STB?"])
            self.values["ECU:STB?"] = str(value | 1 if tag == 2022 else value & ~1)
        elif tag in (2049, 2050):
            self.values["ECU:STBH?"] = "0"
        elif tag == 2052:
            # Clearing latched faults cannot clear a current key interlock.
            self.values["TDG:STBHFLT?"] = format(int(self.values["TDG:STBH?"], 16) & 0x4000, "x")
        elif tag in (2009, 2010, 2011, 2012, 2013, 2018):
            pass
        elif parameter:
            self.values[title.upper() + "?"] = parameter
        else:
            return False
        return True

    def receive(self):
        if not self.pending:
            return []
        self.packet_counter += 1
        return parse_datagram(self.pending.popleft(), self.packet_counter)

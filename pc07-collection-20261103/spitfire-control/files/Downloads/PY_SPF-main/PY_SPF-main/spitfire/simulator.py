"""Deterministic development instrument; never opens a device connection.

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
            "EMP:DIODE:CURR?": "100.00", "EMP:READ:DIODE:CURR?": "100.00",
            "EMP:READ:POW?": "1.25", "EMP:QSW:PRF?": "1000",
            "EMP:QSW:PWID?": "200", "EMP:QSW:SOURCE?": "0",
            "EMP:STB?": "1", "EMP:FAULT?": "0 0 0 0",
            "HED:STB?": "0", "HED:MOTOR:SPEED?": "30",
            "TDG:STB?": "0", "TDG:STBH?": "0", "TDG:STBHFLT?": "0",
            "TDG:HV1:VOLT?": "1200", "TDG:HV2:VOLT?": "1200",
            "TDG:READ:HV1VOLT?": "1200", "TDG:READ:HV2VOLT?": "1200",
            "TDG:READ:HV1CURR?": "0.00", "TDG:READ:HV2CURR?": "0.00",
            "TDG:HV:ON?": "0", "TDG:OSC:FREQ?": "80000000",
            "TDG:READ:OSCQUEST?": "80000000", "TDG:DIV?": "1000",
            "TDG:TRIG:FREQ?": "1000", "TDG:OSC:MODE?": "INT",
            "TDG:TRIG:MODE?": "INT", "TDG:OSC:SETMODE?": "CONT",
            "TDG:BWD?": "POS SING", "ECU:STB?": "0", "ECU:STBH?": "0",
            "ECU:TEMP?": "20.00", "ECU:READTEMP?": "20.00",
            "ECU:TECTEMP?": "20.00", "ECU:HUM?": "15.00",
            "ECU:HUMOVERRIDE?": "0", "ECUOPTOUT?": "0",
            "HEDOPTOUT?": "0", "EMPOPTOUT?": "0", "EMP:LBOTEMP?": "150.0",
            "EMP:LBOBREAK?": "1", "STATUS?": "0", "MONITOR?": "0",
            "TDG:FAULTOVERRIDE?": "0", "COMSTATUS?": "0",
        }
        for ch in range(6):
            self.values[f"TDG:DEL{ch}?"] = f"{ch} ON NBWD ENA DELAY = {ch * 100:.2f}"
        self.values["TDG:DEL0?"] = "0 DELAY = 0.00"
        for ch in range(1, 8):
            self.values[f"EMP:SECRETMSG{ch}?"] = "20.00" if ch == 2 else "0.00"
        for name in ("HED", "EMP", "TDG", "ECU"):
            self.values[name + ":VERS?"] = f"Spectra-Physics, {name}, 1.00, 1.00"

    def open(self):
        pass

    def close(self):
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
                payload = self.values.get(title, "0")
            else:
                title = COMMANDS.get(tag, "")
                parameter = m[2][len(title):].strip()
                self._command(tag, title, parameter)
                payload = "0"
            responses.append(f"<{tag}>{payload}")
        if responses:
            self.pending.append(("Spectra-Physics:REPLY_ECLIPSE:" + "\n".join(responses) + "\n").encode("ascii"))

    def _command(self, tag, title, parameter):
        if tag == 2019:
            parts = parameter.split()
            if len(parts) == 2:
                try:
                    ch = int(parts[0]); float(parts[1])
                    self.values[f"TDG:DEL{ch}?"] = f"{ch} ON NBWD ENA DELAY = {parts[1]}"
                except ValueError:
                    pass
        elif tag in (2005, 2027):
            self.values["EMP:STB?"] = "0"
        elif tag in (2006, 2028):
            self.values["EMP:STB?"] = "1"
        elif tag in (2016, 2017):
            self.values["TDG:HV:ON?"] = str(tag == 2017 and 1 or 0)
        elif parameter:
            self.values[title.upper() + "?"] = parameter

    def receive(self):
        if not self.pending:
            return []
        self.packet_counter += 1
        return parse_datagram(self.pending.popleft(), self.packet_counter)

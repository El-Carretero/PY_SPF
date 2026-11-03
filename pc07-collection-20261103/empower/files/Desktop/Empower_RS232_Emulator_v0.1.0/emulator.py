"""Capture-based Empower FW1.2 peer and optional virtual SASC bridge.

The serial endpoint replaces an Empower peer. The UDP bridge is an explicitly
synthetic SASC/TDG/TCU model for an isolated XP test, not recovered SASC firmware.
No physical output or instrument forwarding is implemented.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import socket
import socketserver
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
from empower.framing import FrameBuffer, ProtocolError, decode, encode
from empower import commands
from empower.responses import parse_response

VERSION = '0.1.0'
CAPTURED = {
    'firmware': '10 02 00 00 0c 62 00 48 43 01 02 0e',
    'stop': '10 02 00 00 1e 12 00 00 00 80 00 64 00 28 00 00 89 34 00 63 00 00 00 02 01 47 ca 3b 01 be',
    'communication-fault': '10 02 00 00 1e 12 00 00 00 90 00 64 00 28 00 00 89 34 00 65 00 00 00 03 01 47 ca 3b 02 d2',
    'key-fault': '10 02 00 00 1e 12 00 00 20 80 00 64 00 28 00 00 89 34 00 65 00 00 00 02 01 47 ca 3b 02 e1',
    'qswitch': '10 02 00 00 09 75 00 02 92',
    'service': '10 02 00 00 15 70 00 00 fa 00 02 58 00 00 30 d4 05 46 04 9c da',
    'reset': '10 02 00 00 0c 18 00 00 20 00 02 58',
    'lbo': '10 02 00 00 10 1a 00 89 34 00 63 04 ff 00 00 5f',
    'power': '10 02 00 00 0a 72 00 00 00 8e',
    'softstart': '10 02 00 00 0b 69 00 01 00 01 88',
    'underfrequency': '10 02 00 00 1e 73 00 00 00 80 00 64 00 28 00 00 89 34 00 62 00 00 00 03 01 47 c9 64 01 47',
}
CAPTURED = {k: bytes.fromhex(v) for k, v in CAPTURED.items()}


def finalized(raw):
    raw = bytearray(raw)
    raw[-1] = sum(raw[:-1]) & 255
    return bytes(raw)


class JsonLog:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.counts = Counter()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind, **values):
        row = {'utc': datetime.now(timezone.utc).isoformat(), 'kind': kind, **values}
        with self.lock:
            self.counts[kind] += 1
            if self.path:
                with self.path.open('a', encoding='utf-8') as file:
                    file.write(json.dumps(row, ensure_ascii=False) + '\n')


class EmpowerPeer:
    def __init__(self, profile='stop', *, log=None, clock=time.monotonic):
        self.log = log or JsonLog()
        self.clock = clock
        self.lock = threading.RLock()
        self.status = bytearray(CAPTURED[profile])
        self.qswitch = 2
        self.softstart = bytearray(CAPTURED['softstart'])
        self.started = None

    def _tick(self):
        if self.started is not None and self.clock() - self.started >= 3:
            self.status[28] = 0
            self.started = None

    def handle(self, raw):
        with self.lock:
            try:
                frame = decode(raw, verify_checksum=True)
            except ProtocolError as exc:
                self.log.write('binary_rejected', request_hex=raw.hex(' '), reason=str(exc))
                return None
            self._tick()
            op = frame.opcode
            source = 'captured-template'
            reply = None
            if op == 0x42 and len(raw) == 8:
                reply = CAPTURED['firmware']
            elif op == 0x02 and len(raw) == 8:
                reply = finalized(self.status)
                source = 'captured-status-with-modelled-state'
            elif op == 0x01 and len(raw) == 17:
                source = 'synthetic-setting-transition'
                current = int.from_bytes(raw[14:16], 'big')
                if current <= 250:
                    self.status[10:14] = raw[8:12]
                    self.status[20:22] = raw[14:16]
                else:
                    self.status[8] |= 4
                    self.status[28] = 2
                result = bytearray(self.status)
                result[5] = 0x11
                reply = finalized(result)
            elif op == 0x08 and len(raw) == 9 and raw[7] in (0, 1):
                source = 'synthetic-state-transition-no-ack'
                faults = self.status[7] or self.status[8] or self.status[9] & 0x13
                if raw[7] == 1:
                    self.status[28] = 2 if faults else 1
                    self.started = None
                elif not faults:
                    self.status[28] = 3
                    self.started = self.clock()
            elif op in (0x55, 0x51) and len(raw) == (8 if op == 0x55 else 9):
                if op == 0x51:
                    if raw[7] not in (0, 1, 2, 3):
                        return None
                    self.qswitch = raw[7]
                    source = 'synthetic-qswitch-transition'
                result = bytearray(CAPTURED['qswitch'])
                result[7] = self.qswitch
                reply = finalized(result)
            elif op == 0x50 and len(raw) == 23:
                # Recorded zero-code service edits were not applied. Do not
                # invent a service authorization policy for other numbers.
                reply = CAPTURED['service']
                source = 'captured-service-unchanged-write-acceptance-unmodelled'
            elif op == 0x09 and len(raw) == 8:
                reply = CAPTURED['reset']
                source = 'captured-opaque-reset-ack-faults-preserved'
            elif op == 0x0b and len(raw) == 8:
                reply = CAPTURED['lbo']
            elif op == 0x52 and len(raw) == 8:
                reply = CAPTURED['power']  # Optical power is never invented.
            elif op == 0x49 and len(raw) == 11:
                self.softstart[7] = int(bool(raw[7]))
                self.softstart[8:10] = raw[8:10]
                reply = finalized(self.softstart)
                source = 'synthetic-softstart-transition'
            elif op == 0x53 and len(raw) == 9 and raw[7] in (0, 1):
                self.status[9] = (self.status[9] & 0x7f) | (raw[7] * 0x80)
                result = bytearray(self.status)
                result[5] = 0x73
                reply = finalized(result)
                source = 'captured-layout-synthetic-protection-transition'
            else:
                source = 'unsupported-no-invented-response'
            if reply:
                decode(reply, verify_checksum=True)
            self.log.write('binary_transaction', request_hex=raw.hex(' '),
                           response_hex=reply.hex(' ') if reply else None,
                           opcode=op, source=source, state_code=self.status[28])
            return reply


class BinaryHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(1.0)
        parser = FrameBuffer(verify_checksum=True)
        while not self.server.stopping.is_set():
            try:
                chunk = self.request.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            before = parser.rejected
            for frame in parser.feed(chunk):
                reply = self.server.peer.handle(frame.raw)
                if reply:
                    self.request.sendall(reply)
            if parser.rejected != before:
                self.server.peer.log.write('stream_rejected', count=parser.rejected - before)


class BinaryServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, address, peer):
        self.peer = peer
        self.stopping = threading.Event()
        super().__init__(address, BinaryHandler)

    def close(self):
        self.stopping.set()
        self.shutdown()
        self.server_close()


class BinaryClient:
    def __init__(self, address, log=None):
        self.address = address
        self.log = log or JsonLog()
        self.socket = None
        self.lock = threading.RLock()

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def exchange(self, raw, *, expect=True):
        # This client is used only by the virtual SASC bridge on loopback.
        with self.lock:
            try:
                if self.socket is None:
                    self.socket = socket.create_connection(self.address, timeout=.5)
                    self.socket.settimeout(.5)
                self.socket.sendall(raw)
                if not expect:
                    return None
                parser = FrameBuffer(verify_checksum=True)
                while True:
                    chunk = self.socket.recv(4096)
                    if not chunk:
                        raise ProtocolError('Peer closed without a complete response')
                    frames = parser.feed(chunk)
                    if frames:
                        return frames[0]
            except (OSError, ProtocolError):
                self.close()
                raise


class SpitfireBridge:
    """Synthetic ASCII SASC mapping backed by the binary Empower endpoint."""
    def __init__(self, binary_client, log=None):
        self.binary = binary_client
        self.log = log or JsonLog()
        catalog = json.loads((ROOT / 'spitfire_catalog.json').read_text())
        self.queries = {int(k): v for k, v in catalog['queries'].items()}
        self.commands = {int(k): v for k, v in catalog['commands'].items()}
        identity = 'Spectra Physics,SASC,EMU-' + VERSION
        self.values = {tag: '0' for tag in self.queries}
        self.values.update({1000: identity, 1038: identity, 1062: identity, 1081: identity, 1082: identity,
            1015: '0', 1019: '0', 1028: '1', 1029: '3073', 1057: '3073', 1088: '3073',
            1030: '19.02', 1031: '3.24', 1032: '19', 1084: '19.3',
            1034: 'Spectra Physics,HED,EMULATED,EMU-' + VERSION,
            1036: 'Spectra Physics,TDG-S,EMULATED,EMU-' + VERSION,
            1037: 'Spectra Physics,TCU,EMU-' + VERSION,
            1024: '1000.0', 1025: '1', 1040: '3.399 KV', 1041: '3.139 KV',
            1050: 'EXT', 1067: 'EXT', 1051: 'EXT CONT 1000.0', 1053: '1000',
            1052: ' DELAY 0 3100.0', 1054: ' NEG DUAL ON', 1060: '90',
            1065: '80.0 MHz', 1080: 'EXT CONT 1000.0'})
        self.delays = {ch: ['OFF', 'BWD', 'ENA', str({1:85.82, 2:990.25}.get(ch, 0))] for ch in range(1, 6)}

    def _status(self):
        frame = self.binary.exchange(commands.query_status())
        return parse_response(frame, (1, 2)), frame.raw

    def _emp_query(self, tag):
        if tag in (1007, 1009, 1010, 1011, 1013, 1014):
            data, raw = self._status()
            if tag in (1007, 1009):
                return str(int.from_bytes(raw[22:24] if tag == 1007 else raw[20:22], 'big'))
            if tag == 1010:
                # FW1.2 operating word is 0.01 kHz = 10 Hz, which equals
                # the SASC value multiplied by ten by the original PC GUI.
                return str(int.from_bytes(raw[10:12], 'big'))
            if tag == 1011:
                return str(data['service']['qswitch_pulse_width_ns'])
            if tag == 1014:
                return f'{raw[7]} {raw[8]} {raw[9] & 0x13} 0'
            # Mapping is inferred from the original PC decoder, not SASC code.
            stb = int(data['state_code'] == 0) | (0x200 if data['state_code'] == 3 else 0)
            if data['faults']:
                stb |= 0x400
            if any(x in data['faults'] for x in ('Key switch', 'Cover interlock')):
                stb |= 0x100
            return str(stb)
        if tag == 1008:
            return str(parse_response(self.binary.exchange(commands.query_power()), (1, 2))['power_w'])
        if tag in (1016, 1035):
            data = parse_response(self.binary.exchange(commands.query_firmware()), (1, 2))
            return 'Spectra Physics,Empower,' + data['firmware'] + ',EMULATED'
        if tag == 1012:
            return str(parse_response(self.binary.exchange(commands.query_qswitch()), (1, 2))['qswitch'])
        if 1071 <= tag <= 1076:
            data = parse_response(self.binary.exchange(commands.service_read()), (1, 2))['service']
            return str(data[('max_current_a', 'power_slope_mw_v', 'power_intercept_mw',
                             'max_power_mw', 'lbo_high_c', 'lbo_low_c')[tag - 1071]])
        if tag == 1077:
            return str(parse_response(self.binary.exchange(commands.query_lbo()), (1, 2))['service']['lbo_temp_c'])
        return self.values.get(tag, '0')

    def _write(self, tag, arg):
        if tag in (2003, 2004, 2007):
            _, raw = self._status()
            cw, fw, pw = (int.from_bytes(raw[a:a+2], 'big') for a in (20, 10, 12))
            number = float(arg)
            if not math.isfinite(number) or number < 0:
                raise ValueError('Invalid setting')
            if tag == 2003: cw = round(number)
            if tag == 2004: fw = round(number)
            if tag == 2007: pw = round(number / 125)
            self.binary.exchange(commands.set_operating_words(cw, fw, pw))
        elif tag == 2008:
            self.binary.exchange(commands.set_qswitch(int(float(arg))))
        elif tag in (2005, 2006, 2027, 2028):
            self.binary.exchange(commands.set_run(tag in (2005, 2027)), expect=False)
            self._status()
        elif tag == 2044:
            self.binary.exchange(commands.reset_faults())
        elif tag == 2019:
            ch, setting = arg.split(maxsplit=1)
            row = self.delays[int(ch)]
            key = setting.upper()
            if key in ('ON', 'OFF'): row[0] = key
            elif key in ('BWD', 'NBWD'): row[1] = key
            elif key in ('ENA', 'NENA'): row[2] = key
            else: row[3] = str(float(setting))
        elif tag in (2016, 2017):
            self.values[1021] = self.values[1061] = str(int(tag == 2017))
            self.values[1042] = self.values[1040] if tag == 2017 else '0'
            self.values[1043] = self.values[1041] if tag == 2017 else '0'
        elif tag in (2030, 2031):
            self.values[1050 if tag == 2030 else 1051] = arg.upper()
            if tag == 2030: self.values[1067] = arg.upper()
        elif tag in (2022, 2023):
            self.values[1028] = str(int(tag == 2022))
        elif tag in (2037, 2038, 2039, 2040, 2041, 2042, 2043):
            return 'ERROR:UNMODELLED_SERVICE_WRITE'
        elif tag in (2014, 2020, 2021, 2024, 2025, 2026, 2029, 2032, 2035, 2036, 2047, 2051, 2053):
            target = {2014:1060, 2020:1025, 2021:1032, 2024:1033, 2025:1040, 2026:1041,
                      2029:1044, 2032:1053, 2035:1069, 2036:1068, 2047:1078, 2051:1086, 2053:1087}[tag]
            self.values[target] = arg
        elif tag == 2048:
            self.values[1080] = 'EXT ' + arg.upper() + ' ' + self.values[1053]
        elif tag not in (2009, 2010, 2011, 2012, 2013, 2018, 2033, 2045, 2046, 2049, 2050, 2052, 2054, 2055):
            return 'ERROR:UNMODELLED'
        return ''  # Matches observed empty SASC command receipts; synthetic bridge.

    def answer(self, tag, text):
        table = self.queries if tag < 2000 else self.commands
        base = table.get(tag)
        if base is None or not text.upper().startswith(base.upper()):
            return 'ERROR:COMMAND'
        arg = text[len(base):].strip()
        if tag < 2000 and arg:
            return 'ERROR:ARG'
        try:
            if tag >= 2000:
                return self._write(tag, arg)
            if base.upper().startswith('EMP:'):
                return self._emp_query(tag)
            if tag == 1089:
                self._status()
                return '0'
            if tag in (1045, 1046, 1047, 1048, 1049, 1058, 1059, 1063, 1064):
                ch = {1058:1, 1059:2, 1063:1, 1064:2}.get(tag, tag - 1044)
                return f' DELAY {ch} ' + ' '.join(self.delays[ch])
            return self.values.get(tag, '0')
        except (OSError, ProtocolError) as exc:
            self.log.write('binary_unavailable', tag=tag, error=str(exc))
            return '4' if tag == 1089 else '2048' if tag == 1013 else '-99'
        except (ValueError, KeyError, OverflowError) as exc:
            self.log.write('bridge_rejected', tag=tag, error=str(exc))
            return 'ERROR:ARG'


def serve_udp(bridge, address, client, log, stop):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(address)
    sock.settimeout(.3)
    prefix = b'Spectra-Physics:CMD_ECLIPSE,'
    try:
        while not stop.is_set():
            try: data, sender = sock.recvfrom(4096)
            except socket.timeout: continue
            if sender[0] != client or len(data) > 1500 or not data.startswith(prefix):
                log.write('udp_rejected', sender=list(sender), payload_hex=data[:1500].hex(' '))
                continue
            try:
                lines = data[len(prefix):].split(b'\0', 1)[0].decode('ascii', errors='strict').splitlines()
            except UnicodeDecodeError:
                log.write('udp_rejected', sender=list(sender), reason='non-ASCII command')
                continue
            replies = []
            for line in lines:
                match = re.fullmatch(r'\[(\d{4})\](.*)', line)
                if not match: continue
                tag, text = int(match[1]), match[2]
                answer = bridge.answer(tag, text)
                replies.append(f'<{tag}>{answer}')
                log.write('ascii_transaction', sender=list(sender), tag=tag, request=text,
                          response=answer, bridge_scope='synthetic-SASC-mapping')
            if replies:
                sock.sendto(('Spectra-Physics:REPLY_ECLIPSE:' + '\n'.join(replies) + '\n').encode('ascii'), sender)
    finally:
        sock.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', help='Explicit RS-232 adapter port; 19200 baud, 8N1')
    parser.add_argument('--profile', choices=('stop', 'communication-fault', 'key-fault'), default='stop')
    parser.add_argument('--tcp-port', type=int, default=19200)
    parser.add_argument('--udp-bind', help='Optional virtual SASC host-only address')
    parser.add_argument('--udp-port', type=int, default=1024)
    parser.add_argument('--client', default='10.19.70.2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=3600)
    opts = parser.parse_args(argv)
    if not 0 < opts.duration <= 86400:
        parser.error('Duration must be between 0 and 86400 seconds')
    opts.output.mkdir(parents=True, exist_ok=True)
    log = JsonLog(opts.output / 'traffic.jsonl')
    peer = EmpowerPeer(opts.profile, log=log)
    log.write('session', version=VERSION, profile=opts.profile,
              scope='EMULATED_PEER_NOT_REAL_FIRMWARE_OR_OPTICAL_VALIDATION', serial=opts.serial)
    if opts.serial:
        if opts.udp_bind:
            parser.error('Serial peer and virtual SASC are separate endpoint modes')
        import serial
        deadline = time.monotonic() + opts.duration
        stream = FrameBuffer(verify_checksum=True)
        with serial.Serial(opts.serial, 19200, bytesize=8, parity='N', stopbits=1,
                           timeout=.1, xonxoff=False, rtscts=False, dsrdtr=False) as port:
            while time.monotonic() < deadline and not (opts.output / 'STOP').exists():
                for frame in stream.feed(port.read(4096)):
                    reply = peer.handle(frame.raw)
                    if reply: port.write(reply)
        return
    if opts.udp_bind not in (None, '127.0.0.1', '10.19.70.13'):
        parser.error('Virtual SASC binds only to loopback or the configured host-only alias')
    server = BinaryServer(('127.0.0.1', opts.tcp_port), peer)
    stop = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if opts.udp_bind:
        bridge = SpitfireBridge(BinaryClient(server.server_address, log), log)
        udp = threading.Thread(target=serve_udp, args=(bridge, (opts.udp_bind, opts.udp_port), opts.client, log, stop), daemon=True)
        udp.start()
    ready = {'version': VERSION, 'pid': __import__('os').getpid(), 'binary_endpoint': list(server.server_address),
             'udp_bind': opts.udp_bind, 'udp_port': opts.udp_port if opts.udp_bind else None,
             'allowed_client': opts.client, 'profile': opts.profile, 'log': str(log.path),
             'scope': 'virtual SASC + capture-based binary peer; physical RS232 unverified'}
    (opts.output / 'ready.json').write_text(json.dumps(ready, indent=2))
    print(json.dumps(ready), flush=True)
    deadline = time.monotonic() + opts.duration
    try:
        while time.monotonic() < deadline and not (opts.output / 'STOP').exists():
            if opts.udp_bind and not udp.is_alive():
                raise RuntimeError('Virtual SASC receive thread stopped')
            time.sleep(.1)
    finally:
        stop.set()
        server.close()
        (opts.output / 'summary.json').write_text(json.dumps(dict(log.counts), indent=2))


if __name__ == '__main__':
    main()

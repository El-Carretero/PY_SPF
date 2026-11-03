#!/usr/bin/env python3
"""Independently read classic Ethernet pcap with dpkt and reconcile simulator JSONL.

Requires dpkt (tested with 1.9.8), not pcap_audit.py. Does not send any traffic.
The filename/CLI does not establish original-process provenance; guest process
and action evidence must establish that separately. Simulator replies remain
synthetic irrespective of whether every captured byte agrees with its log.
"""
import argparse
import collections
import hashlib
import io
import json
import socket
import struct
import sys
from pathlib import Path

import dpkt


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_records(data):
    if len(data) < 24:
        raise ValueError('Incomplete classic pcap global header')
    magic = data[:4]
    formats = {b'\xd4\xc3\xb2\xa1': ('<', 1000000), b'\xa1\xb2\xc3\xd4': ('>', 1000000),
               b'\x4d\x3c\xb2\xa1': ('<', 1000000000), b'\xa1\xb2\x3c\x4d': ('>', 1000000000)}
    if magic not in formats:
        raise ValueError('Input must be classic pcap')
    endian, divisor = formats[magic]
    major, minor, zone, precision, snaplen, linktype = struct.unpack_from(endian + 'HHIIII', data, 4)
    if (major, minor, linktype) != (2, 4, 1):
        raise ValueError('Require pcap 2.4 with Ethernet linktype 1')
    records, pos = [], 24
    while pos < len(data):
        if pos + 16 > len(data):
            raise ValueError('Partial record header at %d' % pos)
        sec, fraction, caplen, original = struct.unpack_from(endian + 'IIII', data, pos)
        pos += 16
        if fraction >= divisor or caplen != original or caplen > snaplen:
            raise ValueError('Invalid timestamp or truncated packet at record %d' % (len(records) + 1))
        if pos + caplen > len(data) or caplen < 14:
            raise ValueError('Partial Ethernet frame at record %d' % (len(records) + 1))
        records.append((sec, fraction, data[pos:pos + caplen]))
        pos += caplen
    return records


def entry(direction, src, sport, dst, dport, payload):
    return (direction, src, int(sport), dst, int(dport), payload.hex())


def describe(key, count):
    direction, src, sport, dst, dport, payload = key
    raw = bytes.fromhex(payload)
    return dict(direction=direction, src=src, sport=sport, dst=dst, dport=dport,
                payload_bytes=len(raw), payload_sha256=digest(raw), occurrences=count)


def sequence_hash(sequence):
    h = hashlib.sha256()
    for record in sequence:
        encoded = json.dumps(record, separators=(',', ':')).encode('ascii')
        h.update(struct.pack('!I', len(encoded)))
        h.update(encoded)
    return h.hexdigest()


def verify(pcap_path, log_path, guest, simulator, guest_port, simulator_port):
    raw, log_raw = pcap_path.read_bytes(), log_path.read_bytes()
    records = strict_records(raw)
    reader = dpkt.pcap.Reader(io.BytesIO(raw))
    decoded = list(reader)
    if reader.datalink() != 1 or len(decoded) != len(records):
        raise ValueError('dpkt record count/linktype differs from structural validation')
    capture = []
    malformed, other_udp, frame_hashes = [], 0, []
    optout = []
    for number, ((timestamp, frame), (_, _, expected)) in enumerate(zip(decoded, records), 1):
        if frame != expected:
            raise ValueError('dpkt bytes differ at frame %d' % number)
        frame_hashes.append(digest(frame))
        try:
            eth = dpkt.ethernet.Ethernet(frame)
            ip = eth.data
            if not isinstance(ip, dpkt.ip.IP) or ip.p != 17:
                continue
            if ip.offset or ip.mf:
                raise ValueError('Fragmented UDP requires separate reassembly')
            udp = ip.data
            if not isinstance(udp, dpkt.udp.UDP):
                raise ValueError('dpkt did not decode UDP')
            if len(bytes(ip)) != ip.len or udp.ulen != 8 + len(udp.data) or ip.len != ip.hl * 4 + udp.ulen:
                raise ValueError('Inconsistent IPv4/UDP lengths')
            src, dst = socket.inet_ntoa(ip.src), socket.inet_ntoa(ip.dst)
            endpoints = (src, udp.sport, dst, udp.dport)
            if endpoints == (guest, guest_port, simulator, simulator_port):
                direction = 'guest_to_simulator'
            elif endpoints == (simulator, simulator_port, guest, guest_port):
                direction = 'simulator_to_guest'
            else:
                other_udp += 1
                continue
            payload = bytes(udp.data)
            capture.append(entry(direction, src, udp.sport, dst, udp.dport, payload))
            if direction == 'simulator_to_guest':
                import re
                for value in re.findall(rb'<1068>([^\r\n\x00]*)', payload):
                    optout.append(dict(frame=number, timestamp_epoch=float(timestamp),
                                       value=value.decode('ascii', 'backslashreplace'),
                                       provenance='simulator response'))
        except (dpkt.Error, ValueError, struct.error) as exc:
            malformed.append(dict(frame=number, error=str(exc)))
    logged, log_errors, excluded_log_sources = [], [], []
    log_records = 0
    for number, line in enumerate(log_raw.decode('utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        log_records += 1
        try:
            record = json.loads(line)
            src, sport = record['source']
            request = bytes.fromhex(record['request_hex'])
            if (src, int(sport)) != (guest, guest_port):
                excluded_log_sources.append(dict(line=number, source=record['source']))
                continue
            logged.append(entry('guest_to_simulator', src, sport, simulator, simulator_port, request))
            if 'reply_hex' in record:
                reply = bytes.fromhex(record['reply_hex'])
                logged.append(entry('simulator_to_guest', simulator, simulator_port, guest, guest_port, reply))
        except (KeyError, TypeError, ValueError) as exc:
            log_errors.append(dict(line=number, error=str(exc)))
    captured_counts, logged_counts = collections.Counter(capture), collections.Counter(logged)
    missing, extra = logged_counts - captured_counts, captured_counts - logged_counts
    directions = {}
    for direction in ('guest_to_simulator', 'simulator_to_guest'):
        cap = [x for x in capture if x[0] == direction]
        log = [x for x in logged if x[0] == direction]
        first_mismatch = next((i + 1 for i, (a, b) in enumerate(zip(cap, log)) if a != b), None)
        if first_mismatch is None and len(cap) != len(log):
            first_mismatch = min(len(cap), len(log)) + 1
        directions[direction] = dict(capture_datagrams=len(cap), logged_datagrams=len(log),
                                     exact_ordered_payload_and_endpoint_match=cap == log,
                                     capture_sequence_sha256=sequence_hash(cap),
                                     log_sequence_sha256=sequence_hash(log),
                                     first_mismatch_ordinal=first_mismatch)
    both = all(x['capture_datagrams'] > 0 for x in directions.values())
    success = both and not malformed and not log_errors and not missing and not extra and all(
        x['exact_ordered_payload_and_endpoint_match'] for x in directions.values())
    return dict(status='PASS' if success else 'FAIL', reader='dpkt', reader_version=dpkt.__version__,
                pcap_path=str(pcap_path.resolve()), log_path=str(log_path.resolve()),
                pcap_sha256=digest(raw), log_sha256=digest(log_raw), frame_count=len(records),
                classic_pcap_structure_valid=True, all_captured_lengths_equal_original=True,
                dpkt_and_structural_reader_frame_bytes_match=True,
                frame_hash_sequence_sha256=sequence_hash(frame_hashes),
                all_ethernet_frame_sha256=frame_hashes,
                both_directions_present=both, directions=directions,
                exact_payload_endpoint_multiset_match=not missing and not extra,
                missing_from_capture_datagrams=sum(missing.values()),
                extra_in_capture_datagrams=sum(extra.values()),
                missing_from_capture_details=[describe(k, v) for k, v in missing.items()],
                extra_in_capture_details=[describe(k, v) for k, v in extra.items()],
                malformed_packets=malformed, malformed_log_records=log_errors,
                other_udp_datagrams=other_udp, excluded_log_sources=excluded_log_sources,
                log_records=log_records, optout_1068_responses=optout,
                provenance='Process origin requires separate guest evidence. All replies are simulator-generated.',
                limitation='Reconciliation establishes captured datagram equality with this simulator log; it does not establish real-controller behavior or rule out losses outside the provided capture/log interval.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pcap', type=Path)
    parser.add_argument('log', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--guest', default='10.19.70.2')
    parser.add_argument('--simulator', default='10.19.70.13')
    parser.add_argument('--guest-port', type=int, default=1024)
    parser.add_argument('--simulator-port', type=int, default=1024)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; refusing to overwrite evidence')
    report = verify(args.pcap, args.log, args.guest, args.simulator, args.guest_port, args.simulator_port)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: report[k] for k in ('status', 'frame_count', 'both_directions_present', 'directions',
                                           'missing_from_capture_datagrams', 'extra_in_capture_datagrams')}, indent=2))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, dpkt.Error) as exc:
        print('INDEPENDENT VERIFICATION ERROR: %s' % exc, file=sys.stderr)
        sys.exit(2)

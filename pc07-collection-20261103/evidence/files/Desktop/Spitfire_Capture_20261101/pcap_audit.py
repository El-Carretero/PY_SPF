#!/usr/bin/env python3
"""Strict stdlib pcapng Ethernet -> classic pcap converter and Spitfire audit.

Never generates network traffic, modifies a payload, or deduplicates packets.
Pktmon ETL remains the upstream source artifact and should be retained separately.
Python 3.8+; no installed packages or capture drivers required for conversion.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import ipaddress
import json
import re
import struct
import sys
from pathlib import Path


class AuditError(ValueError):
    pass


def check(condition, message):
    if not condition:
        raise AuditError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_options(data, endian, where):
    result = collections.defaultdict(list)
    pos = 0
    while pos < len(data):
        check(len(data) - pos >= 4, where + ': partial option header')
        code, size = struct.unpack_from(endian + 'HH', data, pos)
        pos += 4
        if code == 0:
            check(size == 0, where + ': invalid end-of-options length')
            check(not any(data[pos:]), where + ': data after end-of-options')
            return result
        padded = (size + 3) & ~3
        check(pos + padded <= len(data), where + ': truncated option')
        result[code].append(data[pos:pos + size])
        pos += padded
    # The pcapng reader requirements explicitly permit an option list to end
    # exactly at its enclosing block boundary without opt_endofopt. Pktmon
    # emits this form for ISB. Partial option headers/values still fail above.
    # https://datatracker.ietf.org/doc/draft-ietf-opsawg-pcapng/06/ section 4.3
    return result


def one_option(options, code, default, where):
    values = options.get(code, [])
    check(len(values) <= 1, where + ': duplicate option %d' % code)
    return values[0] if values else default


def read_pcapng(data):
    """Return metadata and frames; exact tick timestamps are retained separately."""
    pos, endian, section = 0, None, -1
    interfaces, all_interfaces, frames, statistics = [], [], [], []
    block_counts = collections.Counter()
    quantized = 0
    section_end = None
    while pos < len(data):
        where = 'block at byte %d' % pos
        check(len(data) - pos >= 12, where + ': truncated block header')
        raw_type = data[pos:pos + 4]
        if raw_type == b'\x0a\x0d\x0d\x0a':
            if section_end is not None:
                check(pos == section_end, where + ': incorrect declared section length')
            magic = data[pos + 8:pos + 12]
            check(magic in (b'\x4d\x3c\x2b\x1a', b'\x1a\x2b\x3c\x4d'),
                  where + ': bad byte-order magic')
            endian = '<' if magic == b'\x4d\x3c\x2b\x1a' else '>'
            section += 1
            interfaces = []
        check(endian is not None, where + ': first block must be Section Header')
        kind, length = struct.unpack_from(endian + 'II', data, pos)
        check(length >= 12 and length % 4 == 0, where + ': invalid block length')
        check(pos + length <= len(data), where + ': truncated block')
        check(struct.unpack_from(endian + 'I', data, pos + length - 4)[0] == length,
              where + ': mismatched trailing block length')
        body = data[pos + 8:pos + length - 4]
        block_counts['0x%08x' % kind] += 1
        if kind == 0x0a0d0d0a:
            check(len(body) >= 16, where + ': short Section Header')
            major, minor, declared = struct.unpack_from(endian + 'HHq', body, 4)
            check((major, minor) == (1, 0), where + ': unsupported pcapng version')
            check(declared >= -1, where + ': invalid section length')
            section_end = pos + length + declared if declared != -1 else None
            parse_options(body[16:], endian, where)
        elif kind == 1:
            check(len(body) >= 8, where + ': short Interface Description')
            linktype, reserved, snaplen = struct.unpack_from(endian + 'HHI', body)
            check(linktype == 1, where + ': only Ethernet linktype 1 is accepted')
            check(reserved == 0, where + ': nonzero reserved IDB field')
            options = parse_options(body[8:], endian, where)
            resolution = one_option(options, 9, b'\x06', where)
            check(len(resolution) == 1, where + ': invalid if_tsresol')
            exp = resolution[0]
            divisor = (2 ** (exp & 127)) if exp & 128 else (10 ** exp)
            offset = one_option(options, 14, b'\0' * 8, where)
            check(len(offset) == 8, where + ': invalid if_tsoffset')
            offset = struct.unpack(endian + 'q', offset)[0]
            name = one_option(options, 2, b'', where).decode('utf-8', 'replace')
            interface = dict(section=section, interface_id=len(interfaces),
                             linktype=linktype, snaplen=snaplen, name=name,
                             timestamp_divisor=divisor, timestamp_offset_seconds=offset)
            interfaces.append(interface)
            all_interfaces.append(interface)
        elif kind == 6:
            check(len(body) >= 20, where + ': short Enhanced Packet Block')
            iid, hi, lo, captured, original = struct.unpack_from(endian + 'IIIII', body)
            check(iid < len(interfaces), where + ': unknown interface ID')
            interface = interfaces[iid]
            check(captured == original, where + ': truncated packet (caplen != original)')
            check(captured >= 14, where + ': incomplete Ethernet header')
            check(not interface['snaplen'] or captured <= interface['snaplen'],
                  where + ': packet exceeds declared snaplen')
            padded = (captured + 3) & ~3
            check(20 + padded <= len(body), where + ': incomplete packet bytes')
            parse_options(body[20 + padded:], endian, where)
            payload = body[20:20 + captured]
            ticks = (hi << 32) | lo
            divisor = interface['timestamp_divisor']
            us, residue = divmod(ticks * 1000000, divisor)
            us += interface['timestamp_offset_seconds'] * 1000000
            seconds, micros = divmod(us, 1000000)
            check(0 <= seconds <= 0xffffffff, where + ': timestamp exceeds classic pcap range')
            quantized += bool(residue)
            frames.append(dict(number=len(frames) + 1, section=section, interface_id=iid,
                               timestamp_us=us, timestamp_ticks=ticks,
                               timestamp_divisor=divisor,
                               timestamp_offset_seconds=interface['timestamp_offset_seconds'],
                               submicrosecond_remainder_numerator=residue,
                               submicrosecond_remainder_denominator=divisor,
                               data=payload, captured_length=captured, original_length=original))
        elif kind in (2, 3):
            raise AuditError(where + ': unsupported packet block; refusing to omit packets')
        elif kind == 5:
            check(len(body) >= 12, where + ': short Interface Statistics block')
            iid = struct.unpack_from(endian + 'I', body)[0]
            check(iid < len(interfaces), where + ': invalid statistics interface')
            options = parse_options(body[12:], endian, where)
            stats = dict(section=section, interface_id=iid)
            for code, name in ((4, 'received'), (5, 'interface_dropped'), (6, 'filter_accepted'),
                               (7, 'os_dropped'), (8, 'user_delivered')):
                value = one_option(options, code, None, where)
                if value is not None:
                    check(len(value) == 8, where + ': invalid interface counter length')
                    stats[name] = struct.unpack(endian + 'Q', value)[0]
            statistics.append(stats)
        # Other blocks contain metadata, never packet frames under pcapng 1.0.
        pos += length
        if section_end is not None:
            check(pos <= section_end, where + ': block exceeds declared section length')
    if section_end is not None:
        check(pos == section_end, 'file ends before declared section end')
    check(section >= 0, 'empty input or missing Section Header')
    check(frames, 'capture contains no Ethernet frames')
    return dict(sections=section + 1, interfaces=all_interfaces, interface_statistics=statistics,
                blocks=dict(block_counts), submicrosecond_timestamps_floored=quantized), frames


def encode_pcap(frames):
    snaplen = max(65535, max(x['captured_length'] for x in frames))
    output = bytearray(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, snaplen, 1))
    for frame in frames:
        seconds, micros = divmod(frame['timestamp_us'], 1000000)
        output.extend(struct.pack('<IIII', seconds, micros,
                                  frame['captured_length'], frame['original_length']))
        output.extend(frame['data'])
    return bytes(output)


def verify_classic(data, expected):
    check(len(data) >= 24, 'output: incomplete pcap global header')
    magic, major, minor, zone, sigfigs, snaplen, linktype = struct.unpack_from('<IHHIIII', data)
    check((magic, major, minor, zone, sigfigs, linktype) == (0xa1b2c3d4, 2, 4, 0, 0, 1),
          'output: incorrect pcap global header')
    pos, index = 24, 0
    while pos < len(data):
        check(pos + 16 <= len(data), 'output: partial packet header')
        seconds, micros, captured, original = struct.unpack_from('<IIII', data, pos)
        pos += 16
        check(index < len(expected), 'output: additional packet')
        frame = expected[index]
        check(micros < 1000000 and captured == original and captured <= snaplen,
              'output: invalid record fields')
        check(pos + captured <= len(data), 'output: partial packet data')
        check(seconds * 1000000 + micros == frame['timestamp_us'], 'output: timestamp changed')
        check(data[pos:pos + captured] == frame['data'], 'output: Ethernet bytes changed')
        pos += captured
        index += 1
    check(index == len(expected), 'output: packet missing')
    return index


def timestamp_text(us):
    sec, micro = divmod(us, 1000000)
    return datetime.datetime.fromtimestamp(sec, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + '.%06dZ' % micro


def decode_frame(frame, guest, simulator, port):
    raw = frame['data']
    row = {k: v for k, v in frame.items() if k != 'data'}
    row.update(timestamp_utc=timestamp_text(frame['timestamp_us']), frame_sha256=sha256(raw),
               src_mac=':'.join('%02x' % x for x in raw[6:12]),
               dst_mac=':'.join('%02x' % x for x in raw[:6]),
               src_ip='', dst_ip='', src_port='', dst_port='', direction='other',
               protocol='', udp_payload_hex='', udp_payload_ascii='', tags=[], messages=[])
    offset, etype = 14, struct.unpack_from('!H', raw, 12)[0]
    while etype in (0x8100, 0x88a8, 0x9100):
        check(offset + 4 <= len(raw), 'frame %d: truncated VLAN' % frame['number'])
        etype = struct.unpack_from('!H', raw, offset + 2)[0]
        offset += 4
    row['ethertype'] = '0x%04x' % etype
    if etype != 0x0800:
        return row
    check(offset + 20 <= len(raw), 'frame %d: truncated IPv4 header' % frame['number'])
    version, ihl = raw[offset] >> 4, (raw[offset] & 15) * 4
    total = struct.unpack_from('!H', raw, offset + 2)[0]
    check(version == 4 and ihl >= 20 and total >= ihl and offset + total <= len(raw),
          'frame %d: invalid/incomplete IPv4 packet' % frame['number'])
    row.update(src_ip=str(ipaddress.IPv4Address(raw[offset + 12:offset + 16])),
               dst_ip=str(ipaddress.IPv4Address(raw[offset + 16:offset + 20])),
               protocol=str(raw[offset + 9]))
    flags_fragment = struct.unpack_from('!H', raw, offset + 6)[0]
    if raw[offset + 9] != 17:
        return row
    row['protocol'] = 'UDP'
    if flags_fragment & 0x3fff:
        row['protocol'] = 'UDP-fragment-not-reassembled'
        return row
    check(total >= ihl + 8, 'frame %d: incomplete UDP header' % frame['number'])
    udp = offset + ihl
    sport, dport, length, checksum = struct.unpack_from('!HHHH', raw, udp)
    check(length >= 8 and length == total - ihl,
          'frame %d: UDP length inconsistent with IPv4' % frame['number'])
    payload = raw[udp + 8:udp + length]
    row.update(src_port=sport, dst_port=dport, udp_payload_hex=payload.hex(),
               udp_payload_ascii=payload.decode('ascii', 'backslashreplace'))
    if row['src_ip'] == guest and row['dst_ip'] == simulator and dport == port:
        row['direction'] = 'guest_to_simulator'
    elif row['src_ip'] == simulator and row['dst_ip'] == guest and sport == port:
        row['direction'] = 'simulator_to_guest'
    for match in re.finditer(rb'\[(\d+)\]([^\r\n\x00]*)|<(\d+)>([^\r\n\x00]*)', payload):
        tag = int(match.group(1) or match.group(3))
        value = (match.group(2) if match.group(1) else match.group(4)).decode('ascii', 'backslashreplace')
        row['tags'].append(tag)
        row['messages'].append(dict(tag=tag, kind='request' if match.group(1) else 'response', value=value))
    return row


def summarize(rows, provenance):
    directions = collections.Counter(x['direction'] for x in rows)
    endpoints = collections.Counter((x['src_ip'], str(x['src_port']), x['dst_ip'], str(x['dst_port']))
                                    for x in rows if x['protocol'] == 'UDP')
    pending, pairs, unmatched, values = collections.defaultdict(collections.deque), [], [], []
    request_counts, response_counts = collections.Counter(), collections.Counter()
    for row in rows:
        for message in row['messages']:
            tag = message['tag']
            if row['direction'] == 'guest_to_simulator' and message['kind'] == 'request':
                request_counts[str(tag)] += 1
                pending[(tag, row['src_port'], row['dst_port'])].append((row, message))
            elif row['direction'] == 'simulator_to_guest' and message['kind'] == 'response':
                response_counts[str(tag)] += 1
                if tag == 1068:
                    values.append(dict(frame=row['number'], timestamp_utc=row['timestamp_utc'],
                                       value=message['value'], provenance='simulator_generated_response'))
                queue = pending[(tag, row['dst_port'], row['src_port'])]
                if queue:
                    request, command = queue.popleft()
                    pairs.append(dict(tag=tag, request_frame=request['number'], response_frame=row['number'],
                                      command=command['value'], response=message['value'],
                                      delay_us=row['timestamp_us'] - request['timestamp_us'],
                                      request_payload_hex=request['udp_payload_hex'],
                                      response_payload_hex=row['udp_payload_hex']))
                else:
                    unmatched.append(dict(frame=row['number'], tag=tag, response=message['value']))
    unmatched_requests = [dict(frame=row['number'], tag=msg['tag'], command=msg['value'])
                          for queue in pending.values() for row, msg in queue]
    duplicates = collections.Counter((x['timestamp_us'], x['frame_sha256']) for x in rows)
    return dict(provenance=provenance,
                request_provenance=('diagnostic_code_generated; not original Spitfire GUI packets'
                                    if provenance == 'diagnostic' else
                                    'declared original Spitfire executable; producer identity requires external process evidence'),
                response_provenance='simulator_generated; no real controller behavior established',
                frame_count=len(rows), direction_counts=dict(directions),
                both_directions_present=all(directions[x] > 0 for x in ('guest_to_simulator', 'simulator_to_guest')),
                udp_endpoints=[dict(src_ip=a, src_port=b, dst_ip=c, dst_port=d, frames=n)
                               for (a, b, c, d), n in sorted(endpoints.items())],
                first_timestamp_utc=rows[0]['timestamp_utc'], last_timestamp_utc=rows[-1]['timestamp_utc'],
                request_tag_counts=dict(request_counts), response_tag_counts=dict(response_counts),
                optout_1068_response_values=values, paired_messages=pairs,
                pairing_method='FIFO by tag and reversed UDP ports; heuristic, no transaction sequence ID; duplicates retained',
                unmatched_requests=unmatched_requests, unmatched_responses=unmatched,
                duplicate_timestamp_and_frame_count=sum(n - 1 for n in duplicates.values()),
                timestamp_order_regressions=sum(b['timestamp_us'] < a['timestamp_us'] for a, b in zip(rows, rows[1:])))


def csv_write(path, rows, fields):
    with open(str(path), 'w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=True) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--provenance', required=True, choices=('diagnostic', 'original'))
    parser.add_argument('--guest', default='10.19.70.2')
    parser.add_argument('--simulator', default='10.19.70.13')
    parser.add_argument('--port', type=int, default=1024)
    parser.add_argument('--report', type=Path, help='default: output basename.audit.json')
    parser.add_argument('--allow-one-way', action='store_true', help='retain incomplete diagnostic result; default fails one-way captures')
    args = parser.parse_args(argv)
    check(args.input.resolve() != args.output.resolve(), 'input/output must differ')
    check(not args.output.exists(), 'output exists; refusing to overwrite evidence')
    ipaddress.IPv4Address(args.guest)
    ipaddress.IPv4Address(args.simulator)
    raw = args.input.read_bytes()
    metadata, frames = read_pcapng(raw)
    output = encode_pcap(frames)
    verify_classic(output, frames)
    rows = [decode_frame(frame, args.guest, args.simulator, args.port) for frame in frames]
    report = summarize(rows, args.provenance)
    report.update(pcapng=metadata, input_path=str(args.input.resolve()), output_path=str(args.output.resolve()),
                  input_sha256=sha256(raw), output_sha256=sha256(output),
                  input_bytes=len(raw), output_bytes=len(output),
                  conversion='classic pcap 2.4 little-endian Ethernet; all frames retained in original order',
                  timestamp_conversion='integer floor to microseconds; exact original ticks/divisor/offset retained in frame CSV',
                  validation=dict(valid_blocks=True, no_truncated_packets=True,
                                  original_ethernet_bytes_preserved=True, output_reparsed=True,
                                  no_deduplication=True, no_packet_generation=True))
    report_path = args.report or args.output.with_suffix('.audit.json')
    frame_path = args.output.with_suffix('.frames.csv')
    pair_path = args.output.with_suffix('.pairs.csv')
    check(len({path.resolve() for path in (report_path, frame_path, pair_path)}) == 3,
          'report/CSV artifact paths collide')
    for path in (report_path, frame_path, pair_path):
        check(path.resolve() not in (args.input.resolve(), args.output.resolve()), 'artifact paths collide')
        check(not path.exists(), 'artifact exists: %s' % path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        stream.write(output)
    verify_classic(args.output.read_bytes(), frames)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    csv_write(frame_path, rows, list(rows[0].keys()))
    csv_write(pair_path, report['paired_messages'], ['tag', 'request_frame', 'response_frame', 'command',
                                                  'response', 'delay_us', 'request_payload_hex', 'response_payload_hex'])
    print(json.dumps({k: report[k] for k in ('frame_count', 'direction_counts', 'both_directions_present',
                                           'provenance', 'input_sha256', 'output_sha256')}, indent=2))
    print('Audit: %s\nFrames: %s\nPairs: %s' % (report_path, frame_path, pair_path))
    if not args.allow_one_way:
        check(report['both_directions_present'], 'both guest transmit and receive are required; artifacts retained as incomplete evidence')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (AuditError, OSError, ValueError) as exc:
        print('AUDIT FAILED: %s' % exc, file=sys.stderr)
        sys.exit(2)

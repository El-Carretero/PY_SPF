#!/usr/bin/env python3
"""Independent, stdlib-only, offline verification of one completed USB run.
Never sends packets or operates a process. Usage: python3 verify_run.py RUN_DIR
"""
import collections, hashlib, json, re, struct, sys
from pathlib import Path

root = Path(sys.argv[1])
capdir = root / 'capture' if (root / 'capture').is_dir() else root
summary = json.loads((capdir / 'summary.json').read_text(encoding='utf-8-sig'))
result = json.loads((root / 'result.json').read_text(encoding='utf-8-sig'))
rows = [json.loads(x) for x in (capdir / 'packets.jsonl').read_text().splitlines() if x]
by_adapter = collections.defaultdict(list)
for row in rows:
    by_adapter[row['interface_id']].append(row)
counts = collections.Counter()
tags = {'command': collections.Counter(), 'response': collections.Counter()}
files = []
for path in sorted(capdir.glob('adapter-*.pcap')):
    adapter_id = int(path.stem.split('-')[1])
    raw = path.read_bytes()
    assert len(raw) >= 24 and raw[:4] == b'\xd4\xc3\xb2\xa1', path
    major, minor, zone, sigfigs, snaplen, linktype = struct.unpack_from('<HHiIII', raw, 4)
    assert (major, minor, linktype) == (2, 4, 1), path
    pos = 24
    frame_index = 0
    packet_rows = sorted(by_adapter[adapter_id], key=lambda x: x['frame_index'])
    while pos < len(raw):
        assert len(raw) - pos >= 16
        sec, usec, size, original = struct.unpack_from('<IIII', raw, pos)
        pos += 16
        assert usec < 1_000_000 and size <= original and size <= snaplen
        assert len(raw) - pos >= size
        frame = raw[pos:pos+size]
        pos += size
        row = packet_rows[frame_index]
        frame_index += 1
        assert (row['frame_index'], row['pcap_sec'], row['pcap_usec'], row['captured_length'], row['original_length']) == (frame_index, sec, usec, size, original)
        counts['frames'] += 1
        off = 14
        ethertype = struct.unpack_from('!H', frame, 12)[0]
        if ethertype in (0x8100, 0x88a8):
            ethertype = struct.unpack_from('!H', frame, 16)[0]
            off += 4
        if ethertype != 0x0800 or frame[off+9] != 17:
            continue
        ihl = (frame[off] & 15) * 4
        udp = off + ihl
        src_port, dst_port, udp_size, checksum = struct.unpack_from('!HHHH', frame, udp)
        payload = frame[udp+8:udp+udp_size]
        assert payload.hex() == row['payload_hex']
        assert src_port == row['src_port'] and dst_port == row['dst_port']
        assert '.'.join(map(str, frame[off+12:off+16])) == row['src_ip']
        assert '.'.join(map(str, frame[off+16:off+20])) == row['dst_ip']
        if payload.startswith(b'Spectra-Physics:CMD_ECLIPSE,'):
            kind = 'command'
            taglist = re.findall(rb'\[(\d+)\]', payload)
            counts['write_commands'] += sum(int(tag) >= 2000 for tag in taglist)
        elif payload.startswith(b'Spectra-Physics:REPLY_ECLIPSE:'):
            kind = 'response'
            taglist = re.findall(rb'<(\d+)>', payload)
        else:
            kind, taglist = 'other', []
        counts[kind] += 1
        assert row['kind'] == kind
        if taglist:
            tags[kind][int(taglist[0])] += 1
    assert pos == len(raw) and frame_index == len(packet_rows)
    files.append({'file': path.name, 'frames': frame_index, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
assert counts['frames'] == len(rows)
assert counts['command'] == summary['command_packets']
assert counts['response'] == summary['response_packets']
assert counts['write_commands'] == summary['any_write_commands']
for item in summary['tag_statistics']:
    assert tags[item['kind']][item['tag']] == item['count']
audit = {'scope': 'Independent offline PCAP structure, byte-level JSONL agreement, tag counts and both-direction validation. No physical-controller behavior inferred.',
         'result_outcome': result['outcome'], 'counts': dict(counts), 'files': files,
         'bidirectional': counts['command'] > 0 and counts['response'] > 0,
         'tag_counts': {k: dict(v) for k, v in tags.items()},
         'actions': [{'mode': a['mode'], 'exit_code': a.get('exit_code')} for a in result['actions']]}
(root / 'independent-pcap-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
print(json.dumps(audit, indent=2))

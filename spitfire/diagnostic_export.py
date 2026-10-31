"""Export communication JSONL to CSV for offline Wireshark/tshark comparison."""
from __future__ import annotations

import argparse
import csv
from contextlib import ExitStack
import heapq
import json
from pathlib import Path

FIELDS = ('session_id', 'sequence', 'utc_time', 'frame.time_epoch', 'elapsed_seconds',
          'mode', 'connection_id', 'event', 'request_seq', 'request_id',
          'active_request_seq', 'reset_id', 'reset_step', 'disposition', 'outcome',
          'local_ip_bound', 'local_port', 'peer_ip', 'peer_port', 'sender_ip',
          'sender_port', 'udp.payload', 'payload_text', 'response', 'reason',
          'dropped_total', 'record_omitted')


def decimal_seconds(ns):
    seconds, fraction = divmod(ns, 10**9)
    return f'{seconds}.{fraction:09d}'


def export(paths, destination):
    paths = list(dict.fromkeys(Path(p).resolve() for p in paths))
    destination = Path(destination).resolve()
    if destination in paths:
        raise ValueError('CSV destination must not overwrite an input log')
    # Every file is ordered by sequence, including rotated files. Merge without
    # loading entire sessions into RAM; caller may pass rotations in any order.
    with ExitStack() as stack:
        streams = [stack.enter_context(p.open(encoding='utf-8')) for p in paths]
        rows = heapq.merge(*(map(json.loads, stream) for stream in streams),
                          key=lambda r: (r['session_id'], r['sequence']))
        output = stack.enter_context(destination.open('w', encoding='utf-8', newline=''))
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for record in rows:
            row = {key: record.get(key, '') for key in FIELDS}
            row['frame.time_epoch'] = decimal_seconds(record['wall_time_ns'])
            row['elapsed_seconds'] = decimal_seconds(record['elapsed_ns'])
            row['udp.payload'] = record.get('payload_hex', '')
            for key, ip, port in (('local_endpoint', 'local_ip_bound', 'local_port'),
                                  ('peer_endpoint', 'peer_ip', 'peer_port'),
                                  ('sender_endpoint', 'sender_ip', 'sender_port')):
                endpoint = record.get(key)
                if endpoint:
                    row[ip], row[port] = endpoint
            writer.writerow(row)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logs', type=Path, nargs='+', help='closed JSONL session files, including .1/.2 rotations')
    parser.add_argument('--output', type=Path, required=True)
    opts = parser.parse_args(argv)
    try:
        export(opts.logs, opts.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'Cannot export communication logs: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

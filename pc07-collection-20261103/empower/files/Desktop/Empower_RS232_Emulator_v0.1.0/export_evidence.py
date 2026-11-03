"""Create a bounded evidence snapshot without stopping the live emulator."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    opts = parser.parse_args()
    root = Path(__file__).resolve().parent
    rows = [json.loads(line) for line in (opts.run / 'traffic.jsonl').read_text(encoding='utf-8').splitlines()]
    counts = Counter(r['kind'] for r in rows)
    ascii_rows = [r for r in rows if r['kind'] == 'ascii_transaction']
    binary_rows = [r for r in rows if r['kind'] == 'binary_transaction']
    responses = defaultdict(set)
    for row in ascii_rows:
        responses[str(row['tag'])].add(row['response'])
    core_files = [root / p for p in ('emulator.py','spitfire_catalog.json','vendor/empower/framing.py',
                                    'vendor/empower/responses.py','vendor/empower/commands.py')]
    summary = {
        'scope': 'XP_ORIGINAL_WITH_SYNTHETIC_SASC_AND_CAPTURE_BASED_BINARY_EMPOWER_PEER',
        'physical_spitfire_rs232_tested': False,
        'real_laser_output_tested': False,
        'first_utc': rows[0]['utc'], 'last_utc': rows[-1]['utc'],
        'record_counts': dict(counts),
        'binary_opcodes': dict(Counter(f"0x{r['opcode']:02x}" for r in binary_rows)),
        'source_endpoints': sorted({tuple(r['sender']) for r in ascii_rows}),
        'ascii_response_values': {k: sorted(v) for k, v in responses.items()},
        'errors': [r for r in rows if r['kind'] in ('binary_unavailable','binary_rejected','bridge_rejected')
                   or r['kind'] == 'ascii_transaction' and str(r['response']).startswith('ERROR')],
        'gui_current_requests': [r for r in ascii_rows if r['tag'] == 2003],
        'binary_current_transactions': [r for r in binary_rows if r['opcode'] == 1],
        'run_stop_requests': [r for r in ascii_rows if r['tag'] in (2005,2006,2027,2028)],
        'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in core_files},
        'ready': json.loads((opts.run / 'ready.json').read_text()),
    }
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(opts.output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('traffic_snapshot.jsonl', ''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
        archive.writestr('summary.json', json.dumps(summary, ensure_ascii=False, indent=2))
        archive.writestr('ready.json', (opts.run / 'ready.json').read_bytes())
        if (root / 'unit_windows.txt').is_file():
            archive.writestr('unit_windows.txt', (root / 'unit_windows.txt').read_bytes())
    print(json.dumps({k: v for k, v in summary.items() if k not in ('ascii_response_values','binary_current_transactions')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':main()


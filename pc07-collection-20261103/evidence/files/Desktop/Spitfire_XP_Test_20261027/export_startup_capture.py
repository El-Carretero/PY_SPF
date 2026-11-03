"""Export this one completed XP capture's text evidence; no screenshots."""
from pathlib import Path
import base64
import hashlib
import io
import json
import zipfile

root = Path(__file__).resolve().parent / 'xp_startup_20261027_161959_190'
summary = json.loads((root / 'summary.json').read_text(encoding='utf-8'))
report = Path(summary['report_directory']).resolve()
if not report.is_relative_to(root.resolve()):
    raise ValueError('Report outside capture directory')
paths = [root / 'ready.json', root / 'summary.json']
paths += sorted(p for p in report.iterdir() if p.is_file() and p.suffix in {'.json', '.jsonl', '.csv', '.html'})
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in paths:
        archive.write(path, path.relative_to(root).as_posix())
payload = buffer.getvalue()
encoded = base64.b64encode(payload).decode('ascii')
transfer = root / 'text_evidence_transfer.b64'
with transfer.open('x', encoding='ascii', newline='\n') as stream:
    stream.write('\n'.join(encoded[i:i+8000] for i in range(0, len(encoded), 8000)) + '\n')
print(json.dumps({'archive_sha256': hashlib.sha256(payload).hexdigest(),
                  'archive_bytes': len(payload), 'base64_file': str(transfer),
                  'base64_lines': (len(encoded) + 7999) // 8000,
                  'files': [{'name': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
                             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}))

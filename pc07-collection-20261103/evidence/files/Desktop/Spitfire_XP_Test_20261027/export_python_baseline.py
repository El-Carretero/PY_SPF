"""Export completed Python backend evidence; excludes screenshots and source."""
from pathlib import Path
import base64
import hashlib
import io
import json
import zipfile

root = Path(__file__).resolve().parent / 'python_baseline_20261027_run01'
json.loads((root / 'summary.json').read_text(encoding='utf-8'))
paths = [p for p in sorted(root.rglob('*')) if p.is_file() and p.suffix in {'.json', '.jsonl', '.csv'}]
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
                  'base64_characters': len(encoded), 'base64_lines': (len(encoded) + 7999) // 8000,
                  'files': [{'name': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
                             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}))

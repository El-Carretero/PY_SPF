"""Package explicit release inputs, excluding build caches and stale evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {'__pycache__', '.build-venv', '.venv', 'build', 'release', 'dist',
           'verification_reports', 'validation_matrix', 'validation_output'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--windows-binaries', help='optional explicit directory holding verified EXEs')
    parser.add_argument('--evidence', help='optional exact final validation directory')
    parser.add_argument('--wheel', help='optional exact verified wheel file')
    args = parser.parse_args()
    target = Path(args.output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError('Refusing to overwrite release; choose a fresh output filename')
    members = []
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if (path.is_file() and not path.is_symlink() and not EXCLUDE.intersection(rel.parts)
                and not any(p.endswith('.egg-info') for p in rel.parts)
                and path.suffix not in {'.pyc', '.spec'} and path.name != 'MANIFEST_SHA256.txt'):
            members.append((path, str(rel).replace('\\', '/')))
    if args.windows_binaries:
        for path in sorted(Path(args.windows_binaries).glob('*.exe')):
            members.append((path, 'dist/' + path.name))
    if args.wheel:
        wheel = Path(args.wheel)
        if not wheel.is_file() or wheel.suffix != '.whl':
            raise ValueError('wheel must identify a verified .whl file')
        members.append((wheel, 'release/' + wheel.name))
    if args.evidence:
        base = Path(args.evidence)
        for path in sorted(base.rglob('*')):
            if path.is_file() and path.suffix in {'.json', '.jsonl', '.txt', '.html'}:
                members.append((path, 'validation_0.3.0/' + path.relative_to(base).as_posix()))
    hashes = []
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in members:
            data = path.read_bytes()
            archive.writestr('Spitfire_Twin_Verifier/' + name, data)
            hashes.append(hashlib.sha256(data).hexdigest() + '  ' + name)
        archive.writestr('Spitfire_Twin_Verifier/MANIFEST_SHA256.txt', '\n'.join(hashes) + '\n')
    print(json.dumps({'path': str(target), 'files': len(members) + 1,
                      'size_bytes': target.stat().st_size,
                      'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()

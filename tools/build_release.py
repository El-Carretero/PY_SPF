"""Build developer source distributions under dist/source/PY_SPF_1.2.

No application, diagnostic session or instrument connection is started. Runtime
logs, developer environments and private device-capture evidence are excluded.
Historical Legacy archives and the primary Native installer output are untouched.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE_NAME = 'PY_SPF_1.2'
PACKAGE_VERSION = '1.2.1'
SOURCE_OUTPUT = PurePosixPath('dist/source') / RELEASE_NAME
DEVELOPMENT_GUIDE = 'docs/source-development.md'
ROOT_FILES = {
    '.gitattributes', '.gitignore', 'README.md', 'README.ko.md',
    'RELEASE.ko.md', 'THIRD_PARTY_NOTICES.md', 'docs/internal-trigger-10hz.md',
    'docs/hv-switch-1-2.md', 'docs/shared-ext-rate.md',
    'pyproject.toml', 'requirements.txt', 'requirements-build.txt', 'run_spitfire.py',
    'install.bat', 'run_native.bat', 'run_readonly.bat', 'run_demo.bat',
}
ANALYSIS_DATA = {
    'cab_manifest.json', 'callback_coverage.json', 'callbacks.json',
    'command_tables.json', 'cvi_enum_refs.json', 'decoders.json',
    'functions.json', 'logging_source_identity.json', 'poll_sequences.json',
    'server_gui_spec.json', 'symbols.json', 'symbols.tsv',
    'native_oracle_results.json', 'native_callback_extended_results.json',
    'native_decoder_oracle_results.json', 'native_decoder_oracle_summary.json',
    'native_decoder_extra_results.json', 'native_decoder_extra_summary.json',
    'native_logging_results.json', 'protocol_validation.json',
    'optout_protocol_verification.json',
}
PRIVATE_MARKERS = re.compile(
    rb'(?i)(?:[A-Z]:\\+(?:Users|Documents and Settings)\\+|/workspace/artifacts/|run-\d{4}(?:-\d{1,6}){4,8}|\d{8}T\d{6}Z-\d+-\d+\.zip)'
)


def public_source_path(name: str) -> bool:
    """Curate distributable source; never copy whole developer directories."""
    path = PurePosixPath(name)
    if name in ROOT_FILES or name == DEVELOPMENT_GUIDE:
        return True
    if any(part in {'__pycache__', '.git', '.venv', '.venv-native', '.python32',
                    '.installer-cache', 'logs', 'build', 'dist', 'Legacy', 'node_modules'} for part in path.parts):
        return False
    if path.suffix.lower() in {'.jsonl', '.log', '.pcap', '.pcapng', '.pyc', '.pyo'}:
        return False
    if name.startswith('spitfire/'):
        return path.suffix in {'.py'} or name.startswith('spitfire/resources/')
    if name.startswith('tests/'):
        return path.suffix in {'.py', '.ps1'} or name.startswith('tests/fixtures/') and path.suffix == '.json'
    if name.startswith('tools/'):
        return path.suffix in {'.py', '.ps1'}
    if name.startswith('packaging/windows/'):
        return path.suffix in {'.py', '.ps1', '.spec', '.iss', '.manifest', '.md'}
    if name.startswith('analysis/reference/'):
        return path.name in {'SPITFIRE.EXE', 'SPITFIRE.UIR', 'SERVER.UIR'}
    if name.startswith('analysis/'):
        return (path.suffix in {'.py', '.java', '.c', '.md'} or path.name in ANALYSIS_DATA
                or path.name.startswith(('release_1_0_', 'release_1_2_')) and path.suffix == '.json')
    return name == 'previews/native-cli.png' or name.startswith('previews/release-1.0-') and path.suffix == '.png'


def check_public_content(name: str, data: bytes) -> None:
    if PurePosixPath(name).suffix in {'.md', '.json', '.txt'} and PRIVATE_MARKERS.search(data):
        raise RuntimeError(f'Private capture path/identifier must be removed before packaging: {name}')
    if name.startswith('tests/fixtures/') and name.endswith('.json'):
        if json.loads(data).get('fixture_kind') != 'synthetic':
            raise RuntimeError(f'Public test fixture must declare synthetic provenance: {name}')


def source_entries(root: Path = ROOT):
    paths = None
    if (root/'.git').exists():
        try:
            paths = subprocess.check_output(
                ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                cwd=root, stderr=subprocess.DEVNULL
            ).decode().split('\0')
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    if paths is None:
        # A distributed source ZIP intentionally has no Git metadata. Walk only
        # distributable roots and prune generated environments before scanning.
        paths = list(ROOT_FILES)
        for folder in ('spitfire', 'tests', 'tools', 'analysis', 'previews', 'packaging', 'docs'):
            for directory, children, files in os.walk(root/folder):
                children[:] = [name for name in children if name not in {
                    '__pycache__', '.git', '.venv', '.venv-native', '.python32',
                    '.installer-cache', 'logs', 'build', 'dist', 'Legacy', 'node_modules'}]
                paths.extend((Path(directory)/name).relative_to(root).as_posix() for name in files)
    for name in sorted(set(paths)):
        path = root / name
        if not name or not public_source_path(name) or not path.is_file():
            continue
        data = path.read_bytes()
        check_public_content(name, data)
        if name.endswith(('.bat', '.ps1')):
            data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        yield name, data


def source_readme(root: Path) -> bytes:
    """Derive fresh build instructions from current source, never Legacy files."""
    instructions = (root / DEVELOPMENT_GUIDE).read_bytes()
    check_public_content(DEVELOPMENT_GUIDE, instructions)
    # The copied guide moves from docs/ to dist/source/<release>/.
    instructions = instructions.replace(b'](../', b'](../../../')
    return (
        f'# {RELEASE_NAME} developer source distribution\n\n'
        'Generated by tools/build_release.py. This source ZIP and wheel are '
        'developer artifacts; the current standalone Windows installer is a '
        'separate distribution. Historical archives under Legacy are not '
        'build inputs and are not replaced.\n\n'
    ).encode('utf-8') + instructions


def main():
    version = re.search(r'^version = "([^"]+)"', (ROOT/'pyproject.toml').read_text(), re.M)[1]
    if version != PACKAGE_VERSION:
        raise RuntimeError('Update the release identity and package version together before building')
    sources = list(source_entries(ROOT))  # Fail privacy/fixture checks before producing artifacts.
    readme = source_readme(ROOT)
    output = ROOT.joinpath(*SOURCE_OUTPUT.parts)
    output.mkdir(parents=True, exist_ok=True)
    wheel_name = f'spitfire_gui_reconstruction-{version}-py3-none-any.whl'
    wheel = output/wheel_name
    if wheel.exists():wheel.unlink()
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(output), str(ROOT)], check=True)
    if not wheel.is_file():raise RuntimeError(f'Expected wheel was not produced: {wheel_name}')
    with zipfile.ZipFile(wheel) as installed:
        for resource in (ROOT/'spitfire/resources').rglob('*'):
            if resource.is_file() and '__pycache__' not in resource.parts:
                name = resource.relative_to(ROOT).as_posix()
                if installed.read(name) != resource.read_bytes():raise RuntimeError(f'Wheel resource differs: {name}')
        metadata = installed.read(f'spitfire_gui_reconstruction-{version}.dist-info/METADATA').decode()
        if f'Version: {version}\n' not in metadata:raise RuntimeError('Wheel metadata version differs')
        if not any(name.endswith('/THIRD_PARTY_NOTICES.md') for name in installed.namelist()):
            raise RuntimeError('Wheel is missing bundled vendor resource notices')
    archive = output/f'{RELEASE_NAME}.zip'
    prefix = RELEASE_NAME+'/'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name,data in sources:bundle.writestr(prefix+name,data)
        bundle.write(wheel, prefix + (SOURCE_OUTPUT / wheel.name).as_posix())
        bundle.writestr(prefix + (SOURCE_OUTPUT / 'README.md').as_posix(), readme)
    (output/'README.md').write_bytes(readme)
    manifest = {artifact.name:{'bytes':artifact.stat().st_size,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()} for artifact in (archive,wheel)}
    (output/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__ == '__main__':main()

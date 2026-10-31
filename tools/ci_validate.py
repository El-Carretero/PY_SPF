"""Repeatable Windows/Linux CI entry point. Every app/test child is guarded."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
EXEC = ROOT / 'tools' / 'ci_exec.py'


def version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('portable', 'native-boundary'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    opts = parser.parse_args()
    output = opts.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Reusing a local output path must not preserve old failure logs or images.
    for name in ('pytest.xml', 'profile-setup.error.txt'):
        (output / name).unlink(missing_ok=True)
    for phase_name in ('pytest', 'headless-demo', 'qt-render'):
        for suffix in ('stdout.txt', 'stderr.txt', 'error.txt'):
            (output / f'{phase_name}.{suffix}').unlink(missing_ok=True)
    if (output / 'qt-panels').is_dir():
        for image in (output / 'qt-panels').glob('panel_*.png'):
            image.unlink()
    bits = struct.calcsize('P') * 8
    environment = {
        'profile': opts.profile, 'os': platform.platform(), 'system': platform.system(),
        'python': sys.version, 'executable': sys.executable, 'bits': bits,
        'packages': {name: version(name) for name in ('spitfire-external-control', 'pytest', 'PySide6')},
        'qt_platform': 'offscreen', 'network_policy': 'simulator and loopback only',
        'github': {key: os.environ.get(key) for key in (
            'GITHUB_SHA', 'GITHUB_REF', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'RUNNER_OS')},
        'not_tested': ['physical instruments, optical output and timing',
                       'Native NI GUI initialization/rendering and NI DLL compatibility',
                       '07 PC drivers, display and installed hardware'],
    }
    (output / 'environment.json').write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding='utf-8')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONUTF8='1', PYTHONUNBUFFERED='1')
    phases = []

    def phase(name, args, *, cwd=ROOT, verify=None):
        command = [sys.executable, str(EXEC), *args]
        record = {'name': name, 'command': command, 'cwd': str(cwd), 'status': 'failed'}
        try:
            result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=180)
            (output / f'{name}.stdout.txt').write_text(result.stdout, encoding='utf-8')
            (output / f'{name}.stderr.txt').write_text(result.stderr, encoding='utf-8')
            record['exit_code'] = result.returncode
            if result.returncode:
                raise RuntimeError(f'{name} exited with {result.returncode}')
            if verify:
                record['evidence'] = verify(result.stdout)
            record['status'] = 'passed'
        except Exception as exc:
            record['error'] = str(exc)
            (output / f'{name}.error.txt').write_text(traceback.format_exc(), encoding='utf-8')
            print(f'{name}: {exc}', flush=True)
        phases.append(record)
        print(f"{name}: {record['status']}", flush=True)

    try:
        if opts.profile == 'portable':
            if bits != 64 or not version('PySide6'):
                raise RuntimeError('Portable profile requires x64 Python and installed PySide6')
            import PySide6.QtCore
            environment['qt_version'] = PySide6.QtCore.qVersion()
            tests = [str(ROOT / 'tests')]
        else:
            if sys.platform != 'win32' or bits != 32:
                raise RuntimeError('Native boundary profile requires Windows x86 Python')
            if version('PySide6'):
                raise RuntimeError('Native boundary profile must run without Qt')
            tests = [str(ROOT / 'tests' / name) for name in (
                'test_external_native.py', 'test_native_requirements.py',
                'test_ci_network_guard.py', 'test_protocol_recovery.py')]

        def check_junit(_):
            tree = ET.parse(output / 'pytest.xml')
            cases = tree.findall('.//testcase')
            skipped = tree.findall('.//skipped')
            if not cases or skipped:
                raise AssertionError(f'Expected executed tests without silent skips; cases={len(cases)}, skipped={len(skipped)}')
            return {'junit_testcases': len(cases), 'skipped': len(skipped)}

        phase('pytest', ['pytest', *tests, '-ra', '-q', f'--junitxml={output / "pytest.xml"}'], verify=check_junit)

        # Run CLI demos outside the source tree to exercise the installed package.
        with tempfile.TemporaryDirectory(prefix='py-spf-ci-') as work:
            common = ['spitfire', '--demo', '--host', '127.0.0.1', '--port', '9',
                      '--local-port', '0', '--tcp-port', '0', '--tcp-host', '127.0.0.1',
                      '--config', str(Path(work) / 'config.sp'), '--data-dir', work, '--duration', '2']

            def check_demo(stdout):
                result = json.loads(stdout)
                if result.get('mode') != 'simulator' or result.get('connected') is not True or result.get('controls_updated', 0) <= 0:
                    raise AssertionError(f'Simulator did not connect/update: {result}')
                return result

            phase('headless-demo', [*common, '--headless'], cwd=work, verify=check_demo)
            if opts.profile == 'portable':
                render = output / 'qt-panels'
                def check_panels(_):
                    expected = {f'panel_{n}.png' for n in (1, 2, 3, 4, 5, 6, 7, 'server')}
                    actual = {p.name for p in render.glob('*.png')}
                    if actual != expected or any(p.stat().st_size == 0 for p in render.glob('*.png')):
                        raise AssertionError(f'Expected eight nonempty Qt panels; found {actual}')
                    return sorted(actual)
                phase('qt-render', [*common, '--backend', 'qt', '--render-dir', str(render)], cwd=work, verify=check_panels)
    except Exception as exc:
        phases.append({'name': 'profile-setup', 'status': 'failed', 'error': str(exc)})
        (output / 'profile-setup.error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        print(f'profile-setup: {exc}', flush=True)
    finally:
        (output / 'environment.json').write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = bool(phases) and all(p['status'] == 'passed' for p in phases)
        result = {'passed': passed, 'environment': environment, 'phases': phases}
        (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = f"### External Control: {platform.system()} / Python {platform.python_version()} / {bits}-bit / {opts.profile}\n\n"
        summary += '| Phase | Result |\n|---|---|\n'
        summary += ''.join(f"| {p['name']} | {p['status']} |\n" for p in phases)
        summary += '\nNetwork: simulator and Python loopback sockets only. Native NI GUI and physical hardware remain untested.\n'
        (output / 'summary.md').write_text(summary, encoding='utf-8')
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
                handle.write(summary)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())

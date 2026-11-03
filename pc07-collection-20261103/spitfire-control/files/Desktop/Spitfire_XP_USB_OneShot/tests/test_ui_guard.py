#!/usr/bin/env python3
"""Compile the actual native proof parser with deterministic host-side stubs."""
import json
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
native = (root / 'src/readonly_ui.c').read_text()
guard = native[native.index('static int decimal('):native.index('static int action_guard(')]
template = (root / 'tests/ui_guard_fixture.c.in').read_text()
with tempfile.TemporaryDirectory(prefix='spitfire-proof-') as directory:
    tmp = Path(directory)
    source = template.replace('/* NATIVE_GUARD */', guard).replace('TEST_PROOF_PATH', json.dumps(str(tmp / 'proof.txt')))
    (tmp / 'guard.c').write_text(source)
    subprocess.run(['cc', '-std=c99', '-O2', str(tmp / 'guard.c'), '-o', str(tmp / 'guard')], check=True)
    subprocess.run([str(tmp / 'guard')], check=True)

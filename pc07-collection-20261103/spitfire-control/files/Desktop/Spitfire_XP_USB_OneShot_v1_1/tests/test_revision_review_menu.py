#!/usr/bin/env python3
"""Independent extraction of production popup filtering and final freeze guard.

Window and metadata readers are stubbed; the actual C ownership/ambiguity/freeze
functions are inserted verbatim. No executable original, Windows, or network.
"""
from pathlib import Path
import re
import subprocess

base = Path(__file__).resolve().parents[1]
source = (base / 'src/readonly_ui.c').read_text()
template = (base / 'tests/revision_review_popup_fixture.c.in').read_text()

def function(name):
    match = re.search(r'^static\s+[^\n;]+\b' + re.escape(name) + r'\([^;\n]*\)\s*\{', source, re.M)
    assert match, name
    start = match.start()
    at = source.index('{', start)
    depth = 1
    at += 1
    while depth:
        depth += (source[at] == '{') - (source[at] == '}')
        at += 1
    return source[start:at]

snapshot = re.search(r'typedef struct \{\n HWND hwnd;DWORD window_handle,window_base,menu_handle,menu_base;[\s\S]+?\} MenuSnapshot;', source)
assert snapshot
generated = template.replace('/* SNAPSHOT_TYPE */', snapshot.group()).replace(
    '/* ACTUAL_FUNCTIONS */', function('popup_cb') + '\n' + function('observed_popup'))
out = base / 'build/revision-review'
out.mkdir(parents=True, exist_ok=True)
c = out / 'popup_envelope.c'
c.write_text(generated)
exe = out / 'popup_envelope'
subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)

#!/usr/bin/env python3
"""Independent source extraction of frozen-heading and final input guards.

The Windows reader boundary is modeled; the production snapshot comparison and
final target/ownership check execute unchanged. No original program is run.
"""
from pathlib import Path
import re
import subprocess

base = Path(__file__).resolve().parents[1]
source = (base / 'src/readonly_ui.c').read_text()
template = (base / 'tests/revision_review_heading_fixture.c.in').read_text()


def function(name):
    match = re.search(r'^static\s+[^\n;]+\b' + re.escape(name) + r'\([^;\n]*\)\s*\{', source, re.M)
    assert match, name
    at = source.index('{', match.start()) + 1
    depth = 1
    while depth:
        depth += (source[at] == '{') - (source[at] == '}')
        at += 1
    return source[match.start():at]


snapshots = re.search(r'typedef struct \{\n HWND hwnd;DWORD window_handle,window_base,menu_handle,menu_base;[\s\S]+?\} HeaderSnapshot;', source)
assert snapshots
generated = template.replace('/* SNAPSHOT_TYPES */', snapshots.group()).replace(
    '/* ACTUAL_FUNCTIONS */', function('observed_heading') + '\n' + function('menu_target_unchanged'))
generated = generated.replace('/* GDI_FEATURE */', '#define HAS_GDI_FIELDS ' + str(int('font_measure_kind' in snapshots.group())))
out = base / 'build/revision-review'
out.mkdir(parents=True, exist_ok=True)
c = out / 'heading_envelope.c'
c.write_text(generated)
exe = out / 'heading_envelope'
subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True)

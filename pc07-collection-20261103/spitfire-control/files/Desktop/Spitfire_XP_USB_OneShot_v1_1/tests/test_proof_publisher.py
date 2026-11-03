#!/usr/bin/env python3
"""Validate actual publisher path/error/retry contract with mocked Win32 calls.
No Windows process, device or original Spitfire binary is executed.
"""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parent.parent
source=(root/'src/proof_publish.c').read_text()
a=source.index('static WCHAR source_path'); b=source.index('static int snapshot_transient',a)
original=source[a:b].replace('static WCHAR snapshot_temp[MAX_PATH];\n','').replace('static BYTE snapshot_bytes[524288];\n','')
code=(root/'tests/proof_publisher_fixture.c.in').read_text().replace('@NATIVE_FUNCTIONS@',original)
build=root/'build/proof-contract';build.mkdir(parents=True,exist_ok=True)
(build/'proof_contract.c').write_text(code)
subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror',str(build/'proof_contract.c'),'-o',str(build/'proof_contract')],check=True)
result=subprocess.run([str(build/'proof_contract')],capture_output=True,text=True)
(root/'tests/proof-publisher-test-results.txt').write_text(result.stdout+result.stderr)
print(result.stdout,end='')
if result.returncode: raise SystemExit(result.returncode)
b=source.index('void WINAPI publish_entry',a)
code=(root/'tests/status_snapshot_fixture.c.in').read_text().replace('@NATIVE_FUNCTIONS@',source[a:b])
(build/'snapshot_contract.c').write_text(code)
subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(build/'snapshot_contract.c'),'-o',str(build/'snapshot_contract')],check=True)
result=subprocess.run([str(build/'snapshot_contract')],capture_output=True,text=True)
(root/'tests/status-snapshot-test-results.txt').write_text(result.stdout+result.stderr)
print(result.stdout,end='')
raise SystemExit(result.returncode)

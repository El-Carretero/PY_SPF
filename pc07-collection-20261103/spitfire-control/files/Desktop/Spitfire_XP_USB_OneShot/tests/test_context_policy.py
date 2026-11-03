#!/usr/bin/env python3
"""Test actual C focus classification, visible-window rules, and final input gate.
No Windows/original process or DLL is executed. Functions are extracted verbatim.
"""
from pathlib import Path
import re, subprocess
root=Path(__file__).resolve().parent.parent
source=(root/'src/readonly_ui.c').read_text()
def function(name):
    start=re.search(r'static (?:int|BOOL CALLBACK) '+re.escape(name)+r'\(',source).start()
    brace=source.index('{',start); depth=1; end=brace+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}'); end+=1
    return source[start:end]
functions='\n'.join(function(n) for n in ('focus_policy','context_window_cb','input_tick_matches'))
code=(root/'tests/context_policy_fixture.c.in').read_text().replace('@NATIVE_FUNCTIONS@',functions)
build=root/'build/context-policy'; build.mkdir(parents=True,exist_ok=True)
(build/'context_policy.c').write_text(code)
subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(build/'context_policy.c'),'-o',str(build/'context_policy')],check=True)
result=subprocess.run([str(build/'context_policy')],capture_output=True,text=True)
(root/'tests/context-policy-test-results.txt').write_text(result.stdout+result.stderr)
print(result.stdout,end='')
raise SystemExit(result.returncode)

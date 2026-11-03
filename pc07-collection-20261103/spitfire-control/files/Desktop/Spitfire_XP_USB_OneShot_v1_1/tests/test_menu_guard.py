#!/usr/bin/env python3
"""Exercise actual native menu reader against a bounded synthetic CVI memory graph.
No original process, DLL, Windows API or network is executed.
"""
from pathlib import Path
import re,subprocess
root=Path(__file__).resolve().parent.parent
source=(root/'src/readonly_ui.c').read_text()
def function(name):
 start=re.search(r'static (?:int|BOOL CALLBACK) '+name+r'\([^;{}]*\)\s*\{',source).start()
 brace=source.index('{',start);depth=1;end=brace+1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
records='\n'.join(re.search(r'typedef struct \{[^{}]+\} '+name+';',source).group() for name in ('Panel','MenuSnapshot','HeaderSnapshot','FocusRecord'))
code=(root/'tests/menu_guard_fixture.c.in').read_text().replace('@RECORDS@',records).replace('@FUNCTIONS@','\n'.join(function(n) for n in ('focus_read_word','readable_base','menu_read_bytes','menu_list_entries','menu_expected_items','heading_gdi_widths','heading_text_width','inspect_heading','inspect_popup')))
build=root/'build/menu-guard';build.mkdir(parents=True,exist_ok=True)
(build/'menu_guard.c').write_text(code)
subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(build/'menu_guard.c'),'-o',str(build/'menu_guard')],check=True)
p=subprocess.run([str(build/'menu_guard')],capture_output=True,text=True)
(root/'tests/menu-guard-test-results.txt').write_text(p.stdout+p.stderr)
print(p.stdout,end='');print(p.stderr,end='');raise SystemExit(p.returncode)

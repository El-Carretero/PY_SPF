#!/usr/bin/env python3
"""Run the actual native read-only focus lookup/policy against synthetic memory.

No original program or DLL is loaded/executed; no Windows process is contacted.
The source functions are extracted verbatim so these cases validate the shipped
pointer binding and selector translation rather than a rewritten implementation.
"""
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parent.parent
source = (root / 'src/readonly_ui.c').read_text()

def function(name):
    start = re.search(r'static int ' + re.escape(name) + r'\(', source).start()
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

record = re.search(r'typedef struct \{[^{}]+\} FocusRecord;', source).group()
panel_record = re.search(r'typedef struct \{[^{}]+\} Panel;', source).group()
code = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <wchar.h>
typedef uint32_t DWORD;
typedef void *HWND;
typedef void *HANDLE;
typedef wchar_t WCHAR;
#define FALSE 0
#define PROCESS_QUERY_INFORMATION 0x400
#define PROCESS_VM_READ 0x10
#define _snprintf snprintf
#define ZeroMemory(p,n) memset(p,0,n)
static HWND main_hwnd=(HWND)(uintptr_t)0x223344;
static DWORD loaded_cvi_base=0x68420000u;
typedef struct {DWORD address,value;} Word;
static Word words[100];static int word_count,passed,failed;
static void set(DWORD address,DWORD value){int i;for(i=0;i<word_count;i++)if(words[i].address==address){words[i].value=value;return;}words[word_count].address=address;words[word_count++].value=value;}
static int focus_read_word(DWORD address,DWORD *value,DWORD *error){int i;for(i=0;i<word_count;i++)if(words[i].address==address){*value=words[i].value;return 1;}*error=5;return 0;}
static int32_t GetWindowLongA(HWND h,int offset){(void)offset;return h==main_hwnd?0x10000:0;}
'''
code += record + '\n' + '\n'.join(function(n) for n in ('focus_policy', 'readable_base', 'observe_main_focus'))
code += '\n' + panel_record + r'''
static DWORD original_pid=123;
static HWND panel_hwnd,action_hidden_hwnd;
static HANDLE focus_process;
static int hidden_found=1,process_allowed=1,evidence_allowed=1,context_serial;
static const char *context_reason="";
static int find_hidden_panel(const Panel*p){(void)p;panel_hwnd=main_hwnd;return hidden_found;}
static HANDLE OpenProcess(DWORD rights,int inherit,DWORD pid){(void)rights;(void)inherit;(void)pid;return process_allowed?(HANDLE)(uintptr_t)1:NULL;}
static void CloseHandle(HANDLE h){(void)h;}
static FILE *openout(const char*name,const char*mode){(void)name;(void)mode;return evidence_allowed?tmpfile():NULL;}
static void js(FILE*f,const char*s){fprintf(f,"\"%s\"",s);}
static void event(const char*a,const char*b,const char*c,int d){(void)a;(void)b;(void)c;(void)d;}
'''
code += '\n' + function('hidden_target_guard')
code += r'''
static void fixture(void){
 word_count=0;
 hidden_found=process_allowed=evidence_allowed=1;context_reason="";action_hidden_hwnd=NULL;focus_process=NULL;
 set(0x10000,0x11000);set(0x11058,0x223344);set(0x1102c,loaded_cvi_base+0x1aebb1);
 set(0x11050,0x12000);set(0x12000,0x13000);set(0x1305c,0x10000);
 set(0x13078,loaded_cvi_base+0x16aaae);set(0x13074,0x14000);set(0x14000,0x15000);
 set(0x15000,0xeb13);set(0x150a0,0x12000);set(0x15028,6);set(0x41417c,6);
 set(0x13044,0x2da8);set(0x13054,0x16000);set(0x16000,0x17000);
 set(0x17008,3);set(0x1700c,1);
 set(0x150d4,0x18000);set(0x18000,0x19000);set(0x19004,0xb00bdeed);
 set(0x19010,4);set(0x19014,1);set(0x19018,0x1a000);set(0x1a000,0x1b000);
 set(0x1b000,0xeb19);set(0x1b028,3);set(0x1b0ac,2);
}
static void hidden_fixture(void){fixture();set(0x13044,0);set(0x13048,0);set(0x15028,2);set(0x414188,2);}
static int allow(FocusRecord*f){return observe_main_focus(f)&&focus_policy(f->valid,f->active,f->node,f->kind,f->public_id,f->matches);}
static void check(const char*name,int ok){printf("%s %s\n",ok?"PASS":"FAIL",name);if(ok)passed++;else failed++;}
int main(void){FocusRecord f;Panel p;memset(&p,0,sizeof(p));p.mode="temperature";p.panel_global=0x414188;
 fixture();check("closed main motor ring permits mouse-only navigation",allow(&f));
 check("selector1 maps native2 then public3, not direct selector",f.selector==1&&f.native_id==2&&f.public_id==3&&f.matches==1);
 fixture();set(0x13044,0);check("inactive remembered closed main ring remains classifiable",allow(&f));
 fixture();set(0x13044,0);set(0x1700c,39);set(0x1b0ac,40);set(0x1b028,41);check("inactive remembered editable knob remains blocked",!allow(&f)&&f.public_id==41&&f.active==0);
 fixture();set(0x13044,0);set(0x13054,0);check("no selection is allowed only with inactive context",allow(&f));
 fixture();set(0x13054,0);check("active context without selection fails closed",!allow(&f));
 fixture();set(0x17008,2);check("reviewed no-control node is accepted",allow(&f));
 fixture();set(0x17008,1);check("unimplemented selector kind fails closed",!allow(&f));
 fixture();set(0x11058,0x999999);check("wrong window backreference blocks",!allow(&f));
 fixture();set(0x1102c,loaded_cvi_base+0x1aebb2);check("wrong window callback blocks",!allow(&f));
 fixture();set(0x1305c,0x20000);check("wrong generic-panel backreference blocks",!allow(&f));
 fixture();set(0x13078,loaded_cvi_base+0x16aaaf);check("wrong generic callback blocks",!allow(&f));
 fixture();set(0x15000,0xeb19);check("wrong wrapper type blocks",!allow(&f));
 fixture();set(0x150a0,0x99900);check("wrong wrapper-to-panel binding blocks",!allow(&f));
 fixture();set(0x15028,7);check("wrong application main panel ID blocks",!allow(&f));
 fixture();set(0x19004,0);check("invalid native control-list header blocks",!allow(&f));
 fixture();set(0x19014,2);set(0x1901c,0x1a000);check("duplicate matching controls block",!allow(&f)&&f.matches==2);
 fixture();set(0x1b0ac,3);check("unmatched native selector blocks",!allow(&f)&&f.matches==0);
 fixture();set(0x1700c,256);check("unbounded selector blocks",!allow(&f));
 fixture();set(0x19014,257);check("unbounded control count blocks",!allow(&f));
 fixture();set(0x11050,0x222000);check("unreadable pointer blocks",!allow(&f)&&f.error==5);
 hidden_fixture();check("hidden target requires bound identity and both clean context fields",hidden_target_guard(&p,NULL)&&action_hidden_hwnd==main_hwnd);
 hidden_fixture();set(0x13044,1);check("hidden target active44 alone blocks opening",!hidden_target_guard(&p,NULL));
 hidden_fixture();set(0x13048,1);check("hidden target editor48 alone blocks opening",!hidden_target_guard(&p,NULL));
 hidden_fixture();set(0x414188,9);check("hidden target wrong application global ID blocks",!hidden_target_guard(&p,NULL));
 hidden_fixture();check("hidden target HWND replacement blocks",!hidden_target_guard(&p,(HWND)(uintptr_t)0x999999));
 hidden_fixture();hidden_found=0;check("missing or ambiguous hidden target blocks",!hidden_target_guard(&p,NULL));
 hidden_fixture();process_allowed=0;check("unreadable original process blocks hidden target",!hidden_target_guard(&p,NULL));
 hidden_fixture();evidence_allowed=0;check("missing hidden-context evidence blocks opening",!hidden_target_guard(&p,NULL));
 printf("{\"tests\":%d,\"passed\":%d,\"failed\":%d}\n",passed+failed,passed,failed);
 return failed?1:0;
}
'''
build = root / 'build/focus-review'
build.mkdir(parents=True, exist_ok=True)
(build / 'focus_guard_review.c').write_text(code)
subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation', '-O2', str(build / 'focus_guard_review.c'), '-o', str(build / 'focus_guard_review')], check=True)
result = subprocess.run([str(build / 'focus_guard_review')], capture_output=True, text=True)
(root / 'tests/focus-test-results.txt').write_text(result.stdout)
print(result.stdout, end='')
raise SystemExit(result.returncode)

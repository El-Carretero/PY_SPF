#!/bin/sh
set -eu
cd "$(dirname "$0")"
driver_zig=${DRIVER_ZIG:-zig}
driver_zig_lib=$("$driver_zig" env | python3 -c 'import json,sys; print(json.load(sys.stdin)["lib_dir"])')
mkdir -p bin build
"$driver_zig" cc -target x86-windows-gnu -std=c99 -Os -Wall -Wextra -Werror -fno-builtin -nostdlib \
 -isystem "$driver_zig_lib/libc/include/any-windows-any" \
 -Wl,-e,publish_entry@0 -Wl,--subsystem,windows -o bin/proof_publish.exe src/proof_publish.c \
 -lkernel32 -lshell32
python3 - <<'PY'
from pathlib import Path
import hashlib,json,re,struct,subprocess
p=Path('bin/proof_publish.exe');b=bytearray(p.read_bytes());pe=struct.unpack_from('<I',b,0x3c)[0];opt=pe+24
assert b[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',b,pe+4)[0]==0x14c
assert struct.unpack_from('<H',b,opt)[0]==0x10b
struct.pack_into('<HH',b,opt+40,5,1);struct.pack_into('<HH',b,opt+48,5,1);p.write_bytes(b)
info=subprocess.check_output(['objdump','-p',str(p)],text=True)
dlls=re.findall(r'DLL Name: (.+)',info)
assert {x.lower() for x in dlls}=={'kernel32.dll','shell32.dll'}
assert 'DeleteFile' not in info and 'MoveFileExW' in info
assert struct.unpack_from('<H',b,opt+68)[0]==2
report={'format':'PE32 i386','minimum_os':[5,1],'minimum_subsystem':[5,1],'subsystem':'windows',
        'imports_dlls':dlls,'no_crt':True,'no_delete_file':True,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()}
Path('build/proof_publish.pe-validation.json').write_text(json.dumps(report,indent=2)+'\n')
Path('build/proof_publish.imports.txt').write_text(info)
print(json.dumps(report,indent=2))
PY

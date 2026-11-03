#!/bin/sh
set -eu
cd "$(dirname "$0")"
driver_zig=${DRIVER_ZIG:-zig}
driver_zig_lib=$("$driver_zig" env | python3 -c 'import json,sys; print(json.load(sys.stdin)["lib_dir"])')
mkdir -p build bin
cat > build/ui_msvcrt.def <<'EOF'
LIBRARY msvcrt.dll
EXPORTS
fopen
fclose
fflush
fprintf
printf
fputs
fputc
fgets
fwrite
_snprintf
malloc
free
memset
memcpy
memcmp
strcmp
strcpy
strcspn
strlen
strncmp
strncpy
_wcsicmp
EOF
"$driver_zig" dlltool -m i386 -d build/ui_msvcrt.def -l build/ui_msvcrt.lib
"$driver_zig" cc -target x86-windows-gnu -std=c99 -Os -Wall -Wextra -Werror -fno-builtin -nostdlib \
 -isystem "$driver_zig_lib/libc/include/any-windows-any" \
 -Wl,-e,probe_entry@0 -Wl,--subsystem,console -o bin/readonly_ui.exe src/readonly_ui.c build/ui_msvcrt.lib \
 -lkernel32 -lpsapi -lgdi32 -luser32 -lshell32 -ladvapi32
python3 - <<'PY'
import hashlib,json,re,struct,subprocess
from pathlib import Path
p=Path('bin/readonly_ui.exe')
b=bytearray(p.read_bytes()); pe=struct.unpack_from('<I',b,0x3c)[0]; opt=pe+24
assert b[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',b,pe+4)[0]==0x14c
assert struct.unpack_from('<H',b,opt)[0]==0x10b
# Set our helper's PE minimum to XP. The vendor image is never patched.
struct.pack_into('<HH',b,opt+40,5,1);struct.pack_into('<HH',b,opt+48,5,1)
p.write_bytes(b)
info=subprocess.check_output(['objdump','-p',str(p)],text=True)
dlls=re.findall(r'DLL Name: (.+)',info)
allowed={'msvcrt.dll','kernel32.dll','psapi.dll','gdi32.dll','user32.dll','shell32.dll','advapi32.dll'}
assert {d.lower() for d in dlls}==allowed,dlls
for banned in ('api-ms-win','GetTickCount64','GetSystemTimePreciseAsFileTime','QueryFullProcessImageName','InitializeCriticalSectionEx',
               'ws2_32.dll','wsock32.dll','iphlpapi.dll','WriteProcessMemory','CreateRemoteThread','CreateProcess','ShellExecute','TerminateProcess'):
 assert banned.lower() not in info.lower(),banned
report={'format':'PE32 i386','minimum_os':[5,1],'minimum_subsystem':[5,1],
        'crt':'XP msvcrt.dll with custom entrypoint; no UCRT startup',
        'imports_dlls':dlls,'size':len(b),'sha256':hashlib.sha256(b).hexdigest(),
        'no_network_imports':True,'no_process_creation_or_remote_write_imports':True,
        'validation':'Static PE/import inspection. XP runtime validation reported separately.'}
Path('build/readonly_ui.pe-validation.json').write_text(json.dumps(report,indent=2)+'\n')
Path('build/readonly_ui.imports.txt').write_text(info)
print(json.dumps(report,indent=2))
PY
sha256sum src/readonly_ui.c bin/readonly_ui.exe > build/readonly_ui.sha256

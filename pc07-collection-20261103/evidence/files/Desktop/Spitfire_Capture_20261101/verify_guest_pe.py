#!/usr/bin/env python3
"""Set our helper's PE minimum to XP and fail on unexpected imported DLLs."""
import hashlib,json,re,struct,subprocess
from pathlib import Path
p=Path(__file__).with_name('guest_probe.exe')
b=bytearray(p.read_bytes()); pe=struct.unpack_from('<I',b,0x3c)[0];opt=pe+24
assert b[pe:pe+4]==b'PE\0\0'
assert struct.unpack_from('<H',b,pe+4)[0]==0x14c
assert struct.unpack_from('<H',b,opt)[0]==0x10b
# Zig/lld defaults to Vista6.0 even when every import is available on XP.
# This is our own newly built program; no vendor binary is patched.
struct.pack_into('<HH',b,opt+40,5,1)
struct.pack_into('<HH',b,opt+48,5,1)
p.write_bytes(b)
info=subprocess.check_output(['objdump','-p',str(p)],text=True)
dlls=re.findall(r'DLL Name: (.+)',info)
allowed={'msvcrt.dll','kernel32.dll','ws2_32.dll','iphlpapi.dll','psapi.dll','gdi32.dll','user32.dll','shell32.dll'}
assert {d.lower() for d in dlls}==allowed,dlls
for banned in ('api-ms-win','GetTickCount64','GetSystemTimePreciseAsFileTime','QueryFullProcessImageName','InitializeCriticalSectionEx'):
 assert banned.lower() not in info.lower(),banned
report={'format':'PE32 i386','minimum_os':[5,1],'minimum_subsystem':[5,1],
        'crt':'Windows XP msvcrt.dll; custom entrypoint, no UCRT startup',
        'imports_dlls':dlls,'size':len(b),'sha256':hashlib.sha256(b).hexdigest(),
        'validation':'Static PE/import inspection only; XP runtime must be tested separately'}
p.with_name('guest_probe.pe-validation.json').write_text(json.dumps(report,indent=2)+'\n')
p.with_name('guest_probe.imports.txt').write_text(info)
print(json.dumps(report,indent=2))

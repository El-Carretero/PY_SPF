#!/usr/bin/env python3
"""Set only our newly built PE minimum to XP; validate its passive API surface."""
import hashlib,json,re,struct,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent.parent
p=root/'bin/passive_capture.exe'
b=bytearray(p.read_bytes());pe=struct.unpack_from('<I',b,0x3c)[0];opt=pe+24
assert b[pe:pe+4]==b'PE\0\0'
assert struct.unpack_from('<H',b,pe+4)[0]==0x14c
assert struct.unpack_from('<H',b,opt)[0]==0x10b
assert struct.unpack_from('<H',b,opt+68)[0]==2, 'GUI subsystem required: no foreground-stealing console'
struct.pack_into('<HH',b,opt+40,5,1);struct.pack_into('<HH',b,opt+48,5,1)
p.write_bytes(b)
info=subprocess.check_output(['objdump','-p',str(p)],text=True)
dlls=re.findall(r'DLL Name: (.+)',info)
assert {d.lower() for d in dlls}=={'msvcrt.dll','kernel32.dll','shell32.dll','advapi32.dll'},dlls
for banned in ('api-ms-win','GetTickCount64','GetSystemTimePreciseAsFileTime','InitializeCriticalSectionEx','CreateProcess','StartService','CreateService','SetService','WSAStartup','sendto','send','socket','connect'):
 assert not re.search(r'\b'+re.escape(banned)+r'\b',info,re.I),banned
for banned in (b'pcap_sendpacket',b'pcap_inject',b'pcap_sendqueue'):
 assert banned not in b,banned
for required in (b'pcap_next_ex',b'pcap_setnonblock',b'pcap_setfilter',b'pcap_stats'):
 assert required in b,required
report={'format':'PE32 i386','minimum_os':[5,1],'minimum_subsystem':[5,1],'subsystem':'WINDOWS_GUI (2); no console window',
'crt':'Windows XP msvcrt.dll; custom entrypoint; no UCRT',
'imported_dlls':dlls,'transmission_imports':[],'pcap_injection_exports_resolved':False,
'size':len(b),'sha256':hashlib.sha256(b).hexdigest(),
'validation':'Static PE/import inspection only. XP runtime must be tested separately.'}
(root/'build/capture/pe-validation.json').write_text(json.dumps(report,indent=2)+'\n')
(root/'build/capture/imports.txt').write_text(info)
print(json.dumps(report,indent=2))

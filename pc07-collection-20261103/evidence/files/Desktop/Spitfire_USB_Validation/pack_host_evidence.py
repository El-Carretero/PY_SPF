"""Preserve raw p07 XP artifacts; no packet or screenshot transformations."""
import argparse,base64,hashlib,io,json,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('expanded');p.add_argument('output');a=p.parse_args()
r=Path(a.root);src=Path(a.expanded);out=Path(a.output)
extra=['isolation-before.json','ics-before.json','harness_server.py','controller.hta','bootstrap.hta','fixture-values-original.json','fixture-source.json','fixture-state.json','host-timeline.jsonl','udp-original.jsonl','console-cleanup.json','validation-cleanup.json','vmx-before-console.vmx','final-session-runtime-hashes.json','final-success-runtime-hashes.json','cleanup_console.ps1','pack_sessions.py','verify_cleanup.ps1','delivery.json']
manifest=[]
def add(t,f,name):
 data=f.read_bytes()
 manifest.append({'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
 info=tarfile.TarInfo(name);info.size=len(data);info.mtime=int(f.stat().st_mtime);info.mode=0o600
 t.addfile(info,io.BytesIO(data))
with tarfile.open(out,'w:xz',preset=6) as t:
 for f in sorted(src.iterdir()):
  if f.is_file():
   name='sessions/'+f.name.replace('--','/')
   add(t,f,name)
 for name in extra:
  f=r/name
  if f.is_file():
   add(t,f,'harness/'+name)
 for pattern in ('fixture-segment-*.json','fixture-state.before-resume-*.json','STOP.before-resume-*'):
  for f in sorted(r.glob(pattern)):
   if f.is_file():add(t,f,'harness/'+f.name)
 for f in sorted((r/'received').iterdir()):
  if f.is_file() and f.suffix.lower() in ('.json','.jsonl','.txt','.tsv','.log'):
   add(t,f,'harness/received/'+f.name)
 temp=r/'transfer-manifest.json';temp.write_text(json.dumps(manifest,indent=2),encoding='utf-8');t.add(temp,arcname='transfer-manifest.json')
data=out.read_bytes();b64=base64.b64encode(data).decode();Path(str(out)+'.b64').write_text('\n'.join(b64[i:i+1000] for i in range(0,len(b64),1000)),encoding='ascii');print(json.dumps({'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'base64_lines':(len(b64)+999)//1000,'files':len(manifest)}))

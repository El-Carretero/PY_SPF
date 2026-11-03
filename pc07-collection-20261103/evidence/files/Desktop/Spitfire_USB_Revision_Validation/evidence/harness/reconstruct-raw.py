from pathlib import Path
import hashlib,json,sys,tarfile,base64,shutil
r=Path(__file__).parent
src=r/sys.argv[1]
dst=r/'evidence'/'sessions'
sessions=set()
for f in src.iterdir():
 if not f.is_file():continue
 parts=f.name.split('--')
 if not parts[0].startswith('run-') or len(parts)<2:raise ValueError(f.name)
 sessions.add(parts[0]);p=dst.joinpath(*parts);p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=f.read_bytes():raise ValueError('different existing evidence '+str(p))
 shutil.copyfile(f,p)
for s in sessions:
 p=dst/s
 files=[{'path':str(f.relative_to(p)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(p.rglob('*')) if f.is_file() and f.name!='raw-transfer-manifest.json']
 (p/'raw-transfer-manifest.json').write_text(json.dumps(files,indent=2))
a=r/'raw-sessions.tar.xz'
with tarfile.open(a,'w:xz') as t:
 for s in sorted(sessions):t.add(dst/s,arcname='sessions/'+s)
(r/'raw-sessions.b64').write_text(base64.b64encode(a.read_bytes()).decode())
print(json.dumps({'sessions':sorted(sessions),'bytes':a.stat().st_size,'sha256':hashlib.sha256(a.read_bytes()).hexdigest()}))

from pathlib import Path
import tarfile,base64,hashlib,json,sys
r=Path(__file__).parent
prefix=sys.argv[1]+'--'+sys.argv[2]+'--'
session=sys.argv[3]
dst=r/'evidence'/'sessions'/session
dst.mkdir(parents=True,exist_ok=True)
for f in (r/'received').glob(prefix+'*'):
 p=dst.joinpath(*f.name[len(prefix):].split('--'))
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(f.read_bytes())
manifest={str(f.relative_to(dst)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(dst.rglob('*')) if f.is_file()}
(dst/'transfer-manifest.json').write_text(json.dumps(manifest,indent=2))
a=r/'compact.tar.xz'
with tarfile.open(a,'w:xz') as t:t.add(dst,arcname='sessions/'+session)
(r/'compact.b64').write_text(base64.b64encode(a.read_bytes()).decode())
print(json.dumps({'files':len(manifest),'bytes':a.stat().st_size,'sha256':hashlib.sha256(a.read_bytes()).hexdigest()}))

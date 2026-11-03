from pathlib import Path
import tarfile,hashlib,io,json,base64
r=Path(r'C:\Users\Fluke\Desktop\Spitfire_USB_Validation');src=r/'evidence-all';out=r/'all-raw-sessions.tar.xz';manifest=[]
with tarfile.open(out,'w:xz',preset=6) as t:
 for f in sorted(src.iterdir()):
  if not f.is_file():continue
  data=f.read_bytes();name='sessions/'+f.name.replace('--','/');entry={'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()};manifest.append(entry)
  info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600;t.addfile(info,io.BytesIO(data))
 data=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('raw-sessions-manifest.json');info.size=len(data);info.mode=0o600;t.addfile(info,io.BytesIO(data))
b=out.read_bytes();b64=base64.b64encode(b).decode();Path(str(out)+'.b64').write_text('\n'.join(b64[i:i+1000] for i in range(0,len(b64),1000)))
print(json.dumps({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'lines':(len(b64)+999)//1000,'files':len(manifest)}))

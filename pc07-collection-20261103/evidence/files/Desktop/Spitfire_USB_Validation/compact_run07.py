from pathlib import Path
import zipfile,base64,json,hashlib
r=Path(r"C:\Users\Fluke\Desktop\Spitfire_USB_Validation");prefix='051-compact07--compact--';files=sorted((r/'received').glob(prefix+'*'));assert (r/'received'/'051-compact07-complete.txt').is_file()
hashes=[]
for f in files:
 name=f.name.removeprefix(prefix)
 if name.startswith('runtime--'):
  n=name.removeprefix('runtime--');hashes.append({'file':n,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'source_guest_session':'run-2026-10-31-18-46-25-78376'})
assert len(hashes)==9
h=r/'final-success-runtime-hashes.json';h.write_text(json.dumps(hashes,indent=2),encoding='utf-8')
o=r/'run07-compact.zip'
with zipfile.ZipFile(o,'w',zipfile.ZIP_DEFLATED) as z:
 for f in files:z.write(f,f.name.removeprefix(prefix).replace('--','/'))
 z.write(h,'runtime-hashes.json')
b=base64.b64encode(o.read_bytes()).decode();(r/'run07-compact.b64').write_text('\n'.join(b[i:i+1000] for i in range(0,len(b),1000)))
print(json.dumps({'bytes':o.stat().st_size,'sha256':hashlib.sha256(o.read_bytes()).hexdigest(),'lines':(len(b)+999)//1000,'files':len(files),'runtime_hashes':hashes}))

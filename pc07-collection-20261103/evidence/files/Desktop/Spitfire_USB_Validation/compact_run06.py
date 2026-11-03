from pathlib import Path
import zipfile,base64,json,hashlib
r=Path(r"C:\Users\Fluke\Desktop\Spitfire_USB_Validation");o=r/'run06-compact.zip'
with zipfile.ZipFile(o,'w',zipfile.ZIP_DEFLATED) as z:
 for p in (r/'received').glob('045-final-failure-evidence--*'):
  if p.suffix!='.bmp':z.write(p,p.name.removeprefix('045-final-failure-evidence--').replace('--','/'))
 z.write(r/'final-session-runtime-hashes.json','runtime-hashes.json')
b=base64.b64encode(o.read_bytes()).decode();(r/'run06-compact.b64').write_text('\n'.join(b[i:i+1000] for i in range(0,len(b),1000)))
print(json.dumps({'bytes':o.stat().st_size,'sha256':hashlib.sha256(o.read_bytes()).hexdigest(),'lines':(len(b)+999)//1000}))

from pathlib import Path
import hashlib,json,zipfile
r=Path(__file__).resolve().parent
items=[]
errors=[]
for line in (r/'SHA256SUMS.txt').read_text(encoding='utf8').splitlines():
 h,name=line.split('  ',1);p=r/name
 if not p.is_file():errors.append({'path':name,'error':'missing'});continue
 actual=hashlib.sha256(p.read_bytes()).hexdigest()
 if actual!=h:errors.append({'path':name,'expected':h,'actual':actual})
 items.append((p,name))
if errors:print(json.dumps({'errors':errors},indent=2));raise SystemExit(1)
z=r/'Spitfire_Original_Capture_20261101.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED,9) as f:
 for p,name in items:f.write(p,name)
 f.write(r/'SHA256SUMS.txt','SHA256SUMS.txt')
print(json.dumps({'all_manifest_files_match':True,'files':len(items)+1,'zip_bytes':z.stat().st_size,'zip_sha256':hashlib.sha256(z.read_bytes()).hexdigest(),'path':str(z)},indent=2))

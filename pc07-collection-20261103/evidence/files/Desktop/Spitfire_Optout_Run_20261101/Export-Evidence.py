from pathlib import Path
import subprocess,sys,json,zipfile,hashlib,base64
r=Path(__file__).resolve().parent
parts=sorted(r.glob('original*.etl.pcapng'))
assert parts and (r/'capture-finish.json').exists()
combined=r/'original.pcapng'
combined.write_bytes(b''.join(p.read_bytes() for p in parts))
subprocess.run([sys.executable,str(r/'code'/'pcap_audit.py'),str(combined),str(r/'original.pcap'),'--provenance','original'],check=True)
subprocess.run([sys.executable,str(r/'code'/'analyze_run.py'),str(r)],check=True)
files=[]
for p in r.iterdir():
 if p.is_file() and (p.suffix in ('.json','.jsonl','.txt','.csv','.etl','.pcap','.pcapng') or p.name=='executed-code-before-retry.zip'):
  if p.name.startswith(('console','code.zip')) or p.name.endswith('.etl.pcapng'):continue
  files.append(p)
for folder in ('received','analysis','screenshots'):
 for p in (r/folder).rglob('*'):
  if p.is_file() and p.suffix not in ('.bmp','.exe'):files.append(p)
manifest=[{'path':p.relative_to(r).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
(r/'evidence-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
files.append(r/'evidence-manifest.json')
z=r/'original-evidence.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED,9) as archive:
 for p in files:archive.write(p,p.relative_to(r))
b=base64.b64encode(z.read_bytes()).decode('ascii')
(r/'original-evidence.zip.b64.txt').write_text('\n'.join(b[i:i+1000] for i in range(0,len(b),1000)),encoding='ascii')
print(json.dumps({'zip_bytes':z.stat().st_size,'zip_sha256':hashlib.sha256(z.read_bytes()).hexdigest(),'base64_lines':(len(b)+999)//1000,'files':len(files)},indent=2))

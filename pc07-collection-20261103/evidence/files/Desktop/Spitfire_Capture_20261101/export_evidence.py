import pathlib,zipfile,base64,json,hashlib
r=pathlib.Path(r'C:\Users\Fluke\Desktop\Spitfire_Capture_20261101')
names=['preflight1.etl','preflight2.etl','preflight.pcapng','preflight-segment2.pcapng','host-isolation.json','host-isolation-proof.txt','host-timeline.jsonl','fixture-source.json','fixture-values-original.json','udp-diagnostic.jsonl','capture-counters.txt','capture-stop.txt','capture-filter-cleanup.txt','vmx-observed.txt','bootstrap.hta','guest_probe.exe']
with zipfile.ZipFile(r/'evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n in names:
  p=r/n
  if p.exists():z.write(p,n)
 for p in (r/'received').iterdir():z.write(p,'received/'+p.name)
 for n in ['integrity.json','SIGNATURES-1.10.14.txt']:
  p=r/'official-downloads'/n
  if p.exists():z.write(p,'official-downloads/'+n)
raw=(r/'evidence.zip').read_bytes();b64=base64.b64encode(raw).decode()
(r/'evidence-transfer.b64').write_text('\n'.join(b64[i:i+1000] for i in range(0,len(b64),1000)))
print(json.dumps({'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'lines':(len(b64)+999)//1000}))

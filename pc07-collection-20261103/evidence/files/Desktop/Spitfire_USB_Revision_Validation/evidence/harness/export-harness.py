from pathlib import Path
import hashlib,json,tarfile,base64,shutil,sys
r=Path(__file__).parent
d=r/'evidence'/'harness';d.mkdir(parents=True,exist_ok=True)
root_names=['harness_server.py','reply-values-optout1.json','fixture-source.json','fixture-values-original.json','isolation-before.json','vmx-before-revision.vmx','prepare-revision.ps1','controller.hta','bootstrap.hta','Bootstrap-Console.ps1','Inspect-Revision.ps1','cleanup-revision.ps1','display_fixture.exe','guest-cleanup-verified.json','cleanup-final.json','fixture-state.json','server.stdout.txt','server.stderr.txt','fixture-ledger-audit.json']
root_names += [p.name for p in r.glob('fixture-segment-*.json')]
if '--final' in sys.argv:root_names += ['host-timeline.jsonl','udp-original.jsonl']
root_names += ['start-revision.vbs','stop-original.vbs','close-loggers.vbs','collect-compact.vbs','export_sessions.vbs','export-compact.py','reconstruct-raw.py','export-harness.py','audit-fixture.py']
root_names += ['verify-guest-cleanup.py','final-inventory.vbs','vmx-after-revision.vmx','network-final.json']
for n in root_names:
 p=r/n
 if p.is_file():shutil.copyfile(p,d/n)
for p in (r/'received').iterdir():
 if p.name.startswith(('rev001-','rev002-','rev013-','rev015-','rev016-','rev-final-')) or ('display-' in p.name and p.suffix in ('.json','.bin')) or p.name.endswith('--stop-original.txt'):
  shutil.copyfile(p,d/p.name)
for p in (r/'received').glob('rev003-original-identity--*'):
 if p.suffix.lower() in ('.exe','.uir'):
  (d/(p.name+'.sha256.json')).write_text(json.dumps({'file':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
m=[{'path':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(d.iterdir()) if p.is_file() and p.name!='transfer-manifest.json']
(d/'transfer-manifest.json').write_text(json.dumps(m,indent=2))
a=r/'harness.tar.xz'
with tarfile.open(a,'w:xz') as t:t.add(d,arcname='harness')
(r/'harness.b64').write_text(base64.b64encode(a.read_bytes()).decode())
print(json.dumps({'files':len(m),'bytes':a.stat().st_size,'sha256':hashlib.sha256(a.read_bytes()).hexdigest()}))

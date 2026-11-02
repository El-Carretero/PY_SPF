"""Check documentation references without importing the laser controller."""
from pathlib import Path
import hashlib,json,re,subprocess
from urllib.parse import unquote

root=Path(__file__).resolve().parents[3]
docs=root/'docs/spitfire_control_flow'
errors=[];checked=0;cache={};mermaids=0
required=['README.md','01_main_operation.md','02_signal_interlock.md','03_state_machine.md','04_communication_sequence.md','05_signal_reference.md','06_evidence_and_unknowns.md']
for name in required:
 if not (docs/name).is_file():errors.append('Missing '+name)
for f in sorted(docs.rglob('*.md')):
 t=f.read_text()
 if t.count('```')%2:errors.append(f'{f}: unmatched code fence')
 mermaids+=t.count('```mermaid')
 for m in re.finditer(r'https://github\.com/El-Carretero/PY_SPF/blob/([0-9a-f]{40})/([^\s)#>]+)',t):
  ref,tail=m.groups();parts=tail.split('#',1);path=unquote(parts[0]);key=(ref,path)
  if key not in cache:
   r=subprocess.run(['git','show',ref+':'+path],cwd=root,capture_output=True)
   cache[key]=r.stdout.decode('utf-8','replace').splitlines() if r.returncode==0 else None
  lines=cache[key];checked+=1
  if lines is None:errors.append(f'{f.name}: missing {ref}:{path}');continue
  anchor=re.match(r'#L(\d+)(?:-L(\d+))?',t[m.end():])
  if anchor:
   start=int(anchor[1]);end=int(anchor[2] or start)
   if not 1<=start<=end<=len(lines):errors.append(f'{f.name}: out-of-range {path} {start}-{end}/{len(lines)}')
 for dest in re.findall(r'\]\(([^)]+)\)',t):
  dest=dest.strip('<>')
  if dest.startswith(('http:','https:','#','mailto:')):continue
  if not (f.parent/unquote(dest.split('#')[0])).exists():errors.append(f'{f.name}: missing local link {dest}')
manifest=json.loads((docs/'evidence/source_manifest.json').read_text())
for x in manifest['files']:
 if hashlib.sha256((root/x['path']).read_bytes()).hexdigest()!=x['sha256']:errors.append('Runtime/source hash changed: '+x['path'])
result={'status':'PASS' if not errors else 'FAIL','immutable_links_checked':checked,'git_objects_checked':len(cache),
 'mermaid_blocks':mermaids,'runtime_source_hashes_unchanged':not any('hash changed' in e for e in errors),'errors':errors,
 'limit':'Reference presence and line bounds, not semantic proof or Mermaid rendering; rendering and independent technical review are separate.'}
(docs/'evidence/source_checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2));raise SystemExit(bool(errors))

from pathlib import Path
import subprocess,json,time,os,hashlib
b=Path(__file__).resolve().parents[2]
p=b/'output/Spitfire_Python_Control_1.3.1/Spitfire_Python_Control'
w=Path(__file__).parent
exe=p/'dist/SpitfirePythonControl.exe'
manifest={'self_test_protocol':1,'version':'1.3.1','file':exe.name,'sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
(exe.parent/'SpitfirePythonControl.validation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
results=[]
for mode in ('empower','external'):
 out=w/f'gui_exe_{mode}_131.json'
 start=time.monotonic()
 r=subprocess.run([str(exe),'--self-test-report',str(out),'--pump-mode',mode],cwd=p,capture_output=True,text=True,timeout=90,encoding='utf-8',errors='replace')
 result={'kind':'exe','mode':mode,'exe_sha256':manifest['sha256'],'exit_code':r.returncode,'elapsed_s':time.monotonic()-start,'stdout':r.stdout,'stderr':r.stderr,'report':json.loads(out.read_text(encoding='utf-8')) if out.exists() else None}
 results.append(result)
 print(json.dumps(result),flush=True)
(w/'gui_exe_runs_131.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if any(r['exit_code']!=0 or not r['report'] or r['report']['status']!='PASS' for r in results): raise SystemExit(1)

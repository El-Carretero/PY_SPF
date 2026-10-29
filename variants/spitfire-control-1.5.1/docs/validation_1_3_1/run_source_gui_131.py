from pathlib import Path
import subprocess,json,os,time
b=Path(__file__).resolve().parents[2]
p=b/'output/Spitfire_Python_Control_1.3.1/Spitfire_Python_Control'
w=Path(__file__).parent
python=r'C:\Users\physi\AppData\Local\Programs\Python\Python313\python.exe'
results=[]
for mode in ('empower','external'):
 out=w/f'gui_source_{mode}_131.json'
 start=time.monotonic()
 r=subprocess.run([python,'-X','utf8',str(p/'run_spitfire.py'),'--self-test-report',str(out),'--pump-mode',mode],cwd=p,capture_output=True,text=True,timeout=90,encoding='utf-8',errors='replace')
 result={'kind':'source','mode':mode,'exit_code':r.returncode,'elapsed_s':time.monotonic()-start,'stdout':r.stdout,'stderr':r.stderr,'report':json.loads(out.read_text(encoding='utf-8')) if out.exists() else None}
 results.append(result)
 print(json.dumps(result),flush=True)
(w/'gui_source_runs_131.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
if any(r['exit_code']!=0 or r['report']['status']!='PASS' for r in results): raise SystemExit(1)

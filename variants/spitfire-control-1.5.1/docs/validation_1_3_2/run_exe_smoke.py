from pathlib import Path
import subprocess,json,time
b=Path(__file__).resolve().parents[2];p=b/'output/Spitfire_Python_Control_1.3.2/Spitfire_Python_Control';w=Path(__file__).parent
exe=p/'dist/SpitfirePythonControl.exe';start=time.monotonic()
r=subprocess.run([str(exe),'--help'],cwd=p,capture_output=True,text=True,timeout=30)
result={'scope':'Frozen EXE entry-point import and argparse startup only; no live GUI/operation commands','exit_code':r.returncode,'elapsed_seconds':time.monotonic()-start,'stdout':r.stdout,'stderr':r.stderr}
(w/'exe_startup_smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
raise SystemExit(r.returncode)

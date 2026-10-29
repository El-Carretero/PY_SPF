import json,os,sys,tempfile,unittest
from pathlib import Path
work=Path(__file__).resolve().parent
project=work.parent.parent/'output/Spitfire_Python_Control_1.3.1/Spitfire_Python_Control'
os.chdir(project);sys.path.insert(0,str(project/'src'))
tmp=work/'test_temp_131';tmp.mkdir(exist_ok=True);os.environ['TEMP']=str(tmp);os.environ['TMP']=str(tmp);tempfile.tempdir=str(tmp)
from spitfire_control.validation_worker import install_offline_fence
install_offline_fence(loopback=True)
import tkinter as tk
init=tk.Tk.__init__
def hidden_init(self,*args,**kwargs):init(self,*args,**kwargs);self.attributes('-alpha',0.0)
tk.Tk.__init__=hidden_init
suite=unittest.defaultTestLoader.discover(str(project/'tests'))
with (work/'full_tests_131.txt').open('w',encoding='utf-8') as stream:
 result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),'skip_details':[(t.id(),r) for t,r in result.skipped],'failure_details':[(t.id(),s) for t,s in result.failures+result.errors],'offline_fence':True,'real_hardware_io':False}
(work/'full_tests_131.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)
raise SystemExit(0 if result.wasSuccessful() else 1)

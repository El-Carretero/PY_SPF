from pathlib import Path
import sys,os,json,unittest
b=Path(__file__).resolve().parents[2];p=b/'output/Spitfire_Python_Control_1.3.2/Spitfire_Python_Control';w=Path(__file__).parent
(w/'test_temp').mkdir(exist_ok=True);os.environ['TEMP']=os.environ['TMP']=str(w/'test_temp')
sys.path[:0]=[str(p/'src'),str(p/'tests')]
from spitfire_control.validation_worker import install_offline_fence
install_offline_fence(loopback=False)
import tkinter as tk
original_init=tk.Tk.__init__
def hidden_init(self,*a,**kw):
 original_init(self,*a,**kw);self.attributes('-alpha',0.0)
tk.Tk.__init__=hidden_init
names=['test_arm_reset_132','test_arm_toggle','test_audit_validation',
 'test_ui.GuiRegressionTests.test_cancelled_arm_cannot_be_shown_enabled',
 'test_ui.GuiRegressionTests.test_arm_is_a_toggle_button_and_updates_immediately',
 'test_ui.GuiRegressionTests.test_automatic_disarm_updates_button_and_unavailable_link_disables_it',
 'test_external_profile.ExternalControllerTests.test_fault_latch_reset_requires_a_recent_hv_off_readback',
 'test_external_profile.ExternalControllerTests.test_fault_latch_reset_rechecks_hv_off_before_transmission',
 'test_regressions.SchedulerRegressionTests.test_disarm_wins_between_dequeue_and_actual_send',
 'test_regressions.SchedulerRegressionTests.test_timeout_disarms_cancels_writes_and_marks_link_unknown',
 'test_regressions.SchedulerRegressionTests.test_stop_resets_both_arm_states_and_rejects_more_work']
suite=unittest.defaultTestLoader.loadTestsFromNames(names)
with (w/'targeted_tests_132.txt').open('w',encoding='utf-8') as out:
 result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
r={'version':'1.3.2','scope':'ARM/reset only','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'external_io':'blocked','failure_details':[(str(t),v) for t,v in result.failures+result.errors]}
(w/'targeted_tests_132.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(r,ensure_ascii=False),flush=True)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)

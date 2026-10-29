"""Actual Tk callbacks + asynchronous controller + independent UDP Verifier."""
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from test_verifier_140 import VirtualSpitfire, CapturedResetTwin, CaptureStore, VirtualDeviceServer
from spitfire_control.config import AppConfig
from spitfire_control.ui import SpitfireApp


class GuiVerifier140Tests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.root.withdraw()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(str(args))
    def build(self, mode='empower', model=None):
        self.capture=CaptureStore()
        self.model=model or VirtualSpitfire(isolated_clients=False)
        self.model._shared.values[1068]=1
        self.server=VirtualDeviceServer('127.0.0.1',0,self.model,self.capture)
        self.server.start()
        config=AppConfig(mode='udp',pump_mode=mode,remote_host='127.0.0.1',
                         remote_port=self.server.local_address[1],local_host='127.0.0.1',local_port=0,
                         auto_poll=False,timeout_seconds=.25,log_directory=self.temp.name)
        with patch.object(SpitfireApp,'connect'):
            self.app=SpitfireApp(self.root,config)
        self.app.connect()
        self.wait(lambda:self.app.controller.state.is_fresh(1041))
    def wait(self, predicate, timeout=4):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.root.update()
            if predicate():return
            time.sleep(.01)
        self.fail('GUI/Verifier condition timed out')
    def tearDown(self):
        if hasattr(self,'app'):
            with patch.object(AppConfig,'save'):self.app.close()
            self.server.stop()
            folder=os.environ.get('SPITFIRE_EVIDENCE_DIR')
            if folder:self.capture.snapshot().save_jsonl(Path(folder)/(self.id().split('.')[-1]+'.jsonl'))
            self.assertEqual(self.errors,[])
        elif hasattr(self,'root'):self.root.destroy()
    def test_empower_gui_current_A_and_raw_console_are_distinct(self):
        self.build()
        self.wait(lambda:self.app.drafts[1009].readback.get()=='18')
        self.model.profile.overrides[2003]=''
        self.app.drafts[1009].variable.set('17')
        with patch('spitfire_control.ui.messagebox.askyesno',return_value=True):
            self.app._issue_from_var(2003,self.app.drafts[1009].variable,'Current',numeric=True)
        self.wait(lambda:self.app.drafts[1009].readback.get()=='17')
        writes=[t for t in self.capture.snapshot().transactions if t.command_id==2003]
        self.assertEqual(writes[-1].argument,'170.00')
        self.app.console_command.set('2003 · EMP:DIODE:CURR');self.app.console_arg.set('160')
        with patch('spitfire_control.ui.messagebox.askyesno',return_value=True):self.app._console_send()
        self.wait(lambda:self.app.drafts[1009].readback.get()=='16')
        self.assertEqual([t.argument for t in self.capture.snapshot().transactions if t.command_id==2003],['170.00','160'])
    def test_external_gui_sources_apply_with_empty_receipts(self):
        self.build('external')
        self.model.profile.overrides.update({2030:'',2031:''})
        with patch('spitfire_control.ui.messagebox.askyesno',return_value=True):
            self.assertTrue(self.app._apply_external_sources())
        self.wait(lambda:sum(r.status=='confirmed' for r in self.app.controller.command_results)==2)
        self.assertEqual((self.app.controller.state.value(1050),self.app.controller.state.value(1051)),(1,1))
        self.assertEqual([t.command_id for t in self.capture.snapshot().transactions if t.command_id>=2000],[2030,2031])
    def test_gui_clear_faults_updates_main_without_clearing_key_or_emp(self):
        self.build('external',CapturedResetTwin())
        self.wait(lambda:self.app.controller.state.value(1089)==5)
        with patch('spitfire_control.ui.messagebox.askyesno',return_value=True):self.app._clear_faults()
        self.wait(lambda:any(r.command_id==2050 and r.status=='observed' for r in self.app.controller.command_results),9)
        self.wait(lambda:self.app.state.value(1089)==4)
        self.assertFalse(self.app.state.fault_state(10))
        self.assertTrue(self.app.state.fault_state(7))
        self.assertEqual(self.app.state.value(1089)&4,4)
        self.assertEqual([t.command_id for t in self.capture.snapshot().transactions if t.command_id>=2000],[2044,2049,2052,2050])


if __name__=='__main__':unittest.main()

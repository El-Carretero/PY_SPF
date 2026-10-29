"""Actual Tk controls + worker + loopback Verifier for the new output panel."""
from datetime import timedelta
from pathlib import Path
import os
import time
import unittest
from unittest.mock import patch
import test_gui_verifier_140 as gui_helpers
from test_release_150 import OutputTwin


class OutputGui150Tests(unittest.TestCase):
    setUp=gui_helpers.GuiVerifier140Tests.setUp
    build=gui_helpers.GuiVerifier140Tests.build
    wait=gui_helpers.GuiVerifier140Tests.wait
    tearDown=gui_helpers.GuiVerifier140Tests.tearDown
    def ready(self):
        self.build('external',OutputTwin())
        self.wait(lambda:not self.app.controller._pc_run_reason())
    def writes(self):return [(t.command_id,t.argument) for t in self.capture.snapshot().transactions if t.command_id>=2000]
    def run_button(self):
        self.root.deiconify();self.root.update()
        self.app.run_button.event_generate('<Motion>',warp=True,x=10,y=10);self.root.update()
        self.app.run_button.event_generate('<ButtonPress-1>',x=10,y=10)
        self.wait(lambda:self.app.controller.pc_output_status.action=='RUN',4.5)
        self.app.run_button.event_generate('<ButtonRelease-1>',x=10,y=10)
    def test_gui_run_then_stop_confirms_pair_without_hv_or_pump_write(self):
        self.ready();self.run_button()
        self.wait(lambda:self.app.controller.pc_output_status.status=='confirmed')
        self.wait(lambda:'PC1: ON' in self.app.output_readbacks.get())
        self.assertIn('PC2: ON',self.app.output_readbacks.get())
        self.app.stop_button.invoke()
        self.wait(lambda:self.app.controller.pc_output_status.action=='STOP' and self.app.controller.pc_output_status.status=='confirmed')
        self.wait(lambda:'PC1: OFF' in self.app.output_readbacks.get())
        self.assertEqual(self.writes(),[(2019,'2 ON'),(2019,'1 ON'),(2019,'1 OFF'),(2019,'2 OFF')])
        self.assertIn('Device HV: ON',self.app.output_readbacks.get())
    def test_live_overview_controls_keep_full_height_at_1024(self):
        self.ready();self.root.geometry('1024x768');self.root.deiconify();self.run_button()
        self.wait(lambda:'ON confirmed' in self.app.output_result.get());self.root.update()
        for widget in self.app._walk_widgets(self.app.overview):
            if widget.winfo_ismapped() and widget.winfo_class() in ('TButton','TEntry','TCombobox'):
                with self.subTest(widget=str(widget)):
                    self.assertGreaterEqual(widget.winfo_height(),widget.winfo_reqheight())
    def test_settings_navigation_never_sends_a_write(self):
        self.ready();self.app.timing_settings_button.invoke();self.root.update()
        self.assertEqual(self.app.notebook.select(),str(self.app.timing))
        self.assertEqual(self.writes(),[])
    def test_ordinary_click_does_not_start_run(self):
        self.ready();self.app.run_button.invoke()
        self.root.update();self.assertEqual(self.writes(),[])
    def test_reset_confirmation_explains_key_hv_transition(self):
        self.ready()
        with patch('spitfire_control.ui.messagebox.askyesno',return_value=False) as dialog:
            self.app._clear_faults()
        self.assertIn('Keyswitch',dialog.call_args.args[1]);self.assertIn('HV',dialog.call_args.args[1])
        self.assertEqual(self.writes(),[])
    def test_stale_voltage_key_and_channel_are_not_displayed_as_live(self):
        self.ready();self.app.state=self.app.controller.state
        for cid in (1042,1039,1045):self.app.state.updated_at[cid]-=timedelta(seconds=30)
        self.app._refresh_ui();text=self.app.output_readbacks.get()
        for expected in ('HV1: unknown/stale','Key interlock: unknown/stale','PC1: unknown/stale'):
            self.assertIn(expected,text)
    def test_passive_hv_change_with_autopoll_off_does_not_run(self):
        self.ready()
        with self.model._lock:self.model._shared.values[1021]=0
        self.wait(lambda:'Device HV: OFF' in self.app.output_readbacks.get())
        with self.model._lock:self.model._shared.values[1021]=1
        self.wait(lambda:'Device HV: ON' in self.app.output_readbacks.get())
        self.assertIn('PC1: OFF',self.app.output_readbacks.get());self.assertIn('PC2: OFF',self.app.output_readbacks.get())
        self.assertEqual(self.writes(),[])
    def test_failed_second_on_reports_cleanup_instead_of_run_success(self):
        self.ready();self.model.reject.add('1 ON');self.run_button()
        self.wait(lambda:self.app.controller.pc_output_status.status=='failed')
        self.wait(lambda:'failed · both PC OFF confirmed' in self.app.output_result.get())
        self.assertEqual([self.app.controller.state.pc_output(ch) for ch in (1,2)],['OFF','OFF'])

if __name__=='__main__':unittest.main()

"""UI regressions for refresh stability, preserved fault evidence and RUN hold."""
from datetime import timedelta
from types import SimpleNamespace
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from spitfire_control.hold_button import HoldToRunButton
from spitfire_control.config import AppConfig
from spitfire_control.controller import ControllerEvent
from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState
from spitfire_control.ui import SpitfireApp
from test_external_profile import healthy, apply
import test_gui_verifier_140 as gui_helpers
from test_release_150 import OutputTwin


class HoldWidget151Tests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.calls=[];self.progress=[];self.now=100.0
        self.button=HoldToRunButton(self.root,text='RUN',on_confirm=lambda:self.calls.append(self.now),on_progress=self.progress.append)
        self.button.pack();self.root.update();self.button._clock=lambda:self.now
    def tearDown(self):
        if hasattr(self,'root'):self.button.cancel();self.root.destroy()
    def advance(self,seconds):
        count=round(seconds/.05)
        for _ in range(count):
            self.now=round(self.now+.05,6)
            if self.button._hold_job is not None:
                self.button.after_cancel(self.button._hold_job)
                self.button._tick()
    def test_no_start_before_three_seconds_and_once_after_threshold(self):
        self.button._press();self.advance(2.95);self.assertEqual(self.calls,[])
        self.advance(.05);self.assertEqual(self.calls,[103.0])
        self.advance(2);self.button._press();self.assertEqual(len(self.calls),1)
    def test_short_release_does_not_accumulate_across_presses(self):
        self.button._press();self.advance(2);self.button._release()
        self.button._press();self.advance(2);self.assertEqual(self.calls,[])
    def test_leave_cancels_hold(self):
        self.button._press();self.advance(2.9);self.button.event_generate('<Leave>');self.advance(1)
        self.assertEqual(self.calls,[])
    def test_focus_loss_cancels_hold(self):
        self.button._press();self.advance(2.9);self.button.event_generate('<FocusOut>');self.advance(1)
        self.assertEqual(self.calls,[])
    def test_stalled_ui_cancels_instead_of_firing_on_resume(self):
        self.button._press();self.advance(2.8);self.now+=2;self.button.after_cancel(self.button._hold_job);self.button._tick()
        self.assertEqual(self.calls,[]);self.assertIsNone(self.button._hold_start)
    def test_invoke_and_keyboard_do_not_bypass_hold(self):
        self.button.invoke();self.button.event_generate('<KeyPress-Return>');self.button.event_generate('<KeyRelease-Return>')
        self.button.event_generate('<KeyPress-space>');self.button.event_generate('<KeyRelease-space>')
        self.root.update();self.assertEqual(self.calls,[])
    def test_disabled_during_hold_cancels(self):
        self.button._press();self.advance(2.9);self.button.state(['disabled']);self.advance(.1)
        self.assertEqual(self.calls,[])
    def test_label_stays_run_during_hold(self):
        self.button._press();self.advance(1);self.assertEqual(self.button.cget('text'),'RUN')


class Refresh151Tests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        with patch.object(SpitfireApp,'connect'):self.app=SpitfireApp(self.root,AppConfig(pump_mode='external'))
        # Cancel startup/periodic callbacks; these tests drive snapshots explicitly.
        for token in tuple(self.app._after_jobs):self.root.after_cancel(token)
        self.app._after_jobs.clear()
        self.root.geometry('1024x768');self.root.update()
        self.app.state=healthy(DeviceState(pump_mode='external'))
        self.app._refresh_ui();self.root.update()
    def tearDown(self):
        if hasattr(self,'app'):
            self.app.controller=None
            with patch.object(AppConfig,'save'):self.app.close()
    def test_fault_survives_timeout_as_last_stale_and_still_blocks_run(self):
        apply(self.app.state,1066,'0X4000');self.app._refresh_ui()
        self.app.state.connected=False;self.app._refresh_ui()
        self.assertIn('4000 [last/stale]',self.app.fault_health_raw_var.get())
        self.assertIn('Last reported FAULT',self.app.fault_summary.label.cget('text'))
        indicator=self.app.fault_indicators[7]
        self.assertTrue(indicator.label.cget('text').endswith('*'))
        self.assertEqual(indicator.canvas.itemcget(indicator.dot,'fill'),'#d64545')
        self.assertTrue(self.app.state.external_enable_reason())
    def test_invalid_fault_payload_does_not_replace_last_value_with_zero(self):
        apply(self.app.state,1066,'0X2000');self.app._refresh_ui()
        apply(self.app.state,1066,'ERROR');self.app._refresh_ui()
        self.assertIn('0X2000 [last/stale]',self.app.fault_health_raw_var.get())
        self.assertTrue(self.app.state.external_enable_reason())
    def test_fresh_clear_removes_old_fault(self):
        apply(self.app.state,1066,'0X4000');self.app._refresh_ui()
        apply(self.app.state,1066,'');self.app._refresh_ui()
        apply(self.app.state,1066,'0');self.app._refresh_ui()
        self.assertNotIn('last/stale',self.app.fault_health_raw_var.get())
        self.assertEqual(self.app.fault_indicators[7].canvas.itemcget(self.app.fault_indicators[7].dot,'fill'),'#2ea35f')
    def test_stale_clear_is_amber_not_fresh_green(self):
        self.app.state.updated_at[1066]-=timedelta(seconds=30);self.app._refresh_ui()
        indicator=self.app.fault_indicators[7]
        self.assertEqual(indicator.canvas.itemcget(indicator.dot,'fill'),'#e1a426')
    def test_never_received_fault_remains_unknown(self):
        self.app._fault_last.clear();self.app._fault_raw_last.clear()
        self.app.state=DeviceState(pump_mode='external');self.app._refresh_ui()
        indicator=self.app.fault_indicators[7]
        self.assertEqual(indicator.canvas.itemcget(indicator.dot,'fill'),'#aab3ba')
    def test_health_alias_retains_raw_fault_without_a_canonical_query(self):
        state=DeviceState(pump_mode='external',connected=True,transport_open=True)
        apply(state,1029,'20')
        self.assertTrue(state.is_fresh(1088))
        self.assertEqual(state.raw_values[1088],'20')
        self.app.state=state;self.app._refresh_ui()
        self.app.state.connected=False;self.app._refresh_ui()
        self.assertIn('TCU 20 [last/stale]',self.app.fault_health_raw_var.get())
        self.assertIn('Last reported FAULT',self.app.fault_summary.label.cget('text'))
    def test_older_ui_snapshot_cannot_erase_newer_remembered_fault(self):
        older=self.app.state.copy()
        apply(self.app.state,1066,'0X4000');self.app._refresh_ui()
        self.app._remember_fault_state(older)
        self.app.state.connected=False;self.app._refresh_ui()
        self.assertIn('4000 [last/stale]',self.app.fault_health_raw_var.get())
        self.assertTrue(self.app._fault_last[7])
    def test_unchanged_refresh_does_not_rewrite_value_variables(self):
        writes=[]
        self.app.value_vars[1021].trace_add('write',lambda *args:writes.append(1))
        for _ in range(10):self.app._refresh_ui()
        self.assertEqual(writes,[])
    def test_refresh_keeps_main_control_geometry_fixed(self):
        def geometry():
            self.root.update_idletasks()
            return [(w.winfo_rootx(),w.winfo_rooty(),w.winfo_width(),w.winfo_height()) for w in
                    (self.app.notebook,self.app.run_button,self.app.stop_button,self.app.timing_settings_button)]
        baseline=geometry()
        for connected,number in ((False,0),(True,123456.789),(False,0),(True,80)):
            self.app.state.connected=connected
            if connected:apply(self.app.state,1065,number)
            self.app._refresh_ui();self.assertEqual(geometry(),baseline)
    def test_event_burst_renders_once_and_batches_log_insertion(self):
        import queue
        events=queue.Queue()
        for _ in range(200):
            events.put(ControllerEvent('state',state=self.app.state.copy()))
            events.put(ControllerEvent('log','RX test'))
        self.app.controller=SimpleNamespace(events=events,running=True)
        with patch.object(self.app,'_refresh_ui',wraps=self.app._refresh_ui) as render,patch.object(self.app,'_insert_log',wraps=self.app._insert_log) as log:
            self.app._drain_events()
        self.assertEqual(render.call_count,1);self.assertEqual(log.call_count,1)
        self.assertGreater(events.qsize(),0) # bounded work lets input events run
    def test_stop_press_cancels_hold_and_does_not_wait_for_release(self):
        self.app.controller=Mock(running=True)
        self.app.run_button._press()
        self.app.stop_button.event_generate('<ButtonPress-1>',x=10,y=10)
        self.app.controller.stop_pc_outputs.assert_called_once_with()
        self.assertIsNone(self.app.run_button._hold_start)
        self.app.stop_button.event_generate('<ButtonRelease-1>',x=10,y=10)
        self.app.controller.stop_pc_outputs.assert_called_once_with()
    def test_button_labels_are_exact(self):
        self.assertEqual(self.app.run_button.cget('text'),'RUN');self.assertEqual(self.app.stop_button.cget('text'),'STOP')
    def test_unmap_and_profile_change_cancel_hold(self):
        self.app.run_button._press();self.app._apply_pump_profile()
        self.assertIsNone(self.app.run_button._hold_start)
        self.app.run_button._press();self.app.run_button.event_generate('<Unmap>')
        self.assertIsNone(self.app.run_button._hold_start)


class TecGui151Tests(unittest.TestCase):
    setUp=gui_helpers.GuiVerifier140Tests.setUp
    build=gui_helpers.GuiVerifier140Tests.build
    wait=gui_helpers.GuiVerifier140Tests.wait
    tearDown=gui_helpers.GuiVerifier140Tests.tearDown
    def test_tec_buttons_send_correct_commands_and_confirm_readback(self):
        self.build('external',OutputTwin())
        self.wait(lambda:self.app.controller.state.is_fresh(1028))
        with patch('spitfire_control.ui.messagebox.askyesno',return_value=True):self.app.tec_on_button.invoke()
        self.wait(lambda:'ON: 설정 조회 일치' in self.app.tec_result.get())
        self.assertEqual(self.app.tec_indicator.label.cget('text'),'TEC reported ON')
        self.app.tec_off_button.invoke()
        self.wait(lambda:'OFF: 설정 조회 일치' in self.app.tec_result.get())
        self.assertEqual(self.app.tec_indicator.label.cget('text'),'TEC reported OFF')
        writes=[t for t in self.capture.snapshot().transactions if t.command_id>=2000]
        self.assertEqual([t.command_id for t in writes],[2022,2023])
    def test_tec_ack_without_state_change_is_mismatch(self):
        self.build('external',OutputTwin());self.wait(lambda:self.app.controller.state.is_fresh(1028))
        self.model.profile.overrides[1028]='0'
        with patch('spitfire_control.ui.messagebox.askyesno',return_value=True):self.app.tec_on_button.invoke()
        self.wait(lambda:'설정 불일치' in self.app.tec_result.get())
        self.assertEqual(self.app.tec_indicator.label.cget('text'),'TEC reported OFF')

if __name__=='__main__':unittest.main()

"""Tk regression tests; skipped only when an X/Windows display is unavailable."""
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from spitfire_control.ui import SpitfireApp
from spitfire_control.config import AppConfig
from spitfire_control.protocol import Reply
from spitfire_control.controller import ControllerEvent
from spitfire_control.controller import LaserController
from spitfire_control.transport import SimulatorTransport
from spitfire_control.state import DeviceState

class GuiRegressionTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.connect_patch = patch.object(SpitfireApp, 'connect')
        self.connect_patch.start()
        self.app = SpitfireApp(self.root, AppConfig(auto_poll=False))
        self.root.geometry('1024x768')
        self.root.update()
        self.app.state = DeviceState(connected=True, transport_open=True)
        self.receive(1000, 'test controller')
    def tearDown(self):
        if not hasattr(self, 'app'): return
        if self.app.raw_serial_dialog:
            self.app.raw_serial_dialog.close()
        for job in self.root.tk.call('after', 'info'):
            self.root.after_cancel(job)
        self.root.destroy()
        self.connect_patch.stop()
        self.assertEqual(self.errors, [])
    def receive(self, cid, value):
        r = Reply(cid, str(value), f'<{cid}>{value}')
        self.app.state.apply(r)
        self.app._handle_event(ControllerEvent('state', state=self.app.state.copy(), reply=r))
    def test_edit_survives_unrelated_and_changed_readback(self):
        self.receive(1009, 180)
        draft = self.app.drafts[1009]
        draft.variable.set('20')
        self.receive(1030, 25)
        self.assertEqual(draft.variable.get(), '20')
        self.assertEqual(draft.readback.get(), '18')
        self.receive(1009, 220)
        self.assertEqual(draft.variable.get(), '20')
        self.assertEqual(draft.readback.get(), '22')
        draft.reset()
        self.assertEqual(draft.variable.get(), '22')
    def test_matching_readback_clears_edit(self):
        self.receive(1009, 180)
        draft = self.app.drafts[1009]; draft.variable.set('20.0')
        self.receive(1009, 200)
        self.assertFalse(draft.dirty)
        self.assertEqual(draft.variable.get(), '20')
    def test_qsw_hz_display_and_wire_conversion(self):
        self.receive(1010, '100.00')
        self.assertEqual(self.app.drafts[1010].variable.get(), '1000')
        self.app.controller = Mock(running=True)
        self.app._issue_from_var(2004, self.app.drafts[1010].variable, 'Q-switch frequency', numeric=True)
        self.app.controller.submit.assert_called_once_with(2004, '100.00')
    def test_programmer_console_preserves_raw_wire_units(self):
        self.app.controller = Mock(running=True)
        self.app.console_command.set('2004 · EMP:QSW:PRF')
        self.app.console_arg.set('100')
        self.app._console_send()
        self.app.controller.submit.assert_called_once_with(2004, '100')
    def test_delay_number_and_modes_are_synchronized(self):
        self.receive(1045, 'ON NBWD NENA DELAY VALUE = 12.50')
        self.assertEqual(self.app.drafts[1045].variable.get(), '12.5')
        for field, expected in [('switch', 'on'), ('bwd', 'NBWD'), ('enable', 'NENA')]:
            self.assertEqual(self.app.delay_drafts[(1, field)].variable.get(), expected)
        self.app.drafts[1045].variable.set('15')
        self.receive(1030, 25)
        self.assertEqual(self.app.drafts[1045].variable.get(), '15')
    def test_arm_control_and_api_are_absent(self):
        self.assertFalse(hasattr(self.app, 'arm_button'))
        self.assertFalse(hasattr(self.app, '_toggle_arm'))
        self.assertFalse(hasattr(LaserController, 'arm'))
        self.assertNotIn('armed', DeviceState.__dataclass_fields__)
        labels = [str(w.cget('text')) for w in self.app._walk_widgets(self.root)
                  if w.winfo_class() in ('TButton', 'TCheckbutton')]
        self.assertNotIn('ARM', labels)
        self.assertNotIn('DISARM', labels)
    def test_raw_service_window_does_not_open_serial_port(self):
        self.app.rs232_warning_acknowledged = True
        self.app._raw_serial_shortcut()
        self.assertIsNotNone(self.app.raw_serial_dialog)
        self.assertFalse(self.app.raw_serial_dialog.session.connected)
    def test_all_tabs_fit_operator_controls_at_1024(self):
        self.app._build_service_controls()
        def walk(w):
            for child in w.winfo_children():
                yield child
                yield from walk(child)
        for tab in self.app.notebook.tabs():
            self.app.notebook.select(tab); self.root.update()
            for w in walk(self.root.nametowidget(tab)):
                if w.winfo_ismapped() and w.winfo_class() in ('TButton', 'TEntry', 'TCombobox', 'TCheckbutton'):
                    x = w.winfo_rootx() - self.root.winfo_rootx()
                    y = w.winfo_rooty() - self.root.winfo_rooty()
                    with self.subTest(tab=self.app.notebook.tab(tab, 'text'), widget=str(w)):
                        self.assertGreaterEqual(x, 0)
                        self.assertLessEqual(x + w.winfo_width(), self.root.winfo_width())
                        self.assertLessEqual(y + w.winfo_height(), self.root.winfo_height())
    def test_cancelled_override_restores_confirmed_value(self):
        self.receive(1033, 0)
        self.app.ecu_opt_var.set(True)
        with patch.object(self.app, 'issue', return_value=False):
            self.app._toggle_option(2024, 1033, self.app.ecu_opt_var, 'TCU opt-out')
        self.assertFalse(self.app.ecu_opt_var.get())
    def test_cancelled_delay_mode_restores_confirmed_mode(self):
        self.receive(1045, 'ON NBWD NENA DELAY VALUE = 12.50')
        var = self.app.delay_drafts[(1, 'switch')].variable
        var.set('off')
        with patch.object(self.app, 'issue', return_value=False):
            self.app._apply_channel_mode(1, 'off')
        self.assertEqual(var.get(), 'on')

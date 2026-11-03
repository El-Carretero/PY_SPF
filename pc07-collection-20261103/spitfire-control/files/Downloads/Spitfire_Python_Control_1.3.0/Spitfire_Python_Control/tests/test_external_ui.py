"""External pump GUI checks; no device access or visible windows."""
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone

from spitfire_control.app import build_parser
from spitfire_control.config import AppConfig
from spitfire_control.controller import ControllerEvent
from spitfire_control.protocol import Reply
from spitfire_control.profiles import EXTERNAL_REQUIRED_READS
from spitfire_control.state import DeviceState
from spitfire_control.ui import SpitfireApp


class ExternalConfigurationTests(unittest.TestCase):
    def test_old_config_keeps_empower_default(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps({"mode": "simulator", "remote_port": 1234}))
            config = AppConfig.load(path)
            self.assertEqual(config.pump_mode, "empower")
            self.assertEqual(config.remote_port, 1234)

    def test_external_config_round_trip_is_independent_of_transport(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            AppConfig(mode="simulator", pump_mode="external").save(path)
            config = AppConfig.load(path)
            self.assertEqual((config.mode, config.pump_mode), ("simulator", "external"))

    def test_invalid_profile_falls_back_to_simulator(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps({"mode": "udp", "pump_mode": "broken"}))
            self.assertEqual(AppConfig.load(path).mode, "simulator")

    def test_cli_external_can_use_simulator(self):
        args = build_parser().parse_args(["--simulator", "--pump-mode", "external"])
        self.assertTrue(args.simulator)
        self.assertFalse(args.udp)
        self.assertEqual(args.pump_mode, "external")


class ExternalUiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.connect_patch = patch.object(SpitfireApp, "connect")
        self.connect_patch.start()
        self.app = SpitfireApp(self.root, AppConfig(pump_mode="external", auto_poll=False))
        self.app._apply_pump_profile()
        self.app.state = DeviceState(pump_mode="external", connected=True, transport_open=True)
        self.receive(1000, "synthetic TDG")
        self.root.update_idletasks()

    def tearDown(self):
        if not hasattr(self, "app"):
            return
        for job in self.root.tk.call("after", "info"):
            self.root.after_cancel(job)
        self.root.destroy()
        self.connect_patch.stop()
        self.assertEqual(self.errors, [])

    def receive(self, cid, value):
        self.app.state.apply(Reply(cid, str(value), f"<{cid}>{value}"))
        self.app._refresh_ui()

    def test_empower_controls_disabled_and_readings_not_simulated(self):
        self.assertEqual(str(self.app.notebook.tab(self.app.empower, "state")), "disabled")
        self.assertEqual(str(self.app.notebook.tab(self.app.service, "state")), "disabled")
        self.assertEqual(self.app.value_vars[1013].get(), "N/A")
        self.assertEqual(self.app.metric_cards[1008][0].value.cget("text"), "N/A")
        self.assertTrue(all(widget.instate(["disabled"]) for widget in self.app.override_widgets.values()))

    def test_optout_banner_reports_readback_without_claiming_pump_readiness(self):
        self.assertIn("unavailable", self.app.external_status_text.get())
        self.receive(1068, 0)
        self.assertIn("is OFF", self.app.external_status_text.get())
        self.receive(1068, 1)
        self.assertIn("Opt-out confirmed", self.app.external_status_text.get())
        self.assertNotIn("pump ready", self.app.external_status_text.get().lower())

    def test_run_opens_timing_without_transmitting(self):
        with patch.object(self.app, "issue") as issue:
            self.app._run_laser()
        issue.assert_not_called()
        self.assertEqual(self.app.notebook.select(), str(self.app.timing))

    def test_stop_only_sends_hv_off(self):
        self.app.controller = Mock(running=True)
        with patch.object(self.app, "issue") as issue:
            self.app.software_standby()
        issue.assert_called_once_with(2016)
        self.app.controller.arm.assert_called_once_with(False)
        self.assertIn("not stopped", self.app.connection_text.get())

    def test_fault_reset_does_not_reset_empower_or_global_state(self):
        with patch.object(self.app, "issue") as issue, patch.object(self.app, "_query"):
            self.app._clear_faults()
        self.assertEqual([c.args[0] for c in issue.call_args_list], [2049, 2052])

    def test_optout_requires_fresh_hv_off(self):
        self.app.controller = Mock(running=True, state=self.app.state)
        with patch.object(self.app, "issue") as issue, patch.object(self.app, "_query") as query, patch("spitfire_control.ui.messagebox.showwarning"):
            self.app._apply_external_opt_out()
            issue.assert_not_called()
            query.assert_called_once_with((1021, 1068))
        self.receive(1021, 0)
        self.app.controller.state = self.app.state
        with patch.object(self.app, "issue") as issue:
            self.app._apply_external_opt_out()
        self.assertEqual(issue.call_args.args, (2036, 1))
        self.assertFalse(self.app.state.external_opt_out_confirmed)

    def test_raw_serial_cannot_be_opened(self):
        with patch("spitfire_control.ui.messagebox.showinfo"), patch("spitfire_control.ui.RawSerialDialog") as dialog:
            self.app.open_raw_serial_service()
        dialog.assert_not_called()
        self.assertIsNone(self.app.raw_serial_dialog)

    def test_configuration_change_requires_disarm_and_known_hv_off(self):
        self.app.controller = Mock(running=True, state=self.app.state)
        self.app.state.armed = True
        self.assertIn("DISARM", self.app._configuration_change_reason())
        self.app.state.armed = False
        self.assertIn("HV OFF", self.app._configuration_change_reason())
        self.receive(1021, 0)
        self.assertEqual(self.app._configuration_change_reason(), "")
        self.app.state.updated_at[1021] = datetime.now(timezone.utc) - timedelta(seconds=100)
        self.assertIn("HV OFF", self.app._configuration_change_reason())
        self.app.controller.running = False
        self.assertEqual(self.app._configuration_change_reason(), "")

    def test_failed_settings_save_preserves_controller_and_profile(self):
        self.app.config.pump_mode = "empower"
        self.app._apply_pump_profile()
        previous_config = self.app.config
        state = DeviceState(pump_mode="empower", connected=True, transport_open=True)
        state.apply(Reply(1000, "synthetic TDG", "<1000>synthetic TDG"))
        state.apply(Reply(1021, "0", "<1021>0"))
        previous_controller = Mock(running=True, state=state, pump_mode="empower")
        self.app.controller = previous_controller
        original_toplevel = tk.Toplevel
        def hidden_toplevel(*args, **kwargs):
            window = original_toplevel(*args, **kwargs)
            window.withdraw()
            return window
        with patch("spitfire_control.ui.tk.Toplevel", side_effect=hidden_toplevel):
            self.app.show_connection_settings()
        window = next(w for w in self.root.winfo_children() if w.winfo_class() == "Toplevel")
        widgets = list(self.app._walk_widgets(window))
        profile = next(w for w in widgets if w.winfo_class() == "TCombobox" and tuple(w.cget("values")) == ("empower", "external"))
        profile.set("external")
        save = next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "SAVE & CONNECT")
        self.app.connect.reset_mock()
        with patch.object(AppConfig, "save", side_effect=PermissionError("read only")), patch("spitfire_control.ui.messagebox.showerror") as error:
            save.invoke()
        error.assert_called_once()
        self.assertIs(self.app.config, previous_config)
        self.assertEqual(self.app.config.pump_mode, "empower")
        self.assertIs(self.app.controller, previous_controller)
        self.assertEqual(self.app.controller.pump_mode, "empower")
        self.app.connect.assert_not_called()
        self.assertTrue(window.winfo_exists())
        window.destroy()

    def test_external_refresh_requests_all_enable_readbacks(self):
        refresh = next(w for w in self.app._walk_widgets(self.app.external_banner)
                       if w.winfo_class() == "TButton" and w.cget("text") == "REFRESH")
        self.app.controller = Mock(running=True)
        refresh.invoke()
        self.app.controller.query_now.assert_called_once_with(EXTERNAL_REQUIRED_READS)

    def test_manual_refresh_excludes_empower_fault_query(self):
        self.app.controller = Mock(running=True)
        self.app._query((1007, 1013, 1014, 1019, 1068))
        self.app.controller.query_now.assert_called_once_with((1019, 1068))

    def test_external_empower_fault_data_is_na_but_raw_snapshot_survives(self):
        self.receive(1068, 1)
        self.receive(1014, "64 0 0 0")
        self.assertEqual(self.app.state.raw_values[1014], "64 0 0 0")
        self.assertEqual(self.app.fault_raw_var.get(), "Empower N/A")
        self.assertIn("N/A", self.app.fault_indicators[0].label.cget("text"))
        self.assertNotEqual(self.app.fault_summary.label.cget("text"), "REPORTED SYSTEM FAULT")

    def test_internal_timing_readbacks_do_not_change_external_fault_display(self):
        self.receive(1068, 1)
        self.receive(1050, "INT")
        self.receive(1051, "INT")
        self.receive(1014, "8 0 0 0")
        for cid in (1066, 1088, 1089, 1039):
            self.receive(cid, "0")
        self.assertEqual(self.app.fault_raw_var.get(), "Empower N/A")
        self.assertIn("N/A", self.app.fault_indicators[0].label.cget("text"))
        self.assertEqual(self.app.fault_summary.label.cget("text"), "No reported faults; external pump unmonitored")
        self.assertEqual(self.app.subsystem_indicators["EMPOWER"].label.cget("text"), "N/A")

    def test_external_tdg_fault_is_not_hidden_by_empower_optout(self):
        self.receive(1068, 1)
        for cid in (1088, 1089, 1039):
            self.receive(cid, "0")
        self.receive(1066, "2000")
        self.assertEqual(self.app.fault_summary.label.cget("text"), "REPORTED SYSTEM FAULT")
        self.assertIn("TDG 2000", self.app.fault_health_raw_var.get())
        self.assertEqual(self.app.fault_raw_var.get(), "Empower N/A")

    def test_external_tabs_fit_at_1024_by_768(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("1024x768")
        self.root.deiconify()
        self.root.update()
        for tab in self.app.notebook.tabs():
            if str(self.app.notebook.tab(tab, "state")) == "disabled":
                continue
            self.app.notebook.select(tab)
            self.root.update()
            for widget in self.app._walk_widgets(self.root.nametowidget(tab)):
                if widget.winfo_ismapped() and widget.winfo_class() in (
                    "TButton", "TEntry", "TCombobox", "TCheckbutton"
                ):
                    x = widget.winfo_rootx() - self.root.winfo_rootx()
                    y = widget.winfo_rooty() - self.root.winfo_rooty()
                    with self.subTest(tab=self.app.notebook.tab(tab, "text"), widget=str(widget)):
                        self.assertGreaterEqual(x, 0)
                        self.assertGreaterEqual(y, 0)
                        self.assertLessEqual(x + widget.winfo_width(), self.root.winfo_width())
                        self.assertLessEqual(y + widget.winfo_height(), self.root.winfo_height())

    def test_profile_switch_restores_legacy_controls(self):
        self.app.config.pump_mode = "empower"
        self.app._apply_pump_profile()
        self.assertEqual(str(self.app.notebook.tab(self.app.empower, "state")), "normal")
        self.assertEqual(str(self.app.notebook.tab(self.app.service, "state")), "normal")
        self.assertIn("RUN", self.app.run_button.cget("text"))
        self.assertFalse(self.app.override_widgets[2036].instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()

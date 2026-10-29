"""UI transaction and lifecycle regressions; no devices or visible windows."""
from datetime import datetime, timedelta, timezone
import queue
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from spitfire_control.config import AppConfig
from spitfire_control.protocol import Reply
from spitfire_control.state import DeviceState
from spitfire_control.ui import SpitfireApp


class TimingUiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.attributes("-alpha", 0.0)
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.connect_patch = patch.object(SpitfireApp, "connect")
        self.connect_patch.start()
        self.app = SpitfireApp(self.root, AppConfig(pump_mode="external", auto_poll=False))
        self.app.state = DeviceState(pump_mode="external", connected=True, transport_open=True)
        self.app.state.apply(Reply(1000, "offline fixture", "<1000>offline fixture"))
        self.app.state.apply(Reply(1021, "0", "<1021>0"))
        # The UI timer drains a real queue. An unconfigured Mock.get_nowait()
        # fabricates events and can replace the real DeviceState with a Mock.
        self.app.controller = Mock(running=True, state=self.app.state, events=queue.Queue())
        self.values = {"external_seed_mhz": "80", "external_seed_tolerance_mhz": "0.5", "external_pump_hz": "10"}

    def tearDown(self):
        if not hasattr(self, "app"):
            return
        for token in self.root.tk.call("after", "info"):
            self.root.after_cancel(token)
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.connect_patch.stop()
        self.assertEqual(self.errors, [])

    def test_profile_save_failure_keeps_live_configuration(self):
        previous = self.app.config
        previous_controller = self.app.controller
        with patch.object(AppConfig, "save", side_effect=PermissionError("read-only")), patch("spitfire_control.ui.messagebox.showerror") as error:
            self.assertFalse(self.app._save_external_timing(self.values))
        error.assert_called_once()
        self.assertIs(self.app.config, previous)
        self.assertIs(self.app.controller, previous_controller)
        self.app.connect.assert_not_called()

    def test_profile_save_commits_only_after_success(self):
        previous = self.app.config
        observations = []
        def save(candidate):
            observations.append((self.app.config is previous, candidate.external_pump_hz))
        with patch.object(AppConfig, "save", autospec=True, side_effect=save):
            self.assertTrue(self.app._save_external_timing(self.values))
        self.assertEqual(observations, [(True, 10.0)])
        self.assertEqual(self.app.config.external_seed_mhz, 80.0)
        self.assertEqual(self.app.config.external_seed_tolerance_mhz, 0.5)
        self.app.connect.assert_called_once_with()
        self.app.controller.submit.assert_not_called()

    def test_profile_change_requires_fresh_hv_off(self):
        for hv in ("1", ""):
            with self.subTest(hv=hv):
                self.app.state.apply(Reply(1021, hv, "<1021>" + hv))
                with patch.object(AppConfig, "save") as save, patch("spitfire_control.ui.messagebox.showwarning"):
                    self.assertFalse(self.app._save_external_timing(self.values))
                save.assert_not_called()
        self.app.state.apply(Reply(1021, "0", "<1021>0"))
        self.app.state.updated_at[1021] = datetime.now(timezone.utc) - timedelta(seconds=10)
        with patch.object(AppConfig, "save") as save, patch("spitfire_control.ui.messagebox.showwarning"):
            self.assertFalse(self.app._save_external_timing(self.values))
        save.assert_not_called()

    def test_invalid_profile_input_cannot_change_runtime(self):
        previous = self.app.config
        for value in ("bad", "nan", "0", "-5"):
            values = dict(self.values, external_seed_mhz=value)
            with self.subTest(value=value), patch.object(AppConfig, "save") as save, patch("spitfire_control.ui.messagebox.showerror"):
                self.assertFalse(self.app._save_external_timing(values))
                save.assert_not_called()
                self.assertIs(self.app.config, previous)
        self.app.connect.assert_not_called()

    def test_external_profile_dialog_is_unavailable_for_empower(self):
        self.app.config.pump_mode = "empower"
        self.app._apply_pump_profile()
        self.assertEqual(self.app.file_menu.entrycget(2, "state"), "disabled")
        with patch("spitfire_control.ui.tk.Toplevel") as top:
            self.app.show_external_timing()
        top.assert_not_called()

    def test_explicit_source_setup_sends_only_the_two_mode_commands(self):
        self.assertTrue(self.app._apply_external_sources())
        self.app.controller.submit_batch.assert_called_once_with(((2030,"EXT"),(2031,"EXT")), origin="Apply EXT sources")
        self.assertIn("pending", self.app.connection_text.get())

    def test_source_setup_blocks_unknown_or_on_hv_and_stops_after_failure(self):
        self.app.state.apply(Reply(1021, "1", "<1021>1"))
        with patch.object(self.app, "_query"), patch("spitfire_control.ui.messagebox.showwarning"):
            self.assertFalse(self.app._apply_external_sources())
        self.app.controller.submit_batch.assert_not_called()
        self.app.state.apply(Reply(1021, "0", "<1021>0"))
        self.app.controller.submit_batch.side_effect = PermissionError("preflight failed")
        with patch("spitfire_control.ui.messagebox.showwarning"):
            self.assertFalse(self.app._apply_external_sources())
        self.app.controller.submit_batch.assert_called_once()

    def test_timing_readouts_do_not_present_expected_pump_as_measured(self):
        self.app.state.apply(Reply(1065, "80", "<1065>80"))
        self.app._refresh_ui()
        text = self.app.external_timing_text.get()
        self.assertIn("seed 80 MHz", text)
        self.assertIn("expected pump 10 Hz (unmeasured)", text)
        self.app.state.updated_at[1065] = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.app._refresh_ui()
        self.assertNotIn("seed 80 MHz", self.app.external_timing_text.get())

    def test_controller_receives_timing_expectations(self):
        self.app.config.external_seed_mhz = 79.5
        self.app.config.external_seed_tolerance_mhz = 0.25
        self.app.config.external_pump_hz = 10.0
        with patch("spitfire_control.ui.LaserController") as controller:
            self.app._make_controller()
        self.assertEqual(controller.call_args.kwargs["external_seed_mhz"], 79.5)
        self.assertEqual(controller.call_args.kwargs["external_seed_tolerance_mhz"], 0.25)
        self.assertEqual(controller.call_args.kwargs["external_pump_hz"], 10.0)

    def test_profile_dialog_controls_fit_without_exposing_a_window(self):
        original_top = tk.Toplevel
        def hidden(*args, **kwargs):
            window = original_top(*args, **kwargs)
            window.attributes("-alpha", 0.0)
            window.withdraw()
            return window
        with patch("spitfire_control.ui.tk.Toplevel", side_effect=hidden):
            self.app.show_external_timing()
        window = next(w for w in self.root.winfo_children() if w.winfo_class() == "Toplevel")
        window.deiconify()
        # Exercise the queue callback deterministically, including on a fast
        # machine where the regular 80 ms callback would not yet be due.
        self.root.after(0, self.app._drain_events)
        self.root.update()
        self.assertIs(self.app.state, self.app.controller.state)
        for widget in self.app._walk_widgets(window):
            if widget.winfo_ismapped() and widget.winfo_class() in {"TEntry", "TButton"}:
                with self.subTest(widget=str(widget)):
                    x = widget.winfo_rootx() - window.winfo_rootx()
                    y = widget.winfo_rooty() - window.winfo_rooty()
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + widget.winfo_width(), window.winfo_width())
                    self.assertLessEqual(y + widget.winfo_height(), window.winfo_height())
        window.destroy()

    def test_close_cancels_own_scheduled_callbacks_and_is_idempotent(self):
        scheduled = set(self.app._after_jobs)
        self.assertTrue(scheduled)
        with patch.object(AppConfig, "save") as save, patch.object(self.root, "destroy") as destroy:
            self.app.close()
            self.app.close()
        self.assertTrue(self.app._closed)
        self.assertFalse(self.app._after_jobs)
        self.assertFalse(scheduled.intersection(self.root.tk.call("after", "info")))
        save.assert_called_once()
        destroy.assert_called_once()
        self.app.controller.stop.assert_called_once()

    def test_invalid_connection_host_is_reported_without_callback_exception(self):
        original_top = tk.Toplevel
        def hidden(*args, **kwargs):
            window = original_top(*args, **kwargs)
            window.withdraw()
            return window
        with patch("spitfire_control.ui.tk.Toplevel", side_effect=hidden):
            self.app.show_connection_settings()
        window = next(w for w in self.root.winfo_children() if w.winfo_class() == "Toplevel")
        entries = [w for w in self.app._walk_widgets(window) if w.winfo_class() == "TEntry"]
        entries[0].delete(0, "end")
        button = next(w for w in self.app._walk_widgets(window) if w.winfo_class() == "TButton" and w.cget("text") == "SAVE & CONNECT")
        with patch.object(AppConfig, "save") as save, patch("spitfire_control.ui.messagebox.showerror") as error:
            button.invoke()
        error.assert_called_once()
        save.assert_not_called()
        self.app.connect.assert_not_called()
        window.destroy()


if __name__ == "__main__":
    unittest.main()

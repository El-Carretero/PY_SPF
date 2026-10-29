"""Headless workbench handlers; actual window geometry needs desktop testing."""
import json
import importlib.util
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from spitfire_twin_verifier.records import CaptureStore
from spitfire_twin_verifier.workbench_ui import WorkbenchPanel, evidence_rows, write_workbench_report


class Value:
    def __init__(self, value=""):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class WorkbenchHandlers(unittest.TestCase):
    def setUp(self):
        self.panel = p = WorkbenchPanel.__new__(WorkbenchPanel)
        p.root = SimpleNamespace(after=MagicMock())
        p.app = SimpleNamespace(root=p.root, server=None, capture=CaptureStore(),
                                original_label=Value("XP"), python_label=Value("PY"),
                                _update_setup_text=MagicMock(), latest_result=None)
        p.busy = False
        p.closed = False
        p.worker_queue = queue.Queue()
        p.progress = MagicMock()
        p.status = Value()
        p.live_status = Value()
        p.artifacts = []
        p.results = []
        p.applied_profiles = {}
        p.desired_scenario = None
        p.desired_clock = "realtime"
        p.clock = Value("manual")
        p.advance_ms = Value("1000")
        p.scenario = Value("scenario A")
        p.scenario_choices = {"scenario A": "external_nominal"}
        p.artifact_tree = MagicMock()
        p.output = MagicMock()
        p.profile_choices = {"XP": "xp_gui_1.6.0", "PY": "python_1.3.0"}
        p.left_profile = Value("XP")
        p.right_profile = Value("PY")

    def test_export_escapes_html_and_keeps_runs_separate(self):
        with tempfile.TemporaryDirectory() as d:
            payload = {"result": "<script>alert(1)</script>", "model_verdict": "PASS"}
            a = write_workbench_report(d, payload)
            b = write_workbench_report(d, payload)
            self.assertNotEqual(a, b)
            text = (a / "report.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>", text)
            self.assertIn("&lt;script&gt;", text)
            self.assertIn("Model PASS does not establish", text)
            self.assertEqual(json.loads((a / "report.json").read_text())["model_verdict"], "PASS")
            self.assertNotIn("exported_utc", payload)

    def test_model_summary_keeps_equivalence_unverified(self):
        rows = evidence_rows({"model_verdict": "PASS", "name": "test", "assertions": [
            {"at_ms": 1, "path": "inhibited", "expected": True, "actual": True, "passed": True}]})
        self.assertEqual(rows[0][2], "PASS")
        self.assertEqual(rows[-1][2], "UNVERIFIED")
        self.assertIn("실제", rows[0][3])

    def test_matrix_summary_exposes_real_differences(self):
        rows = evidence_rows({"clients": [{"inspection": {"version": "1.1.3"}, "cases": [
            {"label": "Fault decode", "status": "FAIL", "operations": [{"differences": ["value differs"]}]}]}]})
        self.assertEqual(rows[0], ("1.1.3", "Fault decode", "FAIL", "value differs"))

    def test_headless_report_module_does_not_import_tk(self):
        source_root = str(Path(__file__).resolve().parents[1] / "src")
        code = "import sys; sys.path.insert(0, " + repr(source_root) + "); import spitfire_twin_verifier.evidence_report; assert 'tkinter' not in sys.modules"
        completed = subprocess.run([sys.executable, "-I", "-c", code],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_smoke_visibility_rejects_unmapped_and_horizontal_clipping(self):
        source = Path(__file__).resolve().parents[1] / "tools" / "windows_gui_smoke.py"
        spec = importlib.util.spec_from_file_location("gui_smoke_geometry_test", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fits = module.control_visibility
        self.assertTrue(fits("TButton", True, [10, 10, 110, 40], [0, 0, 150, 50], [100, 30])["reachable"])
        self.assertFalse(fits("TButton", False, [10, 10, 110, 40], [0, 0, 150, 50], [100, 30])["reachable"])
        self.assertFalse(fits("TButton", True, [100, 10, 200, 40], [0, 0, 150, 50], [100, 30])["horizontal_visible"])
        self.assertFalse(fits("TButton", True, [10, 10, 11, 11], [0, 0, 150, 50], [100, 30])["usable_size"])

    def test_declined_trust_does_not_execute_source(self):
        self.panel.artifacts = [{"path": "/test/client.zip"}]
        with patch("spitfire_twin_verifier.workbench_ui.messagebox.askyesno", return_value=False), \
             patch.object(self.panel, "_submit") as submit:
            self.panel.run_client_matrix()
        submit.assert_not_called()

    def test_matrix_requires_explicit_trust_and_captures_paths(self):
        self.panel.artifacts = [{"path": "/test/client.zip"}]
        with patch("spitfire_twin_verifier.workbench_ui.messagebox.askyesno", return_value=True), \
             patch.object(self.panel, "_submit") as submit, \
             patch("spitfire_twin_verifier.workbench_ui.run_matrix", return_value={}) as run:
            self.panel.run_client_matrix()
            self.panel.artifacts.clear()
            submit.call_args.args[1]()
        run.assert_called_once_with(["/test/client.zip"], trusted=True)

    def test_model_execution_does_not_run_client_matrix(self):
        with patch.object(self.panel, "_submit") as submit, \
             patch("spitfire_twin_verifier.workbench_ui.run_scenario", return_value={}) as model, \
             patch("spitfire_twin_verifier.workbench_ui.run_matrix") as matrix:
            self.panel.run_model()
            submit.call_args.args[1]()
        model.assert_called_once_with("external_nominal")
        matrix.assert_not_called()

    def test_profile_selection_is_not_execution_evidence(self):
        self.panel.apply_profiles()
        metadata = self.panel.app.capture.snapshot().metadata
        self.assertFalse(metadata["selected_client_profiles"]["selection_is_execution_evidence"])
        self.assertEqual(metadata["selected_client_profiles"]["candidate"]["version"], "1.3.0")
        self.assertIn("UNVERIFIED", metadata["xp_execution_evidence"])

    def test_running_server_prevents_profile_relabeling(self):
        self.panel.app.server = SimpleNamespace(running=True)
        with patch("spitfire_twin_verifier.workbench_ui.messagebox.showwarning") as warn:
            self.panel.apply_profiles()
        warn.assert_called_once()
        self.assertEqual(self.panel.app.original_label.get(), "XP")

    def test_live_configuration_copied_into_server(self):
        self.panel.desired_scenario = {"id": "test", "events": []}
        self.panel.desired_clock = "manual"
        server = MagicMock()
        self.panel.configure_server(server)
        server.set_scenario.assert_called_once_with({"id": "test", "events": []}, clock="manual")
        server.set_scenario.call_args.args[0]["events"].append("changed")
        self.assertEqual(self.panel.desired_scenario["events"], [])

    def test_manual_advance_requires_manual_live_server(self):
        self.panel.desired_scenario = {"id": "test"}
        server = MagicMock(running=True)
        self.panel.app.server = server
        with patch("spitfire_twin_verifier.workbench_ui.messagebox.showwarning"):
            self.panel.advance_live()
        server.advance_scenario.assert_not_called()
        self.panel.desired_clock = "manual"
        server.advance_scenario.return_value = {}
        self.panel.advance_live()
        server.advance_scenario.assert_called_once_with(1000.0)

    def test_worker_error_is_drained_on_main_thread(self):
        event = threading.Event()
        def work():
            event.set()
            raise ValueError("bad fixture")
        self.assertTrue(self.panel._submit("test", work))
        self.assertTrue(event.wait(2))
        # Join only the owned short test worker to make this deterministic.
        for thread in threading.enumerate():
            if thread.name == "spitfire-workbench":
                thread.join(2)
        self.panel.output.insert.assert_not_called()
        self.panel._drain_results()
        self.assertFalse(self.panel.busy)
        self.assertEqual(self.panel.results[0]["result"]["error"], "ValueError: bad fixture")
        self.assertFalse(self.panel.results[0]["operation_completed"])
        self.panel.output.insert.assert_called_once()

    def test_busy_prevents_overlapping_jobs(self):
        self.panel.busy = True
        work = MagicMock()
        self.assertFalse(self.panel._submit("test", work))
        work.assert_not_called()

    def test_closed_panel_does_not_schedule_tk_callback(self):
        self.panel.closed = True
        self.panel._drain_results()
        self.panel.root.after.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Visible, loopback-only Tk smoke test; never loads or saves user configuration.

Run on the intended Windows desktop:
  python tools/windows_gui_smoke.py --output C:\\path\\gui_smoke.json

Optional --screenshot writes only the application's own client-window crop for
internal visual review. It is not needed for the test and is not a deliverable.
This is a Verifier UI test, NOT an XP vendor GUI or physical hardware test.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import queue
import socket
import sys
import tempfile
import threading
import time
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import tkinter as tk
from spitfire_twin_verifier import __version__
from spitfire_twin_verifier.app import VerifierApp
from spitfire_twin_verifier.config import AppConfig
from spitfire_twin_verifier.protocol import decode_replies, encode_commands


def pump_until(root, condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    pause = threading.Event()
    while time.monotonic() < deadline:
        root.update()
        if condition():
            root.update_idletasks()
            return
        pause.wait(0.02)
    raise TimeoutError(f"GUI condition did not complete within {timeout:g} s")


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def control_visibility(kind, mapped, rect, visible_rect, requested_size):
    """Pure geometry predicate: unmapped/clipped/tiny controls never pass."""
    x, y, right, bottom = rect
    left_limit, top_limit, right_limit, bottom_limit = visible_rect
    width, height = right - x, bottom - y
    requested_width, requested_height = requested_size
    horizontal = x >= left_limit - 2 and right <= right_limit + 2
    vertical = y >= top_limit - 2 and bottom <= bottom_limit + 2
    usable_size = width >= 32 and height >= requested_height - 2
    if kind in {"TButton", "TRadiobutton"}:
        usable_size = usable_size and width >= requested_width - 2
    return {"mapped": bool(mapped), "horizontal_visible": horizontal,
            "vertical_visible": vertical, "usable_size": usable_size,
            "reachable": bool(mapped and horizontal and vertical and usable_size)}


def inspect_layout(root, workbench, width, height):
    # A screen-width client plus a Windows non-client border is wider than
    # the screen. Preserve the requested test size, but fit its actual window.
    actual_width = min(width, max(800, root.winfo_screenwidth() - 32))
    actual_height = min(height, max(560, root.winfo_screenheight() - 80))
    root.geometry(f"{actual_width}x{actual_height}+8+8")
    root.update()
    workbench.viewport.yview_moveto(0)
    root.update()
    controls = [w for w in descendants(workbench.parent)
                if w.winfo_class() in {"TButton", "TRadiobutton", "TCombobox", "TEntry"}]
    rows = []
    total_height = workbench.parent.winfo_height()
    for control in controls:
        relative_y = control.winfo_rooty() - workbench.parent.winfo_rooty()
        workbench.viewport.yview_moveto(max(0.0, (relative_y - 12) / max(1, total_height)))
        root.update()
        left, top = workbench.viewport.winfo_rootx(), workbench.viewport.winfo_rooty()
        right = left + workbench.viewport.winfo_width()
        bottom = top + workbench.viewport.winfo_height()
        # Geometry can exist outside a clipped parent or for an unmapped
        # 1x1 widget. Check the visible intersection through every ancestor,
        # plus the actual screen, not only the canvas' own geometry.
        ancestor = control.master
        while ancestor is not None:
            left = max(left, ancestor.winfo_rootx())
            top = max(top, ancestor.winfo_rooty())
            right = min(right, ancestor.winfo_rootx() + ancestor.winfo_width())
            bottom = min(bottom, ancestor.winfo_rooty() + ancestor.winfo_height())
            ancestor = ancestor.master
        left, top = max(0, left), max(0, top)
        right, bottom = min(root.winfo_screenwidth(), right), min(root.winfo_screenheight(), bottom)
        x, y, w, h = (control.winfo_rootx(), control.winfo_rooty(),
                      control.winfo_width(), control.winfo_height())
        try:
            label = str(control.cget("text"))
        except tk.TclError:
            label = str(control.winfo_class())
        visibility = control_visibility(control.winfo_class(), control.winfo_ismapped(),
                                        [x, y, x + w, y + h], [left, top, right, bottom],
                                        [control.winfo_reqwidth(), control.winfo_reqheight()])
        rows.append({"class": control.winfo_class(), "label": label,
                     "width": w, "height": h, "requested_width": control.winfo_reqwidth(),
                     **visibility, "widget_rect": [x, y, x + w, y + h],
                     "visible_rect": [left, top, right, bottom],
                     })
    workbench.viewport.yview_moveto(1)
    root.update()
    bottom_reachable = workbench.viewport.yview()[1] >= 0.999
    result = {"requested": [width, height], "actual": [root.winfo_width(), root.winfo_height()],
              "viewport_height": workbench.viewport.winfo_height(),
              "content_height": workbench.parent.winfo_height(),
              "bottom_reachable": bottom_reachable, "controls": rows,
              "status": "PASS" if rows and all(r["reachable"] for r in rows) and bottom_reachable else "FAIL"}
    workbench.viewport.yview_moveto(0)
    root.update()
    return result


def query_on_worker(root, endpoint, source_ip):
    """The main Tk thread never blocks in socket.recvfrom."""
    output = queue.Queue()
    def exchange():
        try:
            if endpoint[0] != "127.0.0.1" or source_ip not in {"127.0.0.2", "127.0.0.3"}:
                raise ValueError("Smoke probe only permits explicit loopback addresses")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.bind((source_ip, 0))
                client.settimeout(2.0)
                request = encode_commands(["[1000]*IDN?"])
                client.sendto(request, endpoint)
                response, sender = client.recvfrom(65535)
                replies = decode_replies(response)
                output.put({"request_hex": request.hex(), "response_hex": response.hex(),
                            "sender": list(sender), "source_ip": source_ip,
                            "replies": [asdict(reply) for reply in replies]})
        except Exception as exc:
            output.put({"error": f"{type(exc).__name__}: {exc}"})
    worker = threading.Thread(target=exchange, name="gui-smoke-probe", daemon=True)
    worker.start()
    pump_until(root, lambda: not output.empty(), timeout=4)
    worker.join(timeout=0.1)
    item = output.get_nowait()
    if "error" in item:
        raise RuntimeError(item["error"])
    if len(item["replies"]) != 1 or item["replies"][0]["command_id"] != 1000:
        raise AssertionError("IDN query did not produce exactly one expected reply")
    return item


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="JSON evidence file")
    parser.add_argument("--screenshot", type=Path, help="Optional own-window PNG for internal visual review")
    args = parser.parse_args(argv)
    evidence = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                "verifier_version": __version__, "python": sys.version,
                "platform": platform.platform(), "status": "ERROR",
                "scope": "Actual Verifier Tk construction, handlers, geometry, synthetic model, and internal loopback probe",
                "xp_vendor_execution": "NOT_PERFORMED", "physical_hardware": "NOT_PERFORMED",
                "user_configuration": "not loaded; AppConfig.save mocked",
                "layouts": [], "dialogs": [], "callback_errors": []}
    root = app = None
    output_dir = args.output.resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="spitfire-gui-smoke-") as temporary, \
         patch.object(AppConfig, "save", return_value=None) as save_mock, \
         patch("tkinter.messagebox.askyesno", return_value=False), \
         patch("tkinter.messagebox.showerror", side_effect=lambda *a, **k: evidence["dialogs"].append({"kind": "error", "text": list(a)})), \
         patch("tkinter.messagebox.showwarning", side_effect=lambda *a, **k: evidence["dialogs"].append({"kind": "warning", "text": list(a)})), \
         patch("tkinter.messagebox.showinfo", side_effect=lambda *a, **k: evidence["dialogs"].append({"kind": "info", "text": list(a)})):
        try:
            root = tk.Tk()
            root.report_callback_exception = lambda kind, value, tb: evidence["callback_errors"].append(
                "".join(traceback.format_exception(kind, value, tb)))
            evidence["screen"] = [root.winfo_screenwidth(), root.winfo_screenheight()]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            config = AppConfig(bind_ip="127.0.0.1", bind_port=port,
                               original_ip="127.0.0.2", python_ip="127.0.0.3",
                               original_label="Smoke probe A (not XP)",
                               python_label="Smoke probe B (not Python client)",
                               output_directory=str(output_dir / "gui_smoke_reports"))
            app = VerifierApp(root, config)
            root.title(f"Spitfire Verifier {__version__} — isolated UI smoke test")
            root.lift()
            root.update()
            wb = app.workbench
            app.notebook.select(app.workbench_tab)
            for width, height in ((1536, 768), (1024, 768)):
                evidence["layouts"].append(inspect_layout(root, wb, width, height))
            if any(layout["status"] != "PASS" for layout in evidence["layouts"]):
                raise AssertionError("Some workbench controls are unreachable at a tested geometry")

            choice = next(label for label, sid in wb.scenario_choices.items() if sid == "nominal_external_10hz")
            wb.scenario.set(choice)
            wb.run_model()
            pump_until(root, lambda: not wb.busy and bool(wb.results), timeout=10)
            model = wb.results[-1]["result"]
            evidence["model"] = model
            summary_rows = [list(wb.result_tree.item(iid, "values")) for iid in wb.result_tree.get_children()]
            evidence["model_summary_rows"] = summary_rows
            if (model.get("model_verdict") != "PASS" or model.get("client_equivalence") != "UNVERIFIED"
                    or not any("UNVERIFIED" in row for row in summary_rows)):
                raise AssertionError("Model result or evidence boundary not shown correctly")

            wb.clock.set("manual")
            wb.stage_live_scenario()
            app.toggle_server()
            if not app.server or not app.server.running:
                raise AssertionError("GUI start handler did not start the loopback virtual server")
            endpoint = app.server.local_address
            if endpoint[0] != "127.0.0.1":
                raise AssertionError("Server bound outside the required loopback address")
            evidence["endpoint"] = list(endpoint)
            evidence["probes"] = [query_on_worker(root, endpoint, "127.0.0.2")]
            wb.advance_ms.set("200")
            wb.advance_live()
            evidence["probes"].append(query_on_worker(root, endpoint, "127.0.0.3"))
            pump_until(root, lambda: len(app.capture.transactions()) == 2, timeout=3)
            app._poll_events()
            evidence["capture_transactions"] = [asdict(item) for item in app.capture.transactions()]
            evidence["capture_metadata"] = app.capture.snapshot().metadata
            if evidence["capture_metadata"].get("scenario_clock") != "manual":
                raise AssertionError("Manual scenario clock was not persisted in capture metadata")
            app.toggle_server()
            if app.server is not None:
                raise AssertionError("GUI stop handler did not release the server")
            app.export_report()
            wb.export()
            evidence["comparison_reports"] = [str(p) for p in (output_dir / "gui_smoke_reports").glob("comparison_*/report.json")]
            evidence["workbench_reports"] = [str(p) for p in (output_dir / "gui_smoke_reports").glob("workbench_*/report.json")]
            if not evidence["comparison_reports"] or not evidence["workbench_reports"]:
                raise AssertionError("Both GUI report exports must produce JSON evidence")

            # Restore model summary for an optional screenshot; only this app's
            # client rectangle is captured, never the surrounding desktop.
            wb._show(wb.results[-1])
            root.geometry("1280x800+0+0")
            wb.viewport.yview_moveto(0)
            root.update()
            if args.screenshot:
                try:
                    from PIL import ImageGrab
                    root.attributes("-topmost", True)
                    root.lift()
                    root.update()
                    bbox = (root.winfo_rootx(), root.winfo_rooty(),
                            root.winfo_rootx() + root.winfo_width(), root.winfo_rooty() + root.winfo_height())
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    ImageGrab.grab(bbox=bbox).save(args.screenshot)
                    evidence["internal_window_screenshot"] = str(args.screenshot.resolve())
                    root.attributes("-topmost", False)
                except ImportError:
                    evidence["screenshot"] = "SKIPPED: Pillow not installed"
            if evidence["dialogs"] or evidence["callback_errors"]:
                raise AssertionError("Unexpected dialog or Tk callback error; inspect evidence")
            evidence["config_save_calls_suppressed"] = save_mock.call_count
            evidence["status"] = "PASS"
        except Exception as exc:
            evidence["error"] = f"{type(exc).__name__}: {exc}"
            evidence["traceback"] = traceback.format_exc()
        finally:
            if app is not None:
                if app.server is not None:
                    app.server.stop()
                app.workbench.closed = True
            if root is not None:
                try:
                    for job in root.tk.call("after", "info"):
                        root.after_cancel(job)
                    root.destroy()
                except tk.TclError:
                    pass
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "output": str(args.output.resolve()),
                      "error": evidence.get("error"), "xp_vendor_execution": "NOT_PERFORMED"}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

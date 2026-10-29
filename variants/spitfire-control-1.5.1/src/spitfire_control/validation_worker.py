"""Isolated offline checks, also used by the Windows EXE self-test entry point.

The I/O fence is deliberately process-local and permanent. Never install it
in an ordinary operator session. It supplements the explicit Simulator config;
it is not an OS sandbox or a defence against malicious modified Python code.
"""
from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
from pathlib import Path
import sys
import time
import traceback
import unittest
from unittest.mock import patch

from . import __version__


def install_offline_fence(*, loopback: bool) -> None:
    def permitted(host):
        if not loopback:
            return False
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def audit(event, args):
        if event in {"socket.connect", "socket.sendto", "socket.bind"}:
            address = args[-1]
            if not isinstance(address, tuple) or not permitted(address[0]):
                raise PermissionError("Offline validation blocks non-loopback/device I/O")
        elif event in {"socket.getaddrinfo", "socket.gethostbyname"}:
            if not permitted(args[0]):
                raise PermissionError("Offline validation blocks external DNS")

    sys.addaudithook(audit)
    # Fail before pySerial can open a COM device or toggle DTR/RTS.
    import serial
    def no_serial(*args, **kwargs):
        raise PermissionError("Serial ports are disabled during offline validation")
    serial.Serial.open = no_serial


def gui_probe(work_dir: Path, *, pump_mode: str = "empower") -> dict:
    if pump_mode == "external":
        return external_gui_probe(work_dir)
    install_offline_fence(loopback=False)
    import tkinter as tk
    from .config import AppConfig
    from .ui import SpitfireApp

    root = tk.Tk()
    root.attributes("-alpha", 0.0)  # Validation does not expose a live operator window.
    errors = []
    root.report_callback_exception = lambda *args: errors.append("".join(traceback.format_exception(*args)))
    app = None
    result = {}
    try:
        # Never read the operator's persisted UDP settings.
        app = SpitfireApp(root, AppConfig(mode="simulator", auto_poll=True,
                           log_directory=str(work_dir / "simulator-audit")))
        width = min(1024, root.winfo_screenwidth())
        height = min(768, max(1, root.winfo_screenheight() - 80))
        root.geometry(f"{width}x{height}")

        def pump_until(predicate, timeout=6):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                root.update()
                if errors:
                    raise RuntimeError(errors[0])
                if predicate():
                    return
                time.sleep(.01)
            raise TimeoutError("Simulator GUI did not reach the expected state")

        pump_until(lambda: app.state.connected and app.state.value(1010) == 1000)
        draft = app.drafts[1010]
        draft.variable.set("1250")
        if not app.issue(2004, draft.variable.get()):
            raise RuntimeError("Simulator PRF command was not queued")
        pump_until(lambda: app.state.value(1010) == 1250 and not draft.dirty)
        draft.variable.set("1500")
        prior = app.state.updated_at[1010]
        app.controller.query_now((1010,))
        pump_until(lambda: app.state.updated_at[1010] > prior)
        if draft.variable.get() != "1500" or float(draft.readback.get()) != 1250:
            raise AssertionError("GUI polling overwrote the pending edit")
        draft.reset()
        if float(draft.variable.get()) != 1250:
            raise AssertionError("USE READBACK did not restore the confirmed value")
        app._build_service_controls()
        clipped = []
        def walk(widget):
            for child in widget.winfo_children():
                yield child
                yield from walk(child)
        tab_names = []
        for tab in app.notebook.tabs():
            app.notebook.select(tab)
            root.update()
            name = app.notebook.tab(tab, "text")
            tab_names.append(name)
            for w in walk(root.nametowidget(tab)):
                if w.winfo_ismapped() and w.winfo_class() in {"TButton", "TEntry", "TCombobox", "TCheckbutton"}:
                    x, y = w.winfo_rootx() - root.winfo_rootx(), w.winfo_rooty() - root.winfo_rooty()
                    if x < 0 or y < 0 or x + w.winfo_width() > root.winfo_width() or y + w.winfo_height() > root.winfo_height():
                        clipped.append({"tab": name, "widget": str(w)})
        app.rs232_warning_acknowledged = True
        app._raw_serial_shortcut()
        if app.raw_serial_dialog is None or app.raw_serial_dialog.session.connected:
            raise AssertionError("Raw serial dialog opened a device unexpectedly")
        if errors:
            raise RuntimeError(errors[0])
        result = {"status": "WARN" if clipped else "PASS", "version": __version__,
                  "kind": "gui", "mode": "simulator", "tk": root.tk.call("info", "patchlevel"),
                  "screen": [root.winfo_screenwidth(), root.winfo_screenheight()],
                  "window": [root.winfo_width(), root.winfo_height()], "tabs": tab_names,
                  "clipped_controls": clipped, "prf_round_trip_hz": 1250,
                  "draft_preserved_hz": 1500, "serial_open": False,
                  "external_io": "blocked", "settings_loaded_or_saved": False}
    finally:
        if app is not None:
            with patch.object(AppConfig, "save"):
                app.close()
            if app.controller and app.controller.running:
                raise RuntimeError("Simulator controller did not shut down")
        else:
            root.destroy()
    return result


def external_gui_probe(work_dir: Path) -> dict:
    """Exercise the real GUI/controller in a missing-Empower simulator only."""
    install_offline_fence(loopback=False)
    import tkinter as tk
    from .config import AppConfig
    from .ui import SpitfireApp
    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    errors = []
    root.report_callback_exception = lambda *args: errors.append("".join(traceback.format_exception(*args)))
    app = None
    try:
        app = SpitfireApp(root, AppConfig(mode="simulator", pump_mode="external", auto_poll=False,
                                         log_directory=str(work_dir / "external-simulator-audit")))
        root.geometry("1024x768")
        def wait_for(predicate, timeout=8):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                root.update()
                if errors:
                    raise RuntimeError(errors[0])
                if predicate():
                    return
                time.sleep(0.01)
            raise TimeoutError("External simulator GUI condition not reached")
        wait_for(lambda: app.state.high_voltage is False and app.state.is_fresh(1068))
        if any(cid >= 2000 for cid, _ in app.controller.transport.command_history):
            raise AssertionError("Startup wrote to the controller")
        if app.state.external_opt_out_confirmed:
            raise AssertionError("Opt-out was applied automatically")
        app._apply_external_opt_out()
        wait_for(lambda: app.state.external_opt_out_confirmed)
        with patch("tkinter.messagebox.askyesno", return_value=True):
            if not app._apply_external_sources():
                raise AssertionError("Explicit external timing configuration was rejected")
        wait_for(lambda: not app.state.external_enable_reason())
        app.issue(2017)
        wait_for(lambda: app.state.high_voltage is True)
        wait_for(lambda: not app.controller._pc_run_reason())
        app._run_laser()
        wait_for(lambda: app.controller.pc_output_status.status == "confirmed")
        app.software_standby()
        wait_for(lambda: app.controller.pc_output_status.action == "STOP" and app.controller.pc_output_status.status == "confirmed")
        if app.state.high_voltage is not True:
            raise AssertionError("PC STOP unexpectedly changed HV state")
        app.issue(2016)
        wait_for(lambda: app.state.high_voltage is False)
        forbidden = {2005, 2006, 2027, 2028, 2034, 2044, 2050}
        if any(cid in forbidden for cid, _ in app.controller.transport.command_history):
            raise AssertionError("External profile emitted a pump/global command")
        clipped = []
        def walk(widget):
            for child in widget.winfo_children():
                yield child
                yield from walk(child)
        for tab in app.notebook.tabs():
            if app.notebook.tab(tab, "state") == "disabled":
                continue
            app.notebook.select(tab)
            root.update()
            for w in walk(root.nametowidget(tab)):
                if w.winfo_ismapped() and w.winfo_class() in {"TButton", "TEntry", "TCombobox", "TCheckbutton"}:
                    x, y = w.winfo_rootx() - root.winfo_rootx(), w.winfo_rooty() - root.winfo_rooty()
                    if x < 0 or y < 0 or x + w.winfo_width() > root.winfo_width() or y + w.winfo_height() > root.winfo_height():
                        clipped.append({"tab": app.notebook.tab(tab, "text"), "widget": str(w)})
        return {"status": "WARN" if clipped else "PASS", "version": __version__, "kind": "external_gui",
                "mode": "simulator", "pump_mode": "external", "empower_present": False,
                "startup_writes": 0, "explicit_opt_out_readback": 1, "external_sources_confirmed": True, "hv_on_off_verified": True, "pc_run_stop_verified": True,
                "external_pump_emission": "unmonitored", "clipped_controls": clipped,
                "external_io": "blocked", "settings_loaded_or_saved": False}
    finally:
        if app is not None:
            with patch.object(AppConfig, "save"):
                app.close()
        else:
            root.destroy()


def tests_probe(work_dir: Path, tests_dir: Path) -> dict:
    install_offline_fence(loopback=True)
    if not tests_dir.is_dir():
        return {"status": "SKIP", "kind": "tests", "detail": "Test sources are not installed; use the source ZIP"}
    with (work_dir / "unittest.txt").open("w", encoding="utf-8") as stream:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            suite = unittest.defaultTestLoader.discover(str(tests_dir))
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {"status": "FAIL" if not result.wasSuccessful() else ("WARN" if result.skipped else "PASS"),
            "kind": "tests", "tests_run": result.testsRun,
            "skipped": [[str(test), reason] for test, reason in result.skipped],
            "failures": len(result.failures), "errors": len(result.errors),
            "network": "loopback only", "serial_open": "blocked"}


def write_result(path: Path, callback) -> int:
    # A new output path avoids accepting a stale report from a failed EXE.
    if path.exists():
        raise FileExistsError(f"Self-test output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = callback()
    except Exception as exc:
        result = {"status": "FAIL", "version": __version__, "detail": str(exc),
                  "traceback": traceback.format_exc()}
    with path.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return 0 if result["status"] == "PASS" else (2 if result["status"] in {"SKIP", "WARN"} else 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("gui", "tests"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tests-dir", type=Path)
    args = parser.parse_args(argv)
    if args.kind == "tests" and args.tests_dir is None:
        parser.error("--tests-dir is required")
    callback = (lambda: gui_probe(args.output.parent)) if args.kind == "gui" else (lambda: tests_probe(args.output.parent, args.tests_dir))
    return write_result(args.output, callback)


if __name__ == "__main__":
    raise SystemExit(main())

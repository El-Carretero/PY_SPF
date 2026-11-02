r"""Load the real Windows x86 NI GUI with simulator-only device transport.

Run as a separate process: .venv-native\Scripts\python tools/verify_native_demo.py
Never uses the physical device or the TCP server. The NI shutdown boundary is
the same ExitProcess boundary as the application; do not import this in pytest.
"""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import struct
import sys
import time
import traceback
from unittest.mock import patch


def native_visibility(view):
    """Read actual NI attributes; controller caches alone cannot prove painting."""
    menu = view.dll.GetPanelMenuBar(view.panels[6])
    menu_dimmed = ctypes.c_int()
    view._check(view.dll.GetMenuBarAttribute(menu, 0, 500, ctypes.byref(menu_dimmed)),
                "read main menu dimmed state")
    return {"curtain_visible": view.read_attribute(6, 49, 530),
            "loading_text_visible": view.read_attribute(6, 54, 530),
            "run_visible": view.read_attribute(6, 10, 530),
            "stop_visible": view.read_attribute(6, 11, 530),
            "menu_dimmed": menu_dimmed.value}


def native_dimming(view):
    return {"run": view.read_attribute(6, 10, 500),
            "stop": view.read_attribute(6, 11, 500)}


def save_snapshot(view, path):
    """Ask the original NI renderer for a BMP; no extra imaging dependency."""
    if path.suffix.lower() != ".bmp":
        raise ValueError("--snapshot requires a .bmp output path")

    class Rect(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int) for name in ("top", "left", "height", "width")]

    bitmap = ctypes.c_int()
    capture = view.dll.GetPanelDisplayBitmap
    capture.argtypes = [ctypes.c_int, ctypes.c_int, Rect, ctypes.POINTER(ctypes.c_int)]
    capture.restype = ctypes.c_int
    view._check(capture(view.panels[6], 1, Rect(0, 0, -1, -1), ctypes.byref(bitmap)),
                "capture native main panel")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        view._check(view.dll.SaveBitmapToBMPFile(bitmap.value, view._bytes(path.resolve())),
                    "save native main panel BMP")
    finally:
        view.dll.DiscardBitmap(bitmap.value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration", type=float, default=20.0,
                        help="maximum seconds to wait for the actual usable main screen")
    scenario = parser.add_mutually_exclusive_group()
    scenario.add_argument("--drop-optout-ack", action="store_true",
                          help="simulator applies Opt-out but drops its write ACK")
    scenario.add_argument("--offline", action="store_true",
                          help="simulate an entirely silent device and verify visible disabled controls")
    parser.add_argument("--snapshot", type=Path, help="save main panel as a native-rendered .bmp")
    args = parser.parse_args()
    if sys.platform != "win32" or struct.calcsize("P") != 4:
        raise SystemExit("Native demo verification requires 32-bit Windows Python.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from spitfire.__main__ import arguments, make_controller
    from spitfire.native import NativeGui
    from spitfire.protocol import PACKET_PREFIX
    from spitfire.simulator import SimulatedTransport

    class MissingOptoutAckTransport(SimulatedTransport):
        dropped_optout_acks = 0

        def receive(self):
            replies = super().receive()
            filtered = [reply for reply in replies if not reply.body.startswith("<2036>")]
            self.dropped_optout_acks += len(replies) - len(filtered)
            return filtered

    class SilentTransport(SimulatedTransport):
        def receive(self):
            return []

    result = {"python": sys.version.split()[0], "bits": 32, "mode": "simulator",
              "tcp_server": False, "drop_optout_ack": args.drop_optout_ack,
              "expected_offline": args.offline, "phases": []}
    view = controller = None
    transport_patch = None
    code = 1
    try:
        print("Loading original NI GUI ...", flush=True)
        view = NativeGui()
        result["phases"].append("native_loaded")
        result["panels"] = len(view.panels)
        print(f"Loaded {len(view.panels)} panels", flush=True)
        opts = arguments(["--demo", "--backend", "native", "--tcp-port", "0", "--local-port", "0"])
        if args.drop_optout_ack or args.offline:
            transport_patch = patch("spitfire.controller.SimulatedTransport",
                                    SilentTransport if args.offline else MissingOptoutAckTransport)
            transport_patch.start()
        controller = make_controller(view, opts)
        view.attach(controller)
        controller.start()
        started = time.monotonic()
        deadline = started + args.duration
        ticks = 0
        ready = False
        offline_verified = False
        status_received = False
        while controller.running and time.monotonic() < deadline:
            view.process_events()
            controller.tick()
            ticks += 1
            status_received = any(kind == "RX" and "<1085>" in str(value)
                                  for _, kind, value in controller.events)
            if args.offline:
                failed_startup = (controller.startup is not None and controller.startup.complete
                                  and controller._startup_retry_deadline is not None)
                if failed_startup:
                    visible = native_visibility(view)
                    offline_verified = (
                        not controller.state.get("connected")
                        and controller.state.get("gui_ready") is False
                        and controller.state.get("curtain_not_open") == 1
                        and visible == {"curtain_visible": 0, "loading_text_visible": 0,
                                        "run_visible": 1, "stop_visible": 1, "menu_dimmed": 0}
                        and native_dimming(view) == {"run": 1, "stop": 1}
                        and view.read_attribute(6, 50, 641) == "NOT CONNECTED")
                    if offline_verified:
                        break
            elif (status_received and controller.state.get("curtain_not_open") == 0
                  and controller.state.get("gui_ready") is True):
                visible = native_visibility(view)
                if visible == {"curtain_visible": 0, "loading_text_visible": 0,
                               "run_visible": 1, "stop_visible": 1, "menu_dimmed": 0}:
                    ready = True
                    break
            time.sleep(0.005)
        # Paint queued show/hide changes before visual evidence is captured.
        for _ in range(5):
            view.process_events()
            time.sleep(0.01)
        result.update(connected=bool(controller.state.get("connected")),
                      emp_optout=controller.state["emp_optout"],
                      displayed_optout=view.read(2, 9),
                      controls_updated=len(controller.values),
                      callback_errors=[str(value) for _, kind, value in controller.events if kind == "callback"],
                      ready=ready, elapsed_seconds=round(time.monotonic() - started, 3), ticks=ticks,
                      gui_ready=bool(controller.state.get("gui_ready")),
                      offline_verified=offline_verified,
                      status_received=status_received,
                      curtain_not_open=controller.state.get("curtain_not_open"),
                      native_visibility=native_visibility(view),
                      controls_dimmed=native_dimming(view),
                      alarm_label=view.read_attribute(6, 50, 641),
                      startup_complete=bool(controller.startup and controller.startup.complete),
                      retry_scheduled=controller._startup_retry_deadline is not None,
                      last_sent=str(controller.scheduler.last_sent),
                      balance=controller.scheduler.balance,
                      dropped_optout_acks=getattr(controller.transport, "dropped_optout_acks", 0))
        packets = b"".join(controller.transport.sent_packets)
        lines = [line for packet in controller.transport.sent_packets
                 for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines()]
        result["optout_write_count"] = packets.count(b"[2036]EMPOPTOUT 1\n")
        result["identity_query_count"] = lines.count("[1000]*idn?")
        result["write_command_count"] = sum(int(line[1:line.index("]")]) >= 2000 for line in lines)
        assert result["panels"] == 10, result
        assert not result["callback_errors"], result
        if args.offline:
            assert result["offline_verified"], result
            assert result["identity_query_count"] == 3, result
            assert result["write_command_count"] == 0, result
            assert lines == ["[1000]*idn?"] * 3, result
            assert not result["status_received"], result
        else:
            assert result["connected"], result
            assert result["gui_ready"], result
            assert result["emp_optout"] == result["displayed_optout"] == 1, result
            assert result["optout_write_count"] == 1, result
            assert result["ready"], result
        if args.drop_optout_ack:
            assert result["dropped_optout_acks"] == 1, result
        if args.snapshot:
            save_snapshot(view, args.snapshot)
            result["snapshot"] = str(args.snapshot)
        result["phases"].append("offline_verified" if args.offline else "demo_verified")
        code = 0
    except BaseException:
        result["error"] = traceback.format_exc()
        traceback.print_exc()
    finally:
        try:
            if controller is not None:
                controller.stop()
            if view is not None:
                view.close()
            if transport_patch is not None:
                transport_patch.stop()
            result["phases"].append("closed")
        except BaseException:
            result["close_error"] = traceback.format_exc()
            traceback.print_exc()
            code = 1
        result["exit_code"] = code
        text = json.dumps(result, indent=2)
        print(text, flush=True)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        sys.stdout.flush()
        sys.stderr.flush()
        ctypes.WinDLL("kernel32").ExitProcess(code)


if __name__ == "__main__":
    main()

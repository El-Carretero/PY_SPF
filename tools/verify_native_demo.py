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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration", type=float, default=3.0)
    args = parser.parse_args()
    if sys.platform != "win32" or struct.calcsize("P") != 4:
        raise SystemExit("Native demo verification requires 32-bit Windows Python.")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from spitfire.__main__ import arguments, make_controller
    from spitfire.native import NativeGui

    result = {"python": sys.version.split()[0], "bits": 32, "mode": "simulator",
              "tcp_server": False, "phases": []}
    view = controller = None
    code = 1
    try:
        print("Loading original NI GUI ...", flush=True)
        view = NativeGui()
        result["phases"].append("native_loaded")
        result["panels"] = len(view.panels)
        print(f"Loaded {len(view.panels)} panels", flush=True)
        opts = arguments(["--demo", "--backend", "native", "--tcp-port", "0", "--local-port", "0"])
        controller = make_controller(view, opts)
        view.attach(controller)
        controller.start()
        deadline = time.monotonic() + args.duration
        while controller.running and time.monotonic() < deadline:
            view.process_events()
            controller.tick()
            time.sleep(0.005)
        result.update(connected=bool(controller.state.get("connected")),
                      emp_optout=controller.state["emp_optout"],
                      displayed_optout=view.read(2, 9),
                      controls_updated=len(controller.values),
                      callback_errors=[str(value) for _, kind, value in controller.events if kind == "callback"])
        packets = b"".join(controller.transport.sent_packets)
        result["optout_write_count"] = packets.count(b"[2036]EMPOPTOUT 1\n")
        assert result["panels"] == 10, result
        assert result["connected"], result
        assert result["emp_optout"] == result["displayed_optout"] == 1, result
        assert result["optout_write_count"] == 1, result
        assert not result["callback_errors"], result
        result["phases"].append("demo_verified")
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

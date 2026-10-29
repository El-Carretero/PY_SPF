"""Run the reconstructed program: python -m spitfire [--demo]."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import struct
import sys
import time


def arguments(argv=None):
    p = argparse.ArgumentParser(description="Spitfire External Control 2.0 — Empower-independent")
    p.add_argument("--demo", action="store_true", help="use the development simulator; no instrument connection")
    p.add_argument("--backend", choices=("auto", "native", "qt"), default="auto",
                   help="native uses original NI GUI runtime on 32-bit Windows Python")
    p.add_argument("--host", default="10.19.70.13", help="instrument IPv4 address")
    p.add_argument("--port", type=int, default=1024, help="instrument UDP port")
    p.add_argument("--local-port", type=int, default=1024, help="local UDP bind port")
    p.add_argument("--tcp-port", type=int, default=1001, help="local status server; 0 disables")
    p.add_argument("--tcp-host", default="127.0.0.1", help="TCP status server interface (default: loopback)")
    p.add_argument("--config", type=Path, help="override original C:\\config.sp access settings path")
    p.add_argument("--data-dir", type=Path, default=Path.cwd(), help="datalog.csv destination")
    p.add_argument("--headless", action="store_true", help="run the controller with an in-memory view")
    p.add_argument("--duration", type=float, default=2.0, help="headless/preview runtime in seconds")
    p.add_argument("--render-dir", type=Path, help="save Qt panel previews and exit")
    return p.parse_args(argv)


def make_controller(view, opts):
    from .controller import Controller
    return Controller(view, demo=opts.demo, host=opts.host, port=opts.port,
                      local_port=opts.local_port, config=opts.config,
                      data_dir=opts.data_dir, tcp_port=opts.tcp_port or None,
                      tcp_host=opts.tcp_host)


class MemoryView:
    """Non-graphical adapter for deterministic integration checks."""
    def __init__(self):
        self.values = {}
        self.attributes = {}
        self.panels = {}
        self.panel_attributes = {}
        self.menu_attributes = {}
        self.messages = []
        spec_path = Path(__file__).with_name("resources") / "gui_spec.json"
        if spec_path.exists():
            spec = json.loads(spec_path.read_text())
            for panel in spec.get("panels", []):
                for control in panel.get("controls", []):
                    attrs = control.get("attributes", {})
                    runtime_id = control.get("runtime_id", control.get("local_index", control["id"] - 1) + 1)
                    self.values[panel["id"], runtime_id] = attrs.get("value", control.get("value", 0))

    def read(self, panel, control):
        return self.values.get((panel, control), 0)

    def set_value(self, panel, control, value):
        self.values[panel, control] = value

    def set_attribute(self, panel, control, attribute, value):
        self.attributes[panel, control, attribute] = value

    def set_panel_attribute(self, panel, attribute, value):
        self.panel_attributes[panel, attribute] = value

    def set_menu_attribute(self, panel, item, attribute, value):
        self.menu_attributes[panel, item, attribute] = value

    def show_panel(self, panel, visible=True):
        self.panels[panel] = visible

    def log(self, text):
        self.messages.append(text)


def main(argv=None):
    opts = arguments(argv)
    if opts.headless:
        view = MemoryView()
        controller = make_controller(view, opts)
        try:
            controller.start()
            deadline = time.monotonic() + opts.duration
            while controller.running and time.monotonic() < deadline:
                controller.tick()
                time.sleep(0.002)
            print(json.dumps({"mode": "simulator" if opts.demo else "instrument",
                              "connected": bool(controller.state.get("connected", False)),
                              "events": len(controller.events),
                              "controls_updated": len(controller.values),
                              "pending": len(controller.scheduler.inside) + len(controller.scheduler.outside)},
                             ensure_ascii=False))
        finally:
            controller.stop()
        return 0
    native_available = sys.platform == "win32" and struct.calcsize("P") == 4
    if opts.backend == "native" or (opts.backend == "auto" and native_available):
        from .native import run
        return run(opts)
    if opts.render_dir:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit("Qt GUI requires: python -m pip install PySide6\n"
                         "Original NI GUI: run with 32-bit Windows Python --backend native") from exc
    from .gui import SpitfireWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Spitfire")
    window = SpitfireWindow()
    controller = make_controller(window, opts)
    window.callback.connect(controller.handle_callback)
    window.key_pressed.connect(controller.key_pressed)
    if hasattr(window, "closing"):
        window.closing.connect(controller.stop)
    if hasattr(window, "mouse_released"):
        window.mouse_released.connect(controller.mouse_released)
    app.aboutToQuit.connect(controller.stop)
    window.show()
    if opts.demo:
        window.setWindowTitle(window.windowTitle() + " [DEMO]")
    timer = QTimer(app)
    timer.timeout.connect(controller.tick)
    timer.start(10)
    QTimer.singleShot(0, controller.start)
    if opts.render_dir:
        def render():
            opts.render_dir.mkdir(parents=True, exist_ok=True)
            for panel_id, widget in window.panels.items():
                widget.grab().save(str(opts.render_dir / f"panel_{panel_id}.png"))
            app.quit()
        QTimer.singleShot(max(100, int(opts.duration * 1000)), render)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

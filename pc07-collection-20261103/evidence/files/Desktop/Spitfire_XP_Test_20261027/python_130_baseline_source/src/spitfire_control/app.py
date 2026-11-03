"""Application entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk

from .config import AppConfig
from .ui import SpitfireApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spitfire Python Control")
    transport_group = parser.add_mutually_exclusive_group()
    transport_group.add_argument("--simulator", action="store_true", help="force the safe in-process simulator")
    transport_group.add_argument("--udp", action="store_true", help="select the UDP hardware transport")
    parser.add_argument("--pump-mode", choices=("empower", "external"),
                        help="select the pump configuration independently of simulator/UDP")
    parser.add_argument("--host", help="override remote controller host")
    parser.add_argument("--remote-port", type=int, help="override remote UDP port")
    parser.add_argument("--local-port", type=int, help="override local UDP bind port")
    parser.add_argument("--self-test-report", type=Path,
                        help="run isolated simulator GUI checks, save JSON and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test_report is not None:
        if args.udp or args.host is not None or args.remote_port is not None or args.local_port is not None:
            parser.error("--self-test-report permits simulator mode only; no UDP options")
        # Branch before config.load(), Tk/operator setup or any device access.
        from .validation_worker import gui_probe, write_result
        output = args.self_test_report.expanduser().resolve()
        return write_result(output, lambda: gui_probe(output.parent, pump_mode=args.pump_mode or "empower"))
    config = AppConfig.load()
    if args.simulator:
        config.mode = "simulator"
    if args.udp:
        config.mode = "udp"
    if args.pump_mode is not None:
        config.pump_mode = args.pump_mode
    if args.host:
        config.remote_host = args.host
    if args.remote_port is not None:
        config.remote_port = args.remote_port
    if args.local_port is not None:
        config.local_port = args.local_port
    root = tk.Tk()
    SpitfireApp(root, config)
    root.mainloop()
    return 0

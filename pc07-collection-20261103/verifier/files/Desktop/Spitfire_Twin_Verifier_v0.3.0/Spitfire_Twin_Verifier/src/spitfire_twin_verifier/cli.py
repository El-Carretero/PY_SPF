"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time

from . import __version__
from .compare import compare_transactions
from .config import AppConfig
from .demo import run_loopback_demo
from .model import VirtualSpitfire
from .network import validate_ipv4
from .records import CaptureStore
from .report import write_report
from .server import VirtualDeviceServer


def self_test(output: Path | None = None) -> int:
    capture = CaptureStore()
    original, python = "XP Original 1.6.0", "Python 1.1.3"
    run_loopback_demo(capture, original, python)
    result = compare_transactions(capture.snapshot(), original, python, ignore_polling=True)
    required = len(capture.transactions()) == 18 and result.verdict == "MATCH" and result.differences == 0
    if output is not None:
        directory = write_report(output, result, capture, {"mode": "loopback self-test"})
        print(f"Report: {directory}")
    print(json.dumps({
        "version": __version__, "transactions": len(capture.transactions()),
        "verdict": result.verdict, "similarity": result.sequence_similarity,
        "differences": result.differences, "status": "PASS" if required else "FAIL",
    }, ensure_ascii=False, indent=2))
    return 0 if required else 1


def headless(args) -> int:
    bind_ip = validate_ipv4(args.bind, field="bind")
    original_ip = validate_ipv4(args.original_ip, field="original-ip")
    python_ip = validate_ipv4(args.python_ip, field="python-ip")
    if original_ip == python_ip or args.original_label == args.python_label:
        raise ValueError("XP/Python addresses and labels must be distinct")
    capture = CaptureStore()
    device = VirtualSpitfire(isolated_clients=not args.shared_state)
    labels = {original_ip: args.original_label, python_ip: args.python_label}
    server = VirtualDeviceServer(bind_ip, args.port, device, capture, labels)
    if args.scenario:
        server.set_scenario(args.scenario, clock='realtime')
    stop = threading.Event()

    def handle_signal(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)
    server.start()
    print(f"Virtual Spitfire: {server.local_address[0]}:{server.local_address[1]}")
    print(f"Original: {original_ip} -> {args.original_label}")
    print(f"Python:   {python_ip} -> {args.python_label}")
    print("Press Ctrl+C to stop and create a report.")
    try:
        while not stop.wait(0.5):
            pass
    finally:
        server.stop()
    result = compare_transactions(capture.snapshot(), args.original_label, args.python_label,
                                  ignore_polling=not args.include_polling)
    directory = write_report(Path(args.output), result, capture, {
        "mode": "headless", "virtual_device": f"{bind_ip}:{args.port}",
        "original_client_ip": original_ip, "python_client_ip": python_ip,
    })
    print(f"Report: {directory}")
    return 0 if result.verdict == "MATCH" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Virtual Spitfire and differential verifier")
    parser.add_argument("--version", action="version", version=__version__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", help="run without the Tk GUI")
    mode.add_argument("--self-test", action="store_true", help="run a loopback demo acceptance test")
    mode.add_argument("--list-profiles", action="store_true")
    mode.add_argument("--list-scenarios", action="store_true")
    mode.add_argument("--inspect-client", metavar="ZIP_OR_FOLDER")
    mode.add_argument("--run-scenario", metavar="NAME_OR_JSON")
    mode.add_argument("--scenario-suite", action="store_true", help="all bundled synthetic model assertions, not client parity")
    mode.add_argument("--matrix", nargs='+', metavar="ZIP_OR_FOLDER", help="explicitly execute trusted Python client transport on loopback")
    mode.add_argument("--compare-capture", metavar="CAPTURE_JSONL", help="offline comparison of saved session")
    mode.add_argument("--replay-capture", metavar="CAPTURE_JSONL", help="strict passive loopback response replay")
    parser.add_argument("--replay-label", default=None)
    parser.add_argument("--duration", type=float, default=60.0, help="replay server lifetime seconds")
    parser.add_argument("--scenario", help="live headless synthetic scenario, realtime from each client's first request")
    parser.add_argument("--python-executable", help="Python interpreter for explicit imported-code matrix execution")
    parser.add_argument("--trust-client-code", action="store_true", help="consent to execute selected Python code; subprocess is not a security sandbox")
    parser.add_argument("--reaction-rules", help="JSON reaction rules, evaluated against saved capture")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1024)
    parser.add_argument("--original-ip", default="10.19.70.2")
    parser.add_argument("--python-ip", default="10.19.70.1")
    parser.add_argument("--original-label", default="XP Original 1.6.0")
    parser.add_argument("--python-label", default="Python 1.3.0")
    parser.add_argument("--shared-state", action="store_true", help="share mutable state between clients")
    parser.add_argument("--include-polling", action="store_true")
    parser.add_argument("--output", default="verification_reports")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    from .profiles import list_profiles, inspect_client
    from .scenarios import list_scenarios, run_scenario
    payload = None
    if args.list_profiles:
        payload = list_profiles()
    elif args.list_scenarios:
        payload = list_scenarios()
    elif args.inspect_client:
        payload = inspect_client(args.inspect_client)
    elif args.run_scenario:
        payload = run_scenario(args.run_scenario)
    elif args.scenario_suite:
        payload = {'scope': 'synthetic model assertions only',
                   'client_equivalence': 'UNVERIFIED', 'physical_validation': 'UNVERIFIED',
                   'results': [run_scenario(s['id']) for s in list_scenarios()]}
    elif args.matrix:
        from .client_matrix import run_matrix
        kwargs = {'output_dir': Path(args.output), 'trusted': args.trust_client_code}
        if args.python_executable:
            kwargs['python_executable'] = args.python_executable
        payload = run_matrix(args.matrix, **kwargs)
    elif args.compare_capture:
        from .evidence import load_capture, assess_reactions
        capture = load_capture(args.compare_capture)
        result = compare_transactions(capture, args.original_label, args.python_label,
                                      ignore_polling=not args.include_polling)
        payload = {'comparison': result.to_dict(),
                   'report_directory': str(write_report(Path(args.output), result, capture))}
        if args.reaction_rules:
            rules = json.loads(Path(args.reaction_rules).read_text(encoding='utf-8'))
            payload['reactions'] = [assess_reactions(capture, rules, label)
                                    for label in (args.original_label, args.python_label)]
    elif args.replay_capture:
        import math
        from .evidence import load_capture
        from .replay import ReplayServer
        if not math.isfinite(args.duration) or not 0 < args.duration <= 3600:
            raise ValueError('--duration must be >0 and <=3600 seconds')
        capture = load_capture(args.replay_capture)
        if not args.replay_label:
            raise ValueError('--replay-label is required (select original captured client)')
        with ReplayServer(capture, args.replay_label, bind_ip=args.bind, bind_port=args.port) as replay:
            print(f'Passive fixture replay at {replay.local_address}; no requests sent to hardware', flush=True)
            try:
                threading.Event().wait(args.duration)
            except KeyboardInterrupt:
                pass
        payload = replay.status()
    if payload is not None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.run_scenario or args.scenario_suite or args.matrix or args.compare_capture:
            from .evidence_report import write_workbench_report
            output = write_workbench_report(args.output, payload)
            print(f'Report: {output}')
        # A completed operation is not by itself PASS. Report-specific status
        # is surfaced as a process failure for automation where available.
        statuses = [payload] if isinstance(payload, dict) else []
        statuses += payload.get('results', []) if isinstance(payload, dict) else []
        verdicts = [s.get('status', s.get('model_verdict', s.get('verdict'))) for s in statuses if isinstance(s, dict)]
        if args.compare_capture:
            verdicts.append(payload['comparison']['verdict'])
            verdicts.extend(r.get('status', r.get('verdict')) for r in payload.get('reactions', []))
        if any(v in {'FAIL', 'ERROR', 'DIFFERENT'} for v in verdicts):
            return 1
        if any(v in {'INCOMPLETE', 'UNVERIFIED', 'UNSUPPORTED', 'OBSERVATION_REQUIRED'} for v in verdicts):
            return 2
        return 0
    if args.self_test:
        return self_test(Path(args.output))
    if args.headless:
        return headless(args)
    from .app import launch
    launch(AppConfig.load())
    return 0

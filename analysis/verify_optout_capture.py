"""Replay sanitized original Opt-out capture without opening network sockets.

Run from the repository root:
    python analysis/verify_optout_capture.py --native-oracle
The optional oracle runs original x86 instructions in Unicorn, with CVI/CRT
calls intercepted. It never launches the EXE or loads an NI DLL.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.decoders import ResponseDecoder
from spitfire.protocol import parse_datagram
from spitfire.scheduling import Request, Scheduler

FIXTURE = ROOT / "analysis" / "optout_post2_capture.json"


def load_capture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def verify_poll(capture):
    """Compare real observed query order/counts with the original poll builder."""
    scheduler = Scheduler(clock=lambda: 0)
    scheduler.queue_poll()
    generated = [request.tag for request in scheduler.outside]
    observed = capture["poll_command_tags"]
    assert len(generated) == len(observed) == 29
    rotations = [offset for offset in range(len(generated))
                 if generated[offset:] + generated[:offset] == observed]
    assert rotations, "Original poll sequence differs from the captured order"
    counts = Counter(observed)
    commands = [sample for sample in capture["samples"] if sample["kind"] == "command"]
    assert set(counts) == {sample["tag"] for sample in commands}
    cycle_count, remainder = divmod(capture["provenance"]["command_packets"], len(observed))
    assert remainder == 0
    for sample in commands:
        assert counts[sample["tag"]] * cycle_count == sample["count"]
    assert sum(sample["count"] for sample in commands) == capture["provenance"]["command_packets"]
    return {"cycle_queries": len(generated), "captured_cycles": cycle_count,
            "captured_queries": capture["provenance"]["command_packets"],
            "capture_rotation": rotations[0]}


def verify_command_bytes(capture):
    """Exercise Controller._send against actual captured UDP payload bytes."""
    class RecordingTransport:
        def __init__(self):
            self.packets = []

        def send_packet(self, payload):
            self.packets.append(payload)

    controller = Controller(MemoryView(), tcp_port=None, clock=lambda: 0)
    transport = RecordingTransport()
    controller.transport = transport
    compared = 0
    for sample in capture["samples"]:
        if sample["kind"] != "command":
            continue
        transport.packets.clear()
        controller._send(Request(sample["tag"]))
        assert transport.packets == [bytes.fromhex(sample["payload_hex"])], sample["tag"]
        compared += 1
    return {"exact_command_datagrams": compared}


def verify_responses(capture):
    """Decode real replies with the Opt-out state observed in process memory."""
    decoder = ResponseDecoder()
    decoder.state["emp_optout"] = capture["provenance"]["observed_emp_optout"]
    compared = 0
    raw_payloads = {}
    for sample in capture["samples"]:
        if sample["kind"] != "response":
            continue
        lines = parse_datagram(bytes.fromhex(sample["payload_hex"]), sample["seq"])
        assert len(lines) == 1
        assert lines[0].body.startswith(f"<{sample['tag']}>")
        raw_payloads[sample["tag"]] = lines[0].body.split(">", 1)[1]
        updates = decoder.decode_line(lines[0].decorated)
        assert updates
        assert ("connected", True) in decoder.effects
        compared += 1
    # Independent values in this capture: Opt-out and HV ON coexist. Retain
    # original -99 handling (diode current is scaled by 1/10), not normal zeros.
    assert decoder.state["emp_optout"] == 1
    assert raw_payloads[1021] == " 1"
    assert decoder.values[5, 34] == 1
    for tag in (1007, 1008, 1077):
        assert raw_payloads[tag] == "-99"
    assert decoder.values[9, 2] == -9.9
    assert decoder.values[9, 5] == decoder.values[8, 15] == -99.0
    assert decoder.values[6, 19] == 0  # Original opted-out Empower indicator.
    assert decoder.values[6, 13] == decoder.values[6, 16] == decoder.values[6, 17] == 1
    assert abs(decoder.values[2, 4] - 19.07) < 0.00001
    assert abs(decoder.values[2, 2] - 0.76) < 0.00001
    assert abs(decoder.values[2, 3] - 19.3) < 0.00001
    assert decoder.state["delay_monitor_status"] == 0
    return {"actual_reply_samples_decoded": compared, "observed_emp_optout": 1,
            "observed_hv_on": decoder.values[5, 34],
            "empower_sentinels_retained": True}


def verify_native(capture):
    """Compare captured reply values with the original decoder instructions."""
    sys.path.insert(0, str(ROOT / "analysis"))
    from native_decoder_oracle import compare

    original = ROOT / "analysis" / "reference" / "SPITFIRE.EXE"
    assert hashlib.sha256(original.read_bytes()).hexdigest() == capture["provenance"]["original_exe_sha256"]
    cases = []
    for sample in capture["samples"]:
        if sample["kind"] != "response":
            continue
        line = parse_datagram(bytes.fromhex(sample["payload_hex"]), sample["seq"])[0]
        payload = line.body.split(">", 1)[1]
        result = compare(sample["tag"], payload, state={"emp_optout": 1})
        assert result.get("pass"), result
        cases.append({"query": sample["tag"], "payload": payload, "pass": True})
    return {"method": "Original x86 decoder in Unicorn; CVI/CRT intercepted",
            "cases": cases, "passed": len(cases), "failed": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-oracle", action="store_true")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "analysis" / "optout_post2_replay_results.json")
    args = parser.parse_args(argv)
    capture = load_capture()
    with patch("socket.socket", side_effect=AssertionError("Replay must not open sockets")):
        result = {"fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                  "source_run": capture["source_run"], "network_sockets_blocked": True,
                  "poll": verify_poll(capture),
                  "wire": verify_command_bytes(capture),
                  "decoder": verify_responses(capture),
                  "native_oracle": verify_native(capture) if args.native_oracle else None,
                  "limits": capture["limits"]}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

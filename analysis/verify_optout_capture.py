"""Replay synthetic Opt-out protocol examples without opening network sockets.

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

FIXTURE = ROOT / "tests" / "fixtures" / "optout_protocol.json"


def load_capture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def verify_poll(capture):
    """Compare independent synthetic query order/counts with the recovered poll builder."""
    scheduler = Scheduler(clock=lambda: 0)
    scheduler.queue_poll()
    generated = [request.tag for request in scheduler.outside]
    observed = capture["poll_command_tags"]
    assert len(generated) == len(observed) == 29
    rotations = [offset for offset in range(len(generated))
                 if generated[offset:] + generated[:offset] == observed]
    assert rotations, "Recovered poll sequence differs from the independent example order"
    counts = Counter(observed)
    commands = [sample for sample in capture["samples"] if sample["kind"] == "command"]
    assert set(counts) == {sample["tag"] for sample in commands}
    cycle_count, remainder = divmod(capture["provenance"]["command_packets"], len(observed))
    assert remainder == 0
    for sample in commands:
        assert counts[sample["tag"]] * cycle_count == sample["count"]
    assert sum(sample["count"] for sample in commands) == capture["provenance"]["command_packets"]
    return {"cycle_queries": len(generated), "example_cycles": cycle_count,
            "generated_queries": capture["provenance"]["command_packets"],
            "example_rotation": rotations[0]}


def verify_command_bytes(capture):
    """Exercise Controller._send against static synthetic UDP payload bytes."""
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
    """Decode synthetic replies with an explicitly supplied Opt-out state."""
    decoder = ResponseDecoder()
    decoder.state["emp_optout"] = capture["provenance"]["emp_optout"]
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
    # Synthetic inputs exercise Opt-out with an HV ON readback. Retain
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
    assert abs(decoder.values[2, 4] - 21.25) < 0.00001
    assert abs(decoder.values[2, 2] - 12.5) < 0.00001
    assert abs(decoder.values[2, 3] - 20.5) < 0.00001
    assert decoder.state["delay_monitor_status"] == 0
    return {"example_reply_samples_decoded": compared, "configured_emp_optout": 1,
            "example_hv_on": decoder.values[5, 34],
            "empower_sentinels_retained": True}


def verify_native(capture):
    """Compare synthetic reply values with the original decoder instructions."""
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
                        default=ROOT / "analysis" / "optout_protocol_verification.json")
    args = parser.parse_args(argv)
    capture = load_capture()
    with patch("socket.socket", side_effect=AssertionError("Replay must not open sockets")):
        result = {"fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                  "fixture_kind": capture["fixture_kind"], "fixture_name": capture["fixture_name"], "network_sockets_blocked": True,
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

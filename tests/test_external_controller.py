"""Exercise the independent controller through its simulated wire boundary.

No test opens an instrument socket. Fault injection changes replies and device
readbacks, rather than asserting a particular internal queue implementation.
"""
from __future__ import annotations

import re
import select
import socket

import pytest

from spitfire.__main__ import MemoryView
from spitfire.callbacks import Action
from spitfire.controller import Controller
from spitfire.protocol import COMMANDS, PACKET_PREFIX, UDPTransport
from spitfire.simulator import SimulatedTransport


def packet_requests(packet):
    for line in packet[len(PACKET_PREFIX):].decode("ascii").splitlines():
        match = re.fullmatch(r"\[(\d+)\](.*)", line)
        assert match, line
        tag, text = int(match[1]), match[2]
        parameter = text[len(COMMANDS[tag]):] if tag in COMMANDS else ""
        yield tag, " ".join(parameter.upper().split()), text


def wire_requests(controller):
    return [request for packet in controller.transport.sent_packets
            for request in packet_requests(packet)]


def wire_writes(controller):
    return [(tag, parameter) for tag, parameter, _ in wire_requests(controller)
            if tag >= 2000]


class FaultInstrument(SimulatedTransport):
    """A controller with no Empower and optional delayed/mismatched PC replies."""
    fault = None

    def __init__(self):
        super().__init__()
        for name in list(self.values):
            if name.startswith(("EMP:", "MIL:")):
                del self.values[name]
        self.run_requested = False
        self.failed_first_off = False
        self.stale_readback_queued = False

    def send_packet(self, packet):
        requests = list(packet_requests(packet))
        assert all(not text.upper().startswith(("EMP:", "MIL:"))
                   for _, _, text in requests)
        before = len(self.pending)
        super().send_packet(packet)
        for tag, parameter, _ in requests:
            if (tag, parameter) == (2019, "2 ON"):
                self.run_requested = True
                if self.fault in ("mismatch_pc2", "stale_pc2"):
                    self.values["TDG:DEL2?"] = self.values["TDG:DEL2?"].replace(" ON ", " OFF ")
                if self.fault == "stale_pc2":
                    # An old valid-looking response is already behind the ACK
                    # before the new readback request has even been sent.
                    self.pending.append(b"Spectra-Physics:REPLY_ECLIPSE:<1046>DELAY 2 ON BWD ENA 200\n")
                    self.stale_readback_queued = True
            suppress = (self.fault == "missing_pc2" and self.run_requested and tag == 1046)
            if self.fault == "empty_pc2" and self.run_requested and tag == 1046 and len(self.pending) > before:
                self.pending[-1] = re.sub(rb"(<1046>)[^\r\n]*", rb"\1", self.pending[-1])
            if self.fault == "first_off_timeout" and (tag, parameter) == (2019, "1 OFF") and not self.failed_first_off:
                self.failed_first_off = True
                suppress = True
            if suppress:
                while len(self.pending) > before:
                    self.pending.pop()


@pytest.fixture
def app_factory(monkeypatch):
    created = []

    def make(*, hv_on=True, fault=None, opt_out=True):
        class Instrument(FaultInstrument):
            pass
        Instrument.fault = fault
        monkeypatch.setattr("spitfire.controller.SimulatedTransport", Instrument)
        now = [1.0]
        app = Controller(MemoryView(), demo=True, tcp_port=None,
                         clock=lambda: now[0], request_timeout=0.2)
        created.append(app)
        app.start()
        app.transport.values["TDG:HV:ON?"] = "1" if hv_on else "0"
        if hv_on:
            app.transport.values["TDG:READ:HV1VOLT?"] = "1200"
            app.transport.values["TDG:READ:HV2VOLT?"] = "1200"
        app.transport.values["EMPOPTOUT?"] = "1" if opt_out else "0"
        return app, now

    yield make
    for app in created:
        app.stop()


def tick_until(app, now, condition, *, limit=2000, step=0.005):
    for _ in range(limit):
        app.tick()
        if condition():
            return
        now[0] += step
    pytest.fail("condition was not reached; recent events: " + repr(list(app.events)[-12:]))


def make_ready(app, now):
    tick_until(app, now, lambda: app.state.get("connected") and
               not app.decoder.readbacks.gate_reason(now[0], require_off=True))


def test_startup_and_poll_are_read_only_without_any_empower_response(app_factory):
    app, now = app_factory()
    make_ready(app, now)
    for _ in range(400):
        app.tick()
        now[0] += 0.005
    assert app.state["connected"]
    assert not wire_writes(app)
    assert all(not text.upper().startswith(("EMP:", "MIL:"))
               for _, _, text in wire_requests(app))
    assert app.decoder.readbacks.value(1068) == 1


def test_stop_during_lost_identity_handshake_sends_off_without_startup_wait(app_factory):
    app, now = app_factory(hv_on=False)
    app.transport.pending.clear()  # Drop the first identity response.
    assert not app.startup.complete
    assert not app.startup.received
    assert app.scheduler.hold
    requested_at = now[0]
    app.request_pc_stop()
    tick_until(app, now, lambda: (2019, "2 OFF") in wire_writes(app), limit=10)
    assert now[0] - requested_at < 0.1
    assert app.startup.complete
    assert not app.scheduler.hold
    assert wire_writes(app)[:2] == [(2019, "1 OFF"), (2019, "2 OFF")]
    assert sum(tag == 1000 for tag, _, _ in wire_requests(app)) == 1


def test_empower_and_raw_callbacks_cannot_reach_the_wire(app_factory):
    app, now = app_factory()
    make_ready(app, now)
    for name in ("slidesetcurr", "slideqswprf", "LBOstabilitybreak", "secretcall1"):
        app.handle_callback(name, 1, event=1)
    app.view.values[6, 59] = "[2005]EMP:ON\n[2027]ON"
    app.handle_callback("strnsendcllback", event=1)
    app.apply([Action("command", 2044), Action("command", 2027)])
    for _ in range(100):
        app.tick()
        now[0] += 0.005
    assert not wire_writes(app)


def test_reset_and_escape_only_use_independent_commands(app_factory):
    app, now = app_factory(hv_on=False)
    tick_until(app, now, lambda: app.decoder.readbacks.is_fresh(1068, now[0])
               and app.decoder.readbacks.is_fresh(1021, now[0]))
    app.handle_callback("cllbckcmd_reset", event=1)
    tick_until(app, now, lambda: (2050, "") in wire_writes(app))
    assert [tag for tag, _ in wire_writes(app)] == [2049, 2052, 2050]
    app.key_pressed("\x1b")
    tick_until(app, now, lambda: (2019, "2 OFF") in wire_writes(app))
    assert (2019, "1 OFF") in wire_writes(app)
    assert all(tag not in (2044, 2027, 2028) for tag, _ in wire_writes(app))


def test_optout_is_explicit_only_and_rechecked_before_sending(app_factory):
    app, now = app_factory(hv_on=False, opt_out=False)
    tick_until(app, now, lambda: app.decoder.readbacks.is_fresh(1068, now[0])
               and app.decoder.readbacks.is_fresh(1021, now[0]))
    assert not wire_writes(app)
    app.handle_callback("apply_external_optout", event=1)
    # Device HV changed after click but before the next dispatch.
    app.decoder.readbacks.update(1021, "1", now[0])
    app.transport.values["TDG:HV:ON?"] = "1"
    for _ in range(100):
        app.tick()
        now[0] += 0.005
    assert (2036, "1") not in wire_writes(app)
    app.handle_callback("empoweroptoutcall", 0, event=1, panel=2, control=9)
    assert (2036, "0") not in wire_writes(app)
    app.transport.values["TDG:HV:ON?"] = "0"
    tick_until(app, now, lambda: app.decoder.readbacks.value(1021) == 0)
    app.handle_callback("apply_external_optout", event=1)
    tick_until(app, now, lambda: (2036, "1") in wire_writes(app))
    assert all(tag == 2036 for tag, _ in wire_writes(app))


def test_three_second_hold_runs_pc2_then_confirms_before_pc1(app_factory):
    app, now = app_factory()
    make_ready(app, now)
    app.events.clear()
    app.handle_callback("cllbck", event=3, panel=6, control=10)
    started = now[0]
    while now[0] - started < 2.99:
        app.tick()
        now[0] += 0.01
    assert not wire_writes(app)
    tick_until(app, now, lambda: (2019, "1 ON") in wire_writes(app))
    writes = wire_writes(app)
    assert writes[:2] == [(2019, "2 ON"), (2019, "1 ON")]
    events = list(app.events)
    first_on = next(i for i, (_, kind, text) in enumerate(events)
                    if kind == "TX" and "2 ON" in str(text).upper())
    second_on = next(i for i, (_, kind, text) in enumerate(events)
                     if kind == "TX" and "1 ON" in str(text).upper())
    assert any(kind == "RX" and "<1046>" in str(text) and " ON " in str(text).upper()
               for _, kind, text in events[first_on + 1:second_on])


def test_stop_between_pc_steps_cancels_remaining_on(app_factory):
    app, now = app_factory()
    make_ready(app, now)
    app.request_pc_run()
    tick_until(app, now, lambda: (2019, "2 ON") in wire_writes(app))
    boundary = len(wire_writes(app))
    app.request_pc_stop()
    tick_until(app, now, lambda: (2019, "2 OFF") in wire_writes(app)[boundary:])
    assert (2019, "1 ON") not in wire_writes(app)[boundary:]
    assert (2019, "1 OFF") in wire_writes(app)[boundary:]


@pytest.mark.parametrize("channel", [3, 4, 5])
def test_other_channel_on_cannot_interleave_pc_run(app_factory, channel):
    app, now = app_factory()
    make_ready(app, now)
    app.request_pc_run()
    app.handle_callback(f"swChannelEnableCallback_btn{channel}", 1, event=1)
    tick_until(app, now, lambda: app.run_status.startswith("PC RUN confirmed"))
    assert wire_writes(app) == [(2019, "2 ON"), (2019, "1 ON")]


def test_user_pc2_on_cannot_duplicate_the_pending_owned_run_step(app_factory):
    app, now = app_factory()
    make_ready(app, now)
    app.request_pc_run()
    # The sequence owns one queued PC2 ON. A separate UI click must neither
    # duplicate it nor turn its later rejection into an aborted valid RUN.
    app.handle_callback("swChannelEnableCallback_btn2", 1, event=1)
    tick_until(app, now, lambda: app.run_status.startswith("PC RUN confirmed"))
    assert wire_writes(app) == [(2019, "2 ON"), (2019, "1 ON")]


def test_prequeued_pc2_on_reply_cannot_confirm_a_new_readback(app_factory):
    app, now = app_factory(fault="stale_pc2")
    make_ready(app, now)
    app.request_pc_run()
    tick_until(app, now, lambda: (2019, "2 OFF") in wire_writes(app))
    assert app.transport.stale_readback_queued
    assert (2019, "1 ON") not in wire_writes(app)
    assert (2019, "1 OFF") in wire_writes(app)


@pytest.mark.parametrize("fault", ["missing_pc2", "mismatch_pc2", "empty_pc2"])
def test_unconfirmed_pc2_never_enables_pc1_and_attempts_both_off(app_factory, fault):
    app, now = app_factory(fault=fault)
    make_ready(app, now)
    app.request_pc_run()
    tick_until(app, now, lambda: (2019, "2 OFF") in wire_writes(app))
    writes = wire_writes(app)
    assert (2019, "2 ON") in writes
    assert (2019, "1 ON") not in writes
    assert (2019, "1 OFF") in writes
    assert writes.count((2019, "2 ON")) == 1


def test_first_off_timeout_does_not_prevent_second_off(app_factory):
    app, now = app_factory(fault="first_off_timeout")
    make_ready(app, now)
    app.request_pc_stop()
    tick_until(app, now, lambda: (2019, "2 OFF") in wire_writes(app))
    assert wire_writes(app)[:2] == [(2019, "1 OFF"), (2019, "2 OFF")]
    assert app.transport.failed_first_off


def test_connection_recovery_does_not_discard_pc_cleanup(app_factory):
    app, now = app_factory()
    make_ready(app, now)
    app.request_pc_run()
    tick_until(app, now, lambda: app.run_status.startswith("PC RUN confirmed"))
    old_transport = app.transport
    boundary = len(old_transport.sent_packets)
    old_transport.pending.clear()
    now[0] += 11.0  # Event-loop stall plus loss of the outstanding reply.

    def recovery_writes():
        packets = old_transport.sent_packets[boundary:]
        if app.transport is not old_transport:
            packets = packets + app.transport.sent_packets
        return [(tag, parameter) for packet in packets
                for tag, parameter, _ in packet_requests(packet) if tag >= 2000]

    tick_until(app, now, lambda: (2019, "2 OFF") in recovery_writes())
    assert (2019, "1 OFF") in recovery_writes()
    assert all(parameter not in ("1 ON", "2 ON") for _, parameter in recovery_writes())


def test_udp_reply_from_unconfigured_sender_cannot_confirm_a_readback():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as device, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
        device.bind(("127.0.0.1", 0))
        other.bind(("127.0.0.1", 0))
        transport = UDPTransport("localhost", device.getsockname()[1], bind_port=0, timeout=0.2)
        try:
            transport.open()
            destination = ("127.0.0.1", transport.socket.getsockname()[1])
            frame = b"Spectra-Physics:REPLY_ECLIPSE:<1046>DELAY 2 ON BWD ENA 200\n"
            other.sendto(frame, destination)
            assert transport.receive() == []
            device.sendto(frame, destination)
            replies = transport.receive()
            assert len(replies) == 1
            assert "<1046>DELAY 2 ON BWD ENA 200" in replies[0].decorated
        finally:
            transport.close()


def test_udp_drain_discards_old_peer_packets_and_restores_timeout():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as device:
        device.bind(("127.0.0.1", 0))
        transport = UDPTransport("127.0.0.1", device.getsockname()[1], bind_port=0, timeout=0.03)
        try:
            transport.open()
            destination = ("127.0.0.1", transport.socket.getsockname()[1])
            device.sendto(b"Spectra-Physics:REPLY_ECLIPSE:<1046>DELAY 2 ON BWD ENA 200\n", destination)
            assert select.select([transport.socket], [], [], 0.2)[0]
            transport.discard_pending()
            assert transport.socket.gettimeout() == 0.03
            assert transport.receive() == []
            device.sendto(b"Spectra-Physics:REPLY_ECLIPSE:<1046>DELAY 2 OFF BWD ENA 200\n", destination)
            replies = transport.receive()
            assert len(replies) == 1
            assert "<1046>DELAY 2 OFF" in replies[0].decorated
        finally:
            transport.close()

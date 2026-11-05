"""Packaged check regressions using a memory adapter, never NI or a socket.

The adapter routes the real Native callback method and exposes test-controlled
bounds. These tests do not establish CVI rendering or Windows event delivery.
"""
import json

import pytest

from spitfire.__main__ import MemoryView
from spitfire.controller import Controller
from spitfire.native import NativeGui, RESOURCES
from spitfire.packaged_check import (
    _SimulatorWriteGuard,
    _exercise_external_shared_rate,
    _exercise_internal_10hz,
    _packet_messages,
    _trigger_observation,
)
from spitfire.protocol import PACKET_PREFIX
from spitfire.simulator import SimulatedTransport


class MemoryNativeAdapter(MemoryView):
    _control_event = NativeGui._control_event

    def __init__(self, *, divisor_ceiling=None):
        super().__init__()
        self.controller = None
        self._read_only_controls = set()
        self.bindings = json.loads((RESOURCES / "callback_bindings.json").read_text())
        self.bounds = {731: 10.0, 730: 10000.0}
        self.divisor_ceiling = divisor_ceiling
        self.processed_events = 0

    def read_attribute(self, panel, control, attribute):
        if (panel, control) == (5, 28) and attribute in self.bounds:
            return self.bounds[attribute]
        return self.attributes.get((panel, control, attribute), 0)

    def set_value(self, panel, control, value):
        if (panel, control) == (5, 43) and self.divisor_ceiling is not None:
            value = min(float(value), self.divisor_ceiling)
        super().set_value(panel, control, value)

    def process_events(self):
        self.processed_events += 1


class GuardedBoard(_SimulatorWriteGuard, SimulatedTransport):
    faulty_frequency = False

    def receive(self):
        replies = super().receive()
        if self.validation_phase not in ("internal-10hz", "external-shared-rate") or not self.faulty_frequency:
            return replies
        result = []
        for reply in replies:
            if not reply.body.startswith("<1053>"):
                result.append(reply)
            elif self.faulty_frequency != "drop":
                # Return the malformed/mismatching sample through the actual
                # protocol parser, preserving matching tag and packet identity.
                from spitfire.protocol import parse_datagram
                payload = self.faulty_frequency.removeprefix("payload:")
                packet = f"Spectra-Physics:REPLY_ECLIPSE:<1053>{payload}\n".encode("ascii")
                result.extend(parse_datagram(packet, self.packet_counter))
        return result


class FakeTicker:
    def __init__(self, controller, now):
        self.controller = controller
        self.now = now

    def tick(self):
        self.now[0] += 0.01
        self.controller.tick()

    def raise_if_failed(self):
        pass


@pytest.fixture
def simulation(monkeypatch):
    def forbidden_socket(*args, **kwargs):
        raise AssertionError("Packaged trigger unit tests must never create a socket")

    monkeypatch.setattr("socket.socket", forbidden_socket)
    now = [0.0]
    monkeypatch.setattr("spitfire.packaged_check.time.monotonic", lambda: now[0])
    monkeypatch.setattr("spitfire.packaged_check.time.sleep", lambda _: None)
    controllers = []

    def create(*, divisor_ceiling=None, alternate_baseline=False, preference=0):
        class Board(GuardedBoard):
            def __init__(self):
                super().__init__()
                if alternate_baseline:
                    self.values.update({"TDG:TRIG:MODE?": "EXT",
                                        "TDG:TRIG:FREQ?": "2500.000000",
                                        "TDG:DIV?": " 25.000000"})

        monkeypatch.setattr("spitfire.controller.SimulatedTransport", Board)
        view = MemoryNativeAdapter(divisor_ceiling=divisor_ceiling)
        view.values[6, 48] = preference
        controller = Controller(view, demo=True, tcp_port=None, clock=lambda: now[0])
        view.controller = controller
        controllers.append(controller)
        ticker = FakeTicker(controller, now)
        controller.start()
        for _ in range(2000):
            ticker.tick()
            if controller.state["gui_ready"]:
                break
        else:
            raise AssertionError("Simulator failed to finish genuine startup")
        return view, controller, ticker

    yield create
    for controller in controllers:
        controller.stop()


@pytest.mark.parametrize("options", [
    {},
    {"alternate_baseline": True, "preference": 1},
])
def test_real_controller_confirms_10hz_and_restores_fixture_and_memory_controls(simulation, options):
    view, controller, ticker = simulation(**options)
    board = controller.transport
    baseline_ui = _trigger_observation(view, controller)
    baseline_board = dict(board.values)
    preference = view.read(6, 48)
    original_receive = controller._receive
    startup = _packet_messages(board.sent_packets)
    assert [s for s in startup if int(s[1:s.index("]")]) >= 2000] == [
        "[2036]EMPOPTOUT 1", "[2047]EMP:LBOBREAK 1"]
    report = {}
    _exercise_internal_10hz(view, controller, ticker, report)

    result = report["internal_trigger_10hz"]
    confirmed = result["confirmed"]
    assert confirmed["mode_control"] == 0
    assert confirmed["frequency_control_hz"] == confirmed["int_pump_hz"] == 10
    assert confirmed["divisor_control"] == 1
    assert confirmed["int_amp_hz"] == 10
    assert confirmed["confirmation"] == {
        "internal_trigger_requested_hz": 10.0,
        "internal_trigger_actual_hz": 10.0,
        "internal_trigger_pending": False,
        "internal_trigger_confirmed": True,
        "internal_trigger_result": "confirmed",
    }
    assert {(sample["tag"], sample["payload"].strip()) for sample in result["matched_readbacks"]
            if sample["phase"] == "internal-10hz"} == {(1051, "INT"), (1053, "10.00"), (1025, "1.00")}
    assert result["restored_before_snapshot"] is True
    assert board.values == baseline_board
    restored = _trigger_observation(view, controller)
    assert {key: value for key, value in restored.items() if key != "confirmation"} == {
        key: value for key, value in baseline_ui.items() if key != "confirmation"}
    assert view.read(6, 48) == preference
    assert controller._receive == original_receive
    assert board.allowed_write_messages == frozenset()
    assert board.forbidden_write_attempts == []
    assert [item["message"] for item in board.write_audit if item["phase"] == "internal-10hz"] == [
        "[2031]TDG:TRIG:MODE INT", "[2032]TDG:TRIG:FREQ 10.00", "[2020]TDG:DIV  1.00"]
    assert [item["message"] for item in board.write_audit if item["phase"] == "restore-original"] == [
        "[2020]TDG:DIV %5.2f" % baseline_ui["divisor_control"],
        "[2032]TDG:TRIG:FREQ %5.2f" % baseline_ui["frequency_control_hz"],
        "[2031]TDG:TRIG:MODE " + ("EXT" if baseline_ui["mode_control"] else "INT")]
    assert result["windows_mouse_input_validated"] is False
    assert result["ni_event_delivery_validated"] is False
    assert view.processed_events > 0


def test_divisor_clamping_restores_derived_rate_after_final_frequency_readback(simulation):
    # This is an intentionally clamping memory adapter, not a claim about CVI.
    # Refresh frequency last so rates use the divisor the adapter actually read.
    view, controller, ticker = simulation(divisor_ceiling=100.0)
    original_board = dict(controller.transport.values)
    original_ui = _trigger_observation(view, controller)
    assert view.read(5, 43) == 100.0
    assert original_ui["int_amp_hz"] == 10.0
    assert float(original_board["TDG:DIV?"]) == 1000.0
    report = {}
    _exercise_internal_10hz(view, controller, ticker, report)
    result = report["internal_trigger_10hz"]
    assert result["restored_before_snapshot"] is True
    assert "restore_error" not in result
    assert {key: value for key, value in result["restored"].items() if key != "confirmation"} == {
        key: value for key, value in original_ui.items() if key != "confirmation"}
    assert result["restored"]["int_amp_hz"] == 10.0
    assert [sample["tag"] for sample in result["matched_readbacks"]
            if sample["phase"] == "restore-fixture-readback"] == [1025, 1051, 1053]
    assert controller.transport.values == original_board
    assert controller.transport.allowed_write_messages == frozenset()
    assert view.read(6, 48) == 0


@pytest.mark.parametrize("attribute,wrong_bound", [(731, 20.0), (730, 9999.0)])
def test_incorrect_memory_native_bound_fails_before_any_test_write(simulation, attribute, wrong_bound):
    view, controller, ticker = simulation()
    view.bounds[attribute] = wrong_bound
    board = controller.transport
    before = list(board.sent_packets)
    before_values = dict(board.values)
    with pytest.raises(AssertionError):
        _exercise_internal_10hz(view, controller, ticker, {})
    assert board.sent_packets == before
    assert board.values == before_values


@pytest.mark.parametrize("message", [
    "[2017]TDG:HV:ON", "[2027]ON", "[2005]EMP:ON",
    "[2999]UNEXPECTED", "[2032]TDG:TRIG:FREQ 100.00",
])
def test_write_guard_rejects_energizing_and_unexpected_requests_without_transmitting(message):
    board = GuardedBoard()
    before = dict(board.values)
    with pytest.raises(AssertionError, match="Unexpected self-test write"):
        board.send_packet(PACKET_PREFIX + message.encode("ascii") + b"\n")
    assert board.sent_packets == []
    assert not board.pending
    assert board.values == before
    assert board.forbidden_write_attempts == [message]


@pytest.mark.parametrize("fault", ["drop", "payload:invalid", "payload:", "payload:11.00"])
def test_missing_invalid_or_mismatched_frequency_response_cannot_pass_10hz_check(simulation, fault):
    view, controller, ticker = simulation()
    controller.query_timeout = 0.02
    controller.transport.faulty_frequency = fault
    report = {}
    with pytest.raises(AssertionError, match="Timed out waiting for matched INT/10Hz"):
        _exercise_internal_10hz(view, controller, ticker, report, timeout=0.3)
    result = report["internal_trigger_10hz"]
    assert "confirmed" not in result
    assert result["restored_before_snapshot"] is True
    assert controller.transport.forbidden_write_attempts == []
    if fault == "drop":
        assert controller.diagnostics["query_retries"] == 2
        assert controller.diagnostics["query_timeouts"] == 1
    elif fault == "payload:11.00":
        assert any(kind == "frequency" and "NOT confirmed" in message
                   for _, kind, message in controller.events)
    else:
        assert controller.diagnostics["internal_trigger_unconfirmed"] >= 1


@pytest.mark.parametrize("options", [{}, {"alternate_baseline": True, "preference": 1}])
def test_external_shared_rate_uses_confirmed_frequency_not_empower_or_oscillator(simulation, options):
    view, controller, ticker = simulation(**options)
    board = controller.transport
    baseline_ui = _trigger_observation(view, controller)
    baseline_board = dict(board.values)
    original_receive = controller._receive
    original_preference = view.read(6, 48)
    report = {}

    _exercise_external_shared_rate(view, controller, ticker, report)

    result = report["external_shared_rate"]
    assert result["simulator_only"] is True
    assert result["physical_device_io"] is False
    assert result["divisor_one"]["mode_control"] == 1
    assert result["divisor_one"]["frequency_control_hz"] == 10
    assert result["divisor_one"]["ext_pump_hz"] == result["divisor_one"]["ext_amp_hz"] == 10
    assert result["divisor_two"]["ext_pump_hz"] == 10
    assert result["divisor_two"]["ext_amp_hz"] == 5
    assert result["empower_reply_ignored"] is True
    assert result["oscillator_reply_ignored"] is True
    assert result["restored"] is True
    assert result["mode_write_commands"] == []
    assert result["target_write_messages"] == [
        "[2032]TDG:TRIG:FREQ 10.00", "[2020]TDG:DIV  1.00", "[2020]TDG:DIV  2.00"]
    assert result["windows_mouse_input_validated"] is False
    assert result["ni_event_delivery_validated"] is False
    assert board.values == baseline_board
    assert {key: value for key, value in _trigger_observation(view, controller).items()
            if key != "confirmation"} == {
        key: value for key, value in baseline_ui.items() if key != "confirmation"}
    assert view.read(6, 48) == original_preference
    assert controller._receive == original_receive
    assert board.allowed_write_messages == frozenset()
    assert board.forbidden_write_attempts == []


def test_external_rate_snapshot_is_taken_at_ten_hz_before_fixture_restoration(simulation, monkeypatch, tmp_path):
    view, controller, ticker = simulation()
    captured = []

    def capture(actual_view, path, *, panel=6):
        captured.append((panel, _trigger_observation(actual_view, controller)))
        path.write_bytes(b"BM simulator snapshot boundary")

    monkeypatch.setattr("spitfire.packaged_check._snapshot", capture)
    report = {}
    _exercise_external_shared_rate(view, controller, ticker, report,
                                   snapshot=tmp_path / "native-self-test.bmp")
    result = report["external_shared_rate"]
    assert result["snapshot"] == str(tmp_path / "native-self-test_external_rate.bmp")
    assert len(captured) == 1 and captured[0][0] == 6
    assert captured[0][1]["mode_control"] == 1
    assert captured[0][1]["ext_pump_hz"] == captured[0][1]["ext_amp_hz"] == 10
    assert result["restored"] is True


@pytest.mark.parametrize("fault", ["drop", "payload:invalid", "payload:", "payload:11.00"])
def test_external_phase_rejects_unconfirmed_frequency_without_mode_or_hv_writes(simulation, fault):
    view, controller, ticker = simulation()
    board = controller.transport
    original_board = dict(board.values)
    controller.query_timeout = 0.02
    board.faulty_frequency = fault
    report = {}
    with pytest.raises(AssertionError, match="Timed out waiting for matched EXT/10Hz"):
        _exercise_external_shared_rate(view, controller, ticker, report, timeout=0.3)
    result = report["external_shared_rate"]
    assert "divisor_one" not in result
    assert result["restored"] is True
    assert board.values == original_board
    assert result["mode_write_commands"] == []
    assert board.forbidden_write_attempts == []

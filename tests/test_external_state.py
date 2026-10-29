"""External eligibility is based on current board facts, never absent pump data."""
import pytest

from spitfire.external_state import ExternalReadbacks, ExternalResponseDecoder, REQUIRED_IDS
from spitfire.protocol import PACKET_PREFIX, QUERIES
from spitfire.simulator import SimulatedTransport


def fixture(*, hv_on=True, now=10.0):
    transport = SimulatedTransport()
    if hv_on:
        transport._command(2017, "TDG:HV:ON", "")
    facts = ExternalReadbacks()
    for tag in REQUIRED_IDS + (1042, 1043):
        assert facts.update(tag, transport.values[QUERIES[tag].upper()], now)
    return facts, transport


def test_no_empower_device_is_needed_but_real_optout_is_required():
    facts, transport = fixture()
    assert not any(name.startswith("EMP:") for name in transport.values)
    assert facts.value(1089) == 4  # Pump communication is absent, not forged healthy.
    assert facts.run_block_reason(10) == ""
    facts.update(1068, "0", 10)
    assert "opt-out" in facts.run_block_reason(10)
    facts.invalidate(1068)
    assert facts.run_block_reason(10)


def test_hv_enable_is_separate_from_pc_run():
    facts, _ = fixture(hv_on=False)
    assert facts.enable_block_reason(10) == ""
    assert facts.hv_off_reason(10) == ""
    assert "HV already ON" in facts.run_block_reason(10)
    facts.update(1021, "1", 10)
    assert "positive measured" in facts.run_block_reason(10)


@pytest.mark.parametrize("tag,payload", [
    (1021, ""), (1021, "2"), (1042, "NaN"), (1042, "1 broken"),
    (1065, "inf"), (1019, "0 trailing"), (1019, "-1"),
    (1039, "0000 invalid"), (1089, "0.5"),
    (1045, "DELAY 2 OFF BWD ENA 100"),
    (1045, "100"), (1045, "DELAY 1 OFF BWD ENA NaN"),
])
def test_malformed_required_readback_invalidates_previous_fact(tag, payload):
    facts, _ = fixture()
    assert facts.is_fresh(tag, 10)
    assert not facts.update(tag, payload, 10.1)
    assert not facts.is_fresh(tag, 10.1)
    assert facts.run_block_reason(10.1)


@pytest.mark.parametrize("tag,payload", [
    (1039, "4000"), (1039, "10000"), (1066, "1000"),
    (1088, "4"), (1089, "5"), (1089, "20"),
    (1019, "2048"), (1028, "2048"), (1015, "2048"),
    (1087, "1"), (1044, "1"), (1033, "1"), (1069, "1"),
    (1050, "INT"), (1051, "INT"), (1065, "0"),
    (1045, "DELAY 1 OFF NBWD ENA 100"),
    (1046, "DELAY 2 OFF BWD NENA 100"),
])
def test_every_protection_failure_blocks_output(tag, payload):
    facts, _ = fixture()
    assert facts.update(tag, payload, 10)
    assert facts.enable_block_reason(10)


def test_stale_data_and_reconnect_cannot_reuse_good_observations():
    facts, _ = fixture()
    assert facts.run_block_reason(15) == ""
    assert facts.run_block_reason(15.01)
    facts.clear()
    assert facts.run_block_reason(10)
    assert facts.channel_on(1, 10) is None


def test_pc_sequence_checks_live_channels_without_requiring_both_off_mid_run():
    facts, _ = fixture()
    facts.update(1046, "DELAY 2 ON BWD ENA 200", 10)
    assert facts.channel_on(2, 10) is True
    assert facts.run_block_reason(10)
    assert facts.gate_reason(10, require_off=False) == ""
    facts.update(1046, "ERROR", 10.1)
    assert facts.channel_on(2, 10.1) is None
    assert facts.gate_reason(10.1, require_off=False)


def test_invalid_alias_cannot_keep_canonical_readback_fresh():
    facts, _ = fixture()
    assert not facts.update(1061, "", 10.1)
    assert not facts.is_fresh(1021, 10.1)
    assert facts.run_block_reason(10.1)


def test_delayed_ack_is_not_a_readback_or_a_connectivity_fact():
    facts = ExternalReadbacks()
    assert not facts.update(2019, "ACK", 10)
    assert not facts.link_fresh(10)
    assert facts.channel_on(1, 10) is None


def test_independent_decoder_never_autowrites_or_reads_empower_panels():
    def read(panel, control):
        assert panel not in (8, 9)
        return 0
    decoder = ExternalResponseDecoder(read=read, clock=lambda: 10)
    for tag, payload in [(1067, "EXT"), (1068, "0"), (1085, "2"),
                         (1025, "1"), (1053, "10"), (1013, "0")]:
        decoder.decode(tag, payload)
        assert decoder.next_queries == []
        assert not any(kind in ("initial_updates", "fault_update", "hide_emp") for kind, _ in decoder.effects)
        assert "call_for_reset_c1n2" not in decoder.state
    assert not decoder.last_valid  # Unsolicited Empower reply is ignored.
    assert decoder.readbacks.value(1068) == 0


def test_external_visible_rate_uses_tdg_readbacks_without_empower_prf():
    def read(panel, control):
        assert panel not in (8, 9)
        return 0
    decoder = ExternalResponseDecoder(read=read, clock=lambda: 10)
    decoder.decode(1051, "EXT")
    decoder.decode(1025, "2")
    decoder.decode(1053, "10")
    assert decoder.values[6, 7] == 5
    assert decoder.values[6, 6] == 5
    decoder.decode(1010, "999")
    assert not decoder.last_valid
    assert decoder.values[6, 7] == 5


def test_decoder_keeps_previous_display_on_empty_reply_but_invalidates_eligibility():
    decoder = ExternalResponseDecoder(clock=lambda: 10)
    decoder.decode_line("(1,1)<1042>3.3")
    assert decoder.last_valid
    assert decoder.values[5, 32] == 3.3
    assert decoder.decode_line("(1,2)<1042>") == []
    assert not decoder.last_valid
    assert decoder.values[5, 32] == 3.3
    assert not decoder.readbacks.is_fresh(1042, 10)


def test_malformed_multiline_reply_invalidates_named_readback():
    decoder = ExternalResponseDecoder(clock=lambda: 10)
    decoder.decode_line("(1,1)<1042>3.3")
    assert decoder.decode_line("(1,2)<1042>3.3\nACK") == []
    assert not decoder.last_valid
    assert not decoder.readbacks.is_fresh(1042, 10)


def test_unit_suffixes_and_hex_prefix_keep_original_gui_scale_and_bits():
    decoder = ExternalResponseDecoder(clock=lambda: 10)
    for payload in ("3.3", "3.3 KV", "3300 V"):
        decoder.decode(1042, payload)
        assert decoder.values[5, 32] == 3.3
    decoder.decode(1066, "0x1000")
    assert decoder.values[3, 14] == 1
    decoder.decode(1065, "80 MHZ")
    assert decoder.values[5, 7] == 80


def test_current_fault_is_not_cleared_by_absent_pump_or_legacy_system_status():
    decoder = ExternalResponseDecoder(clock=lambda: 10)
    for tag, payload in [(1068, "1"), (1039, "4000"), (1066, "4000"),
                         (1088, "0"), (1089, "4"), (1085, "0")]:
        decoder.decode(tag, payload)
    assert decoder.readbacks.fault_reason(10)
    decoder.decode(1014, "0 0 0 0")
    assert not decoder.last_valid
    assert decoder.readbacks.fault_reason(10)


def test_health_attribute_preserves_tcp_fault_contract_without_empower():
    _, transport = fixture()
    decoder = ExternalResponseDecoder(clock=lambda: 10)
    for tag in REQUIRED_IDS:
        decoder.decode(tag, transport.values[QUERIES[tag].upper()])
    updates = decoder.check_health()
    assert any((u.panel_id, u.control_id, u.attribute, u.value) == (6, 50, 500, 1) for u in updates)
    for tag, bad in ((1015, "2048"), (1066, "1000"), (1088, "4")):
        original = transport.values[QUERIES[tag].upper()]
        decoder.decode(tag, bad)
        updates = decoder.check_health()
        assert any((u.panel_id, u.control_id, u.attribute, u.value) == (6, 50, 500, 0) for u in updates)
        decoder.decode(tag, original)


def test_simulator_refuses_pump_traffic_and_models_independent_pc_channels():
    transport = SimulatedTransport()
    transport.send_packet(PACKET_PREFIX + b"[1013]EMP:STB?\n")
    assert transport.receive() == []
    transport.send_packet(PACKET_PREFIX + b"[2027]ON\n")
    assert "ERROR" in transport.receive()[0].body
    transport.send_packet(PACKET_PREFIX + b"[2019]TDG:DEL 2 ON\n[1046]TDG:DEL2?\n")
    responses = transport.receive()
    assert "DELAY 2 ON BWD ENA 200.00" in responses[-1].body
    assert "OFF" in transport.values["TDG:DEL1?"]
    transport._command(2019, "TDG:DEL", "2 123.5")
    assert transport.values["TDG:DEL2?"] == "DELAY 2 ON BWD ENA 123.5"
    transport._command(2019, "TDG:DEL", "2 OFF")
    assert transport.values["TDG:DEL2?"] == "DELAY 2 OFF BWD ENA 123.5"

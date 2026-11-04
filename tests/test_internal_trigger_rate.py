"""Internal trigger input limits and request serialization without hardware."""
import ctypes
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from spitfire.callbacks import dispatch
from spitfire.limits import (
    INTERNAL_TRIGGER_MIN_HZ,
    INTERNAL_TRIGGER_MAX_HZ,
    validate_internal_trigger_hz,
)
from spitfire.native import NativeGui, RESOURCES
from spitfire.protocol import PACKET_PREFIX, PacketBuffer
from spitfire.scheduling import Request, Scheduler


def read_control(closed_loop, frequency=5000.0):
    values = {(6, 48): closed_loop, (5, 28): frequency, (5, 43): 1.0,
              (9, 9): 1000.0, (2, 7): 5.0}
    return lambda panel, control: values.get((panel, control), 0)


@pytest.mark.parametrize("frequency", [10, 10.0, 12.345, 1000, 10000, "10"])
def test_finite_internal_trigger_range(frequency):
    assert validate_internal_trigger_hz(frequency) == float(frequency)


@pytest.mark.parametrize("frequency", [
    0, -1, 9.99, 10000.01, 1e300,
    float("nan"), float("inf"), float("-inf"), "invalid", None,
])
def test_invalid_internal_trigger_input_is_rejected_before_any_action(frequency):
    with pytest.raises(ValueError, match="10 and 10000 Hz"):
        dispatch("trig_reprate", frequency, event=1, panel=5, control=28,
                 read=read_control(0))


@pytest.mark.parametrize("closed_loop", [0, 1])
@pytest.mark.parametrize("frequency,argument", [(10, " 10.00"), (10000, " 10000.00")])
def test_trigger_commit_serializes_only_rate_and_mandatory_readback(closed_loop, frequency, argument):
    actions = dispatch("trig_reprate", frequency, event=1, panel=5, control=28,
                       read=read_control(closed_loop))
    assert [(a.kind, a.target, a.value) for a in actions] == [
        ("command", 2032, argument), ("query", 1053, None)]
    packets = []
    for action in actions:
        buffer = PacketBuffer()
        packets.extend(buffer.append(Request(action.target, action.value or "").message))
        packets.append(buffer.flush())
    assert packets == [
        PACKET_PREFIX + f"[2032]TDG:TRIG:FREQ{argument}\n".encode("ascii"),
        PACKET_PREFIX + b"[1053]TDG:TRIG:FREQ?\n",
    ]


def test_noncommit_trigger_events_do_not_validate_or_send():
    assert dispatch("trig_reprate", float("nan"), event=2, panel=5, control=28) == []


@pytest.mark.parametrize("closed_loop", [0, 1])
@pytest.mark.parametrize("name,value,tag,query", [
    ("SetHVCallback1", 5.0, 2025, 1040),
    ("ecu_set_temp", 5.0, 2021, 1032),
    ("com_motor_speed", 5.0, 2014, 1060),
])
def test_other_numeric_callbacks_keep_original_range_and_followup_policy(closed_loop, name, value, tag, query):
    actions = dispatch(name, value, event=1, read=read_control(closed_loop))
    assert [(a.kind, a.target, a.value) for a in actions] == (
        [("command", tag, "  5.00")]
        + ([("query", query, None)] if closed_loop else []))


def test_native_range_override_uses_numeric_varargs_without_changing_setpoint():
    view = NativeGui.__new__(NativeGui)
    view.controller = None
    view.panels = {5: 505}
    view.attributes = json.loads((RESOURCES / "cvi_attributes.json").read_text())
    view._types = {(5, 28): 3}
    view.values = {(5, 28): 5000.0}
    view.varargs = SimpleNamespace(SetCtrlAttribute=Mock(return_value=0), SetCtrlVal=Mock())
    view._configure_internal_trigger_range()
    calls = view.varargs.SetCtrlAttribute.call_args_list
    assert [call.args[:3] for call in calls] == [(505, 28, 731), (505, 28, 730)]
    assert all(isinstance(call.args[3], ctypes.c_double) for call in calls)
    assert [call.args[3].value for call in calls] == [10.0, 10000.0]
    view.varargs.SetCtrlVal.assert_not_called()
    assert view.values[5, 28] == 5000.0


def test_qt_spec_range_matches_native_and_preserves_original_defaults():
    spec = json.loads((RESOURCES / "gui_spec.json").read_text())
    panel = next(p for p in spec["panels"] if p["id"] == 5)
    control = next(c for c in panel["controls"] if c["id"] == 28)
    assert control["minimum"] == control["attributes"]["min_value"] == INTERNAL_TRIGGER_MIN_HZ
    assert control["maximum"] == control["attributes"]["max_value"] == INTERNAL_TRIGGER_MAX_HZ
    assert control["value"] == control["attributes"]["value"] == control["attributes"]["dflt_value"] == 5000.0
    assert control["increment"] == control["attributes"]["incr_value"] == 500.0


def test_initialization_and_polling_do_not_queue_a_trigger_rate_setpoint():
    scheduler = Scheduler()
    scheduler.queue_initial()
    scheduler.queue_poll()
    assert all(request.tag != 2032 for request in (*scheduler.inside, *scheduler.outside))

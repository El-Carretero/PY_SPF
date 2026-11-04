"""Recovered Spitfire 1.6.0 callback semantics, independent of a GUI toolkit.

Panel numbers are the original UIR panel IDs. Attribute IDs deliberately retain
CVI constants so the same actions can drive a CVI adapter or a Python GUI.
Evidence: original executable build 2005-03-18, functions 0x40ab3c..0x413148.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
import struct

from .limits import validate_internal_trigger_hz

EVENT_COMMIT = 1
EVENT_LEFT_CLICK = 3
EVENT_LEFT_DOUBLE_CLICK = 4
EVENT_RIGHT_CLICK = 5
EVENT_RIGHT_DOUBLE_CLICK = 6
EVENT_TIMER_TICK = 15
ATTR_VISIBLE = 0x212
ATTR_ENABLED = 0x4F7
ATTR_INCR_VALUE = 0x2DD
ATTR_PRECISION = 0x2DF

@dataclass(frozen=True)
class Action:
    kind: str
    target: Any
    value: Any = None


def command(number: int, parameter: str = "") -> Action:
    return Action("command", number, parameter)


def query(number: int) -> Action:
    return Action("query", number)


def _f32(value: Any) -> float:
    """CVI numeric controls used single precision before sprintf promotion."""
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


# name: (command id, follow-up query id, factor, original fixed source control)
NUMERIC_CALLBACKS = {
    "slidesetcurr": (2003, 1009, 10.0, (9, 8)),
    "slideqswprf": (2004, 1010, 0.1, (9, 9)),
    "slideqswpw": (2007, 1011, 1.0, (9, 10)),
    "slideqswsrc": (2008, 1012, 1.0, (9, 11)),
    "com_motor_speed": (2014, 1060, 1.0, None),
    "ecu_set_temp": (2021, 1032, 1.0, (2, 7)),
    "DivisorCallback": (2020, 1025, 1.0, (5, 43)),
    "trig_reprate": (2032, 1053, 1.0, None),
    "SetHVCallback1": (2025, 1040, 1.0, None),
    "SetHVCallback2": (2026, 1041, 1.0, None),
}
INTEGER_CALLBACKS = {
    "optoutecucall": (2024, 1033, (2, 11)),
    "optoutcompressorcall": (2035, 1069, (2, 10)),
    "empoweroptoutcall": (2036, 1068, (2, 9)),
    "LBOstabilitybreak": (2047, 1078, None),
}
SHOW_PANELS = {"show_secrets": (7, "SECRETS_OPEN"), "show_setup": (9, "SETUP_OPEN"),
               "show_faults": (3, "FAULTS_OPEN"), "show_info": (5, "INFO_OPEN"),
               "show_help": (4, "HELP_OPEN"), "show_ccu": (2, "CCU_OPEN")}
HIDE_PANELS = {"close_fault": 3, "close_info": 5, "close_service": 7,
               "close_setup": 9, "close_ecu": 2, "close_help": 4,
               "close_secrets_emp": 8, "Close_Programmer_Panel_Callback": 1}
CLICK_CALLBACKS = {"parse_command5", "BW_reset"}


def _rate_updates(read: Callable, *, copy_emp: bool = False,
                  copy_trigger: bool = False) -> list[Action]:
    divisor = _f32(read(5, 43)) or 1.0
    emp = _f32(read(9, 9))
    trigger = _f32(read(5, 28))
    # In the original non-positive frequencies are copied without division.
    actions = [Action("set", (6, 6), trigger / divisor if trigger > 0 else trigger),
               Action("set", (6, 7), emp / divisor if emp > 0 else emp)]
    if copy_emp:
        actions.insert(0, Action("set", (6, 9), emp))
    if copy_trigger:
        actions.insert(0, Action("set", (6, 8), trigger))
    return actions


def access_level_actions(level: int) -> list[Action]:
    """Exact panel/control mutations made by _SetAccessLevel (0x40b0b8)."""
    level = int(level)
    actions = [Action("state", "gAccessLevel", level)]
    if level not in range(4):
        return actions
    labels = ("USER MODE", "SERVICE MODE, CLICK TO LOWER LEVEL",
              "FACTORY MODE, CLICK TO LOWER LEVEL", "PROGRAMMER MODE, CLICK TO LOWER LEVEL")
    colors = (0xC0C0C0, 0x008000, 0x00FFFF, 0xFFFF00)
    actions.append(Action("attribute", (6, 45, 0x281), labels[level]))
    if level == 0:
        actions += [Action("attribute", (6, 49, 0x214), -30),
                    Action("attribute", (6, 49, 0x213), -30)]
    actions.append(Action("attribute", (6, 45, ATTR_VISIBLE), int(level != 0)))
    actions += [Action("panel_attribute", (9, 0x21C), (250, 480, 480, 850)[level]),
                Action("panel_attribute", (5, 0x21C), 546 if level == 3 else 446),
                Action("panel_attribute", (5, 0x215), 390 if level == 0 else 750),
                Action("panel_attribute", (6, 0x21C), 550),
                Action("panel_attribute", (2, 0x21C), 250 if level == 0 else 480)]
    for panel in (3, 9, 5, 2):
        actions.append(Action("panel_attribute", (panel, 0x23A), colors[level]))
    if level == 3:
        actions.append(Action("panel_attribute", (6, 0x21C), 990))
    actions.append(Action("panel", 8, level != 0))
    if level:
        actions.append(Action("panel_attribute", (8, 0x23A), colors[level]))
    actions.append(Action("panel", 1, level == 3))
    if level == 3:
        actions.append(Action("panel_attribute", (1, 0x23A), colors[level]))
    actions.append(Action("server_panel", None, level == 3))
    return actions


def dispatch(callback_name: str, value: Any = 0, *, read: Callable | None = None,
             event: int | None = None, panel: int | None = None,
             control: int | None = None, state: dict | None = None) -> list[Action]:
    """Translate one original CVI callback event to explicit application actions.

    ``read(panel, control)`` returns current GUI values. If omitted, the supplied
    value is used for the callback control and other controls default to zero.
    ``event=None`` selects the original callback's normal activation event.
    Runtime-only callbacks (mouse timer, hold-to-run) can use ``state``.
    """
    name = callback_name.lstrip("_")
    if read is None:
        read = lambda p, c: value if (panel, control) == (p, c) else 0
        source_value = lambda src: value
    else:
        source_value = lambda src: read(*src) if src else value
    state = {} if state is None else state
    event = (3 if name in CLICK_CALLBACKS else 1) if event is None else event
    if name in SHOW_PANELS:
        p, flag = SHOW_PANELS[name]
        return [Action("state", flag, 1), Action("panel", p, True)]
    if name in ("hide_emp_controls", "show_emp_controls"):
        return [Action("attribute", (6, 19, ATTR_VISIBLE), int(name == "show_emp_controls"))]
    if name in ("hide_ecu_controls", "show_ecu_controls"):
        visible = int(name == "show_ecu_controls")
        return [Action("attribute", target, visible) for target in
                ((6, 16, ATTR_VISIBLE), (2, 16, ATTR_VISIBLE), (2, 15, ATTR_VISIBLE))] + [query(1032)]
    if name in HIDE_PANELS:
        return [Action("panel", HIDE_PANELS[name], False)] if event == 1 else []
    if name in ("QuitProgram", "Shutdown", "exit_from_menu"):
        return [Action("quit", None)] if name == "exit_from_menu" or event == 1 else []
    if name == "SetAccessLevel":
        return access_level_actions(int(value))
    if name == "cmtRETUSERMODE":
        return access_level_actions(int(state.get("gAccessLevel", value)) - 1) if event == 1 else []
    if name == "set_max_current":
        return []  # Original callback is intentionally empty (0x40aaee).
    if name == "strnsendcllback":
        return [command(2034, str(source_value((6, 59))))]
    if name == "reconnect":
        return [Action("reconnect", None)]
    if name == "MainPanelCB":
        return [Action("server_panel", None, False)] if event == 11 else []
    if name == "MainCallBack":
        if event == 7:
            character = chr(int(value) & 255) if isinstance(value, (int, float)) else str(value)[:1]
            return [Action("key_pressed", None, character)]
        return []
    if name == "ClearScreenCB":
        return [Action("reset_textbox", (panel, 4), "")] if event == 1 else []
    if name == "TransmitCB":
        if event == 1:
            message = str(source_value((panel, 3))) + "\n"
            return [Action("set", (panel, 2), message), Action("set", (panel, 3), ""),
                    Action("server_write", None, message)]
        return []
    if name == "tmr_Data_Logger":
        if event == 15 and read(1, 3):
            return [Action("append_file", "datalog.csv", "%.2f, %.2f\n" %
                           (_f32(read(9, 2)), _f32(read(8, 15))))]
        return []
    if name == "display_faults":
        return dispatch("show_faults", read=read) if event == 1 else []
    if name == "picture_Callback1":
        if event not in (3, 5):
            return []
        return [Action("state", "motor_mouse_button", 1 if event == 3 else 2),
                command(2009 if event == 3 else 2010),
                Action("attribute", (6, 4, ATTR_ENABLED), 1)]
    if name == "picture_Callback2":
        return [command({3: 2012, 4: 2012, 5: 2011, 6: 2011}[event])] if event in (3, 4, 5, 6) else []
    if name == "tmr_Mouse_Callback1":
        if event == 15 and not state.get("left_mouse_down") and not state.get("right_mouse_down"):
            return [command(2013), Action("attribute", (6, 4, ATTR_ENABLED), 0)]
        return []
    if name == "cllbck":
        if event == 1:
            return [Action("state", "evnt_cmt", 0)]
        if event == 3:
            return [Action("state", "turn_on_started", "now"), Action("state", "evnt_cmt", 1)]
        return []
    if name == "parse_command5":
        return [command(2028), query(1013), Action("set", (2, 8), 0)] if event == 3 else []
    if name == "BW_reset":
        return [command(2018), query(1066)] if event == 3 else []
    if event != 1:
        return []
    connected = bool(read(6, 48))
    if name in NUMERIC_CALLBACKS:
        cmd, followup, factor, src = NUMERIC_CALLBACKS[name]
        source = source_value(src)
        if name == "trig_reprate":
            source = validate_internal_trigger_hz(source)
        val = _f32(source)
        # Float multiplication/division occurs on the x87 stack before sprintf.
        number = val / 10.0 if name == "slideqswprf" else val * factor
        actions = [command(cmd, " %5.2f" % number)]
        # A trigger-rate edit needs an actual readback even when the legacy
        # closed-loop preference is off; do not publish an optimistic rate.
        if connected or name == "trig_reprate":
            actions.append(query(followup))
        elif name in ("slideqswprf", "DivisorCallback"):
            actions += _rate_updates(read, copy_emp=name == "slideqswprf")
        return actions
    if name in INTEGER_CALLBACKS:
        cmd, followup, src = INTEGER_CALLBACKS[name]
        val = int(source_value(src))
        actions = [command(cmd, " %i" % val)]
        if name == "empoweroptoutcall":
            actions.append(Action("attribute", (6, 19, ATTR_VISIBLE), int(not val)))
        if connected:
            actions.append(query(followup))
        else:
            field = {"optoutecucall": "ecu_optout", "optoutcompressorcall": "hed_optout",
                     "empoweroptoutcall": "emp_optout"}.get(name)
            if field:
                actions.append(Action("state", field, val))
            if name == "optoutecucall":
                actions += [Action("attribute", target, int(not val)) for target in
                            ((6, 16, ATTR_VISIBLE), (2, 16, ATTR_VISIBLE), (2, 15, ATTR_VISIBLE))]
                actions.append(query(1032))
        return actions
    if name in ("osc_mode", "trig_mode", "humoverride", "bwdpolarity", "bwdduality"):
        options = {
            "osc_mode": (2030, 1050, "  EXT", "  INT"),
            "trig_mode": (2031, 1051, " EXT", " INT"),
            "humoverride": (2029, 1057, " 1", " 0"),
            "bwdpolarity": (2033, 1054, "  POS", "  NEG"),
            "bwdduality": (2033, 1054, "  DUAL", "  SING"),
        }
        cmd, followup, yes, no = options[name]
        actions = [command(cmd, yes if _f32(value) else no)]
        if connected:
            actions.append(query(followup))
        elif name == "trig_mode":
            for ctrl in (6, 7, 8, 9):
                visible = int((ctrl in (6, 8)) != bool(_f32(value)))
                actions.append(Action("attribute", (6, ctrl, ATTR_VISIBLE), visible))
        return actions
    if name == "HV_switch":
        return [command(2017 if _f32(value) else 2016), query(1061)]
    if name == "teconoff":
        return [command(2022 if _f32(value) else 2023)]
    if name.startswith("swChannelEnableCallback_btn"):
        ch = int(name[-1])
        actions = [command(2019, " %d %s" % (ch, "on" if int(value) else "off"))]
        if ch >= 3 and connected:
            actions.append(query(1044 + ch))
        return actions
    if name.startswith("setbwd") or name.startswith("setena"):
        ch = int(name[-1])
        yes, no = ("BWD", "NBWD") if name.startswith("setbwd") else ("ENA", "NENA")
        actions = [command(2019, " %d %s" % (ch, yes if _f32(value) else no))]
        if connected:
            actions.append(query(1044 + ch))
        return actions
    if name.startswith("SetCoarseCallback_btn"):
        ch = int(name[-1])
        actions = [command(2019, " %d %5.2f" % (ch, _f32(value)))]
        if connected and ch not in (1, 2):
            actions.append(query(1052 if ch == 0 else 1044 + ch))
        return actions
    coarse_controls = {"Ch1_Coarse_Check_Callback": (6, 43), "Ch2_Coarse_Check_Callback": (6, 42),
                       "SYNC_Coarse_Check_Callback": (6, 41), "Ch3_Coarse_Check_Callback": (5, 42),
                       "Ch4_Coarse_Check_Callback": (5, 41)}
    if name in coarse_controls:
        p, ctrl = coarse_controls[name]
        return [Action("attribute", (p, ctrl, ATTR_INCR_VALUE), 10.0 if int(value) else 0.25),
                Action("attribute", (p, ctrl, ATTR_PRECISION), 0 if int(value) else 2)]
    if name.startswith("secretcall") and name[-1].isdigit():
        n = int(name[-1])
        actions = [command(2036 + n, " %5.2f" % _f32(value)), command(2045)]
        if n >= 2:
            actions.append(query(1069 + n))
        return actions
    if name == "cllbckcmd_reset":
        return [command(n) for n in (2044, 2049, 2052, 2050)] + fault_update_actions()
    if name == "cmd_osc_to_meas":
        return [command(2046, " %5.2f" % _f32(source_value((5, 7)))), query(1065)]
    if name == "setopmode":
        val = int(value)
        params = {0: " CONT", 1: " COUNT", 2: " COUNT 1"}
        if val not in params:
            raise ValueError("Original operation mode is 0, 1 or 2")
        actions = [command(2048, params[val])]
        if connected:
            actions.append(query(1080))
        elif val == 2:
            actions.append(Action("set", (panel, control), 1))
        return actions
    if name == "esc_turnoff":
        return [command(2028), Action("set", (2, 8), 0)]
    if name == "Monitor_switch":
        return [command(2051, " %d" % int(value))]
    if name == "tdg_fault_override":
        return [command(2053, " %d" % int(value))]
    if name in ("open_curtain", "close_curtain"):
        closed = int(name == "close_curtain")
        return [Action("menu_attribute", (6, 0, 0x1F4), closed),
                Action("attribute", (6, 49, ATTR_VISIBLE), closed),
                Action("attribute", (6, 54, ATTR_VISIBLE), closed)]
    raise KeyError(f"Callback {callback_name!r} is not implemented")


def fault_update_actions() -> list[Action]:
    # The original intentionally enqueues this sequence twice.
    return [query(n) for n in (1089, 1088, 1014, 1066, 1057) * 2]


class AccessKeyTracker:
    """Original typed-key access sequence, gated by config.sp maxLevel."""
    words = ("user", "regensvc", "factory", "programmer")

    def __init__(self):
        self.positions = [0, 0, 0, 0]

    def feed(self, character: str, max_level_code: int = 0) -> int | None:
        result = None
        for level, word in enumerate(self.words):
            pos = self.positions[level]
            if character == (word[pos] if pos < len(word) else "\0"):
                pos += 1
                if pos == len(word):
                    allowed = level in (0, 1) or (level == 2 and max_level_code in (6251, 3146)) or (level == 3 and max_level_code == 3146)
                    if allowed:
                        result = level
                        pos = 0
                    else:
                        # Native code leaves a completed but denied sequence at
                        # its terminating NUL until the next mismatching key.
                        pos = len(word)
                self.positions[level] = pos
            else:
                self.positions[level] = 0
        return result

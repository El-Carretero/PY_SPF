# Spitfire 1.6.0 callback reconstruction

Evidence is the uploaded `SPITFIRE.EXE` (native 32-bit LabWindows/CVI, build timestamp 2005-03-18), its retained internal symbol table, x86 instructions, and `decompiled.c`. Attached document text has not been treated as instructions.

Implementation: `work/spitfire_python/spitfire/callbacks.py`. Machine-readable evidence: `callbacks.json`. All command/query titles and parameter format references: `callback_summary.txt`.

## Adapter contract

`dispatch(callback_name, value=0, read=read_control, event=None, panel=None, control=None, state=None)` returns immutable `Action(kind, target, value)` values. Names accept the original leading underscore. `read(panel_id, control_id)` must read current GUI/model state. Panel IDs are the original UIR IDs, independent of runtime CVI handles.

- `command`: target is a command ID (2000 series), value is the exact suffix including spaces.
- `query`: target is a query ID (1000 series).
- `set`: target `(panel, control)`, value is the new control value.
- `attribute`: target `(panel, control, CVI attribute)`, value is the new attribute value.
- `panel_attribute`: target `(panel, CVI attribute)`.
- `panel`: target is the panel ID, value is visibility.
- `state`: target is an original/global state field name.
- `menu_attribute`: target `(panel, menu item, CVI attribute)`.
- `server_panel`, `server_write`, `reset_textbox`, `reconnect`, `quit`, and `append_file` require application adapters.

Panel mapping: main 6, setup 9, info 5, ECU 2, faults 3, help 4, secrets 7, Empower 8, programmer 1. Main control 48 indicates connected status. Raw CVI attributes verified independently from runtime metadata: 530 visible, 531 left, 532 top, 533 width, 540 height, 570 background, 641 label, 733 increment, 735 precision, 1271 timer enabled.

## Directly recovered behavior

| Original function / address | Recovered behavior |
| --- | --- |
| `_slidesetcurr` 0x40b00f | Reads setup control 8 as float32, multiplies by 10, command 2003, format ` %5.2f`; query 1009 when connected. |
| `_slideqswprf` 0x40acda | Reads setup control 9 as float32, divides by 10, command 2004; query 1010 when connected. Offline updates the displayed frequencies. |
| `_slideqswpw` 0x40aecd | Command 2007, query 1011 when connected. |
| `_slideqswsrc` 0x40af6e | Command 2008, query 1012 when connected. |
| `_ecu_set_temp` 0x40e6be | Fixed source ECU panel 2 control 7; command 2021, query 1032 when connected. |
| `_DivisorCallback` 0x40e75f | Fixed source info panel 5 control 43; command 2020, query 1025 when connected. Offline recomputes trigger/divisor and pump/divisor. Zero divisor is replaced by 1 for display calculations. |
| `_trig_reprate` 0x40edbf | Command 2032, query 1053 when connected. Offline recomputes frequency displays. |
| `_HV_switch` 0x40ec0f | Nonzero -> command 2017 `TDG:HV:ON`; zero -> command 2016 `TDG:HV:OFF`; always query 1061. |
| `_teconoff` 0x410720 | Nonzero -> command 2022 `ECU:TECON`; zero -> command 2023 `ECU:TECOFF`. |
| `_SetHVCallback1/2` 0x40ef87 / 0x40f01f | Commands 2025/2026, queries 1040/1041 when connected. Float32 input and ` %5.2f`. |
| `_osc_mode` 0x40e913 | Command 2030 with exact suffixes `  EXT` / `  INT`; query 1050 when connected. |
| `_trig_mode` 0x40ea14 | Command 2031 with exact suffixes ` EXT` / ` INT`; query 1051 when connected. Offline shows/hides main controls 6–9. |
| `_humoverride` 0x40ecbe | Command 2029 ` 1` / ` 0`; source query is 1057 (`ECU:STBH?`), preserving the original choice. |
| `_bwdpolarity` 0x410518 | Command 2033 suffix `  POS` / `  NEG`; query 1054 when connected. |
| `_bwdduality` 0x410600 | Command 2033 suffix `  DUAL` / `  SING`; query 1054 when connected. |
| `_swChannelEnableCallback_btn1..5` 0x40f109.. | Command 2019 suffix ` n on` / ` n off`. Channels 1/2 do not immediately query. Channels 3/4/5 query 1047/1048/1049 when connected. |
| `_setbwd1..5`, `_setena1..5` 0x40f5ea.. | Command 2019 suffix ` n BWD` / ` n NBWD` or ` n ENA` / ` n NENA`; channel-specific query when connected. |
| `_SetCoarseCallback_btn0..5` 0x411653.. | Command 2019 suffix ` n %5.2f`. Channels 1/2 do not immediately query; channel 0 queries 1052, channels 3–5 query 1047–1049 when connected. |
| Coarse checkboxes 0x411ab5..0x411df9 | Checked: increment 10.0 and precision 0. Unchecked: increment 0.25 and precision 2. Main Ch1/Ch2/sync controls 43/42/41; info Ch3/Ch4 controls 42/41. |
| `_secretcall1..7` 0x412037.. | Command 2037..2043 followed by 2045 `EMP:SECRETSCOMT`. Secret1 has no immediate query; secrets2..7 query 1071..1076. |
| `_cllbckcmd_reset` 0x412428 | Commands 2044,2049,2052,2050, followed by the fault update query sequence below. |
| `_issue_fault_update_sequence` 0x4130b7 | Queries 1089,1088,1014,1066,1057 in this order, intentionally repeated twice. |
| `_setopmode` 0x412584 | Command 2048 suffix ` CONT`, ` COUNT`, or ` COUNT 1`. Query 1080 when connected. Offline mode 2 is reset to control value 1 after dispatch. |
| `_Monitor_switch` 0x412ffd | Command 2051 suffix ` %d`. |
| `_tdg_fault_override` 0x41305a | Command 2053 suffix ` %d`. |
| `_strnsendcllback` 0x410a10 | Reads main control 59 and dispatches its text as command 2034's suffix, preserving direct console behavior. |
| `_set_max_current` 0x40aaee | Empty original callback. |

## Event-specific behavior

Most control changes execute only for CVI event 1 (commit). `_parse_command5` (command 2028 `OFF`, query 1013, ECU control8=0) and `_BW_reset` (command 2018, query1066) execute for event3 (left click). This distinction must be preserved by a GUI adapter.

`_picture_Callback1` (0x4107b5) starts motor rewind command2009 on event3 and forward command2010 on event5. It enables main timer control4. `_tmr_Mouse_Callback1` (0x410885) handles event15; after both global mouse button states are up, command2013 stops the motor and disables timer4. `_picture_Callback2` (0x410928) dispatches command2012 for events3/4 and command2011 for events5/6 (jog behavior).

`_cllbck` (0x40aba7) clears `evnt_cmt` on event1; on event3 it records current whole-second time and sets `evnt_cmt=1`. The worker at 0x406953 acts only after elapsed whole seconds are greater than 3, then sends command2027 (`ON`), sets ECU control8=1, and clears `evnt_cmt`. The application scheduling layer must implement this timer. The callback module emits `turn_on_started='now'` plus `evnt_cmt=1`.

`_tmr_Data_Logger` (0x412e60), event15, checks programmer panel1 control3. If enabled, it appends `%.2f, %.2f\n` (setup panel9 control2 and Empower panel8 control15, both float32 inputs) to `datalog.csv`.

Quit callbacks quit the user interface; they do not issue a hardware OFF command.

## Access modes and panels

`access_level_actions(level)` preserves `_SetAccessLevel` (0x40b0b8), including per-mode panel dimensions, control label, title/background color changes, and service/Empower/programmer/server panel visibility. User mode also moves main control49 to left/top −30. Service/factory leave main height550; programmer expands it to990 after setting550. `cmtRETUSERMODE` (0x4106e8) decrements the current access level by one, despite its name.

The keyboard sequence itself is implemented by `settings.AccessKeySequence`: words `user`, `regensvc`, `factory`, `programmer`, case-sensitive. User and service are always allowed; factory requires `[Spitfire] maxLevel` numeric6251 or3146 from `c:\config.sp`; programmer requires3146. Original event is7 and the key character is eventData1 &255. `callbacks.AccessKeyTracker` is a standalone equivalent helper, but the application should use the settings module to keep file handling together.

The show-panel menu functions set their original `*_OPEN` global flags to1. Close-panel callbacks hide the panel without resetting those flags. This source behavior is preserved. Curtain helpers dim/undim the main menu and show/hide main controls49 and54.

## Validation and limits

The Python module compiles successfully. The implemented command branches, IDs, parameter formats, fixed source controls, access-mode mutations, and event constants were compared with the recovered x86 and Ghidra C. This subtask did not run the original program or connect to hardware. The root integration may perform differential tests against an isolated original-code oracle. Invalid operation-mode values outside0–2 are rejected explicitly, while the original would reuse a prior global parameter string; valid GUI paths never generate such values.

## Extended original-code differential validation

The follow-up oracle `native_callback_extended.py` maps the original x86 code into Unicorn and intercepts CVI/CRT calls. It starts no Windows process, loads no original DLL, and performs no external file, socket or device I/O. `GetCtrlVal` uses each original UIR control's actual data type (integer, float32 or string), rather than writing floats indiscriminately.

`python work/analysis/native_oracle.py --extended` now passes **395/395 cases across 85 callback/helper names**, including **63 command-producing names and 34 names producing GUI mutations**. Integer control samples use0/1 (operation mode also2), float controls use0/1/12.345, and connected/debug branches use0/1. Additional cases cover every motor click/double-click direction, mouse-held timer branches, access-level GUI effects, original show/hide helpers and SERVER console callbacks. Command sequence and formatted text are compared exactly. GUI values/attributes/panel/menu effects are compared by final observable state; numeric comparisons allow1e−13 for emulator floating-point representation. Full per-case evidence is `native_callback_extended_results.json`.

This check found and corrected a real discrepancy in offline trigger-mode display: INT shows main controls6/8 and hides7/9; EXT shows7/9 and hides6/8. The corrected implementation passes all cases. Logging timer file append and the multi-key access-sequence workflow remain covered by their separately recovered code and settings/controller checks, rather than this callback oracle. These checks do not substitute for physical hardware testing or a pixel comparison of the complete GUI.

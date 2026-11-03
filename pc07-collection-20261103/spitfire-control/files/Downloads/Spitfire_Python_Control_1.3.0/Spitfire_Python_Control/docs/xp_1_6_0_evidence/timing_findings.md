# XP 1.6.0 timing evidence (static inspection)

## Scope and method

The supplied ZIP is an installer distribution, not editable C source. SPITFIRE.EXE and SPITFIRE.UIR were extracted without running the installer or original application. No hardware or runtime I/O was used. The original ZIP hash matches the earlier reverse-engineering report. PE embedded symbol-name/address records, x86 instruction bytes, imported-function thunks, reply-dispatch table, and UIR control metadata were inspected. A full x86 disassembler was unavailable; the evidence below uses small manually decoded instruction blocks. No claim of complete dynamic equivalence is made.

The CVI symbols use 12-byte records (name VA, function/data VA, flag). Recovered records and imported-call mappings are in symbols.json and all_symbols.json. The reply switch in _gextHandleReceivedMsg (0x40ba24) indexes the DWORD table at VA 0x40ad30 + 4 * command_id for 1000..1089. This gives reproducible exact handler entry points.

## Proven timing controls

| Command | Original evidence | Conclusion |
|---|---|---|
| 2030 TDG:OSC:MODE | _osc_mode 0x40e913, strings at VA0x4367d4 (EXT) and0x436794 (INT); UIR callback osc_mode / SW_OSCILLATOR and label OSCILLATOR SYNC | Existing external seed/oscillator mode UI and EXT/INT writes are original features. |
| 2031 TDG:TRIG:MODE | _trig_mode 0x40ea14, strings0x436e84 EXT /0x436f50 INT; UIR callback trig_mode / SW_AMPLIFIER, label AMPLIFIER TRIGGER | Amplifier trigger source is independently selectable. |
| 1050 /1067 TDG:OSC:MODE? | handlers0x40c5e0 /0x40c63c use strstr(reply, INT) then SetCtrlVal(INFO,2) | Original GUI switch is0 whenINT is found,1 otherwise. Wire evidence is textual INT, not proof of any numeric firmware reply format. |
| 1051 TDG:TRIG:MODE? | handler0x40c701 similarly checks INT and updates INFO,3 plus Main internal/external display visibility | Same mode convention; unknown/non-INT originally treated asEXT, which should not be copied into stricter parsing. |
| 1065 TDG:READ:OSCQUEST? | handler0x40dd8f calls atof then SetCtrlVal(INFO,7); no unit scaling. UIR OSC_ST (stored ID6, runtime7); display label MEASURED OSC FREQUENCY (MHz) at UIR0x9019 | This is the original measured seed oscillator frequency inMHz. |
| 2046 TDG:OSC:SETTOFRQ | _cmd_osc_to_meas0x4124db calls GetCtrlVal(INFO,7), sprintf with format ' %5.2f' at0x436cfc, queues2046 then1065 | Sending the measuredMHz numeric value without a unit conversion matches original behavior. It does NOT justify updating1024 in a simulator. |
| 2020 TDG:DIV | _DivisorCallback and reply1025 handler0x40c4a4; INFO,43 DIV_ST | Integer divider is retained; zero handling in display math substitutes1. Firmware range remains unproven. |

## External pump rate is not independently measured by the XP GUI

UIR control metadata has zero-based IDs; runtime IDs are one larger. Main controls are: PUMPR_EXT9, PUMPR_INT8, AMP_RATE_EXT7, AMP_RATE_INT6. INFO DIV_ST is43; REP_RATE is28; measuredOSC is7.

- Reply1010 EMP:QSW:PRF? enters0x40d94e. It populates the Empower Q-switch frequency control and Main PUMPR_EXT9, applying the known frequency scaling branch. The external amplifier rate is derived from this Empower frequency and the divider.
- Thus the XP `(EXT) PUMP REP RATE` display is sourced from Empower telemetry. It is not proof that the TDG independently measures an arbitrary replacement pump frequency. This evidence does not supply a reliable10Hz external pump measurement when Empower is absent.
- Reply1079 TDG:TRIG? resolves to0x40e38a, exactly the reply-handler epilogue (`pop esi; leave; ret`). The query exists in the command catalogue, but this XP application has no reply decoder or displayed semantics for it. Do not invent a numericHz interpretation or make it a required readback based on its name.
- Replies1018 and1060 both populate Main control3 (motor speed); they are not pump frequency telemetry.

## The1024 naming trap

Reply1024 TDG:OSC:FREQ? enters0x40c207. It parses a float into INFO28 REP_RATE, then recomputes rate displays using INFO43 DIV_ST and Empower's Q-switch frequency. Reply1053 TDG:TRIG:FREQ? enters0x40c0ae and uses the same INFO28 field, additionally updating Main PUMPR_INT8. The UIR visible label for that control is INTERNAL AMP REP RATE.

Therefore1024 must NOT be treated as a second independently measured80MHz seed frequency. The measuredMHz display is1065. The application behavior alone does not resolve whether1024 is a legacy firmware alias, a confusing firmware name, or an original GUI mapping defect. Keep its raw value/query name without inventing a unit or hardware interpretation. In particular, the simulator should not assume2046 updates1024 merely because both command names containOSC.

## Original initialization side effect worth not copying

The1067 reply handler checks forINT. IfINT is absent (normallyEXT), it queues2030 INT followed by2030 EXT (0x40c6bc..0x40c6f9). The strings are0x43679c INT and0x4367dc EXT. The apparent purpose may be re-locking/reinitialization, but that is an inference. Python's read-only connection startup should not reproduce this automatic write sequence. An explicit re-lock function would require separate hardware/firmware validation.

## Limits

The installer/GUI does not provide TDG firmware source, a proven minimum external trigger frequency, independent externalpumpHz measurement semantics, an optical phase-lock detector, replacement-pump flashlamp/Q-switch delay requirements, or proof of10Hz operation. Existence of a configuration command or simulator response is not such proof. Gate on known mode/readback/fault evidence; label pump timing and optical synchronization as unverified where no independent measurement exists.

## Integrity

- SPITFIRE.EXE: 271360 bytes, SHA-256 `8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b`
- SPITFIRE.UIR: 152636 bytes, SHA-256 `1c5b82a8cf528934bffffe0989a73312059b07a15fc3056df8fbeb41607bd67b`

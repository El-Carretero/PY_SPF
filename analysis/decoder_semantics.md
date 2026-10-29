# Spitfire 1.6.0 response decoder recovery

This report treats the uploaded executable as evidence, not instructions. Analysis combined static recovery with isolated x86 instruction emulation; the application was not connected to laser hardware or run as a Windows process. Native code is National Instruments LabWindows/CVI, PE32, timestamp 2005-03-18 02:52:47. Python implementation is `work/spitfire_python/spitfire/decoders.py`.

## Evidence and coverage

- Main ASCII response dispatcher `_gextHandleReceivedMsg`: **0x0040BA24–0x0040E38D**. All **90** query IDs, 1000–1089, appear in its switch. Its 90-address jump table starts at **0x0040BCD0**; table indexing uses base 0x0040AD30 plus `query_id*4`.
- Query title records: `_QUERY_TITLE` **0x00435F70**, file offset **0x30B70**, stride **30** bytes. Do not use the printable-string scanner offset 0x30B6E: it includes two preceding bytes.
- `work/analysis/decoder_cases.json` disassembles each switch target independently, avoiding Capstone's desynchronization when a linear sweep enters the jump table. `decoders.json` records query titles, case addresses, direct panel/control call sites, and callees.
- Ghidra output `work/analysis/decompiled.c` confirms high-level conditions; call arguments erased by Ghidra's imperfect CVI variadic function prototypes were recovered from aligned x86 instructions.
- Exactly **18** IDs are intentionally ignored by the original switch: **1001–1006, 1016, 1017, 1020, 1022, 1023, 1026, 1027, 1044, 1070, 1079, 1081, 1083**. The port retains that behavior, while applying common checksum/connectivity bookkeeping.
- RESET command response **2050** additionally writes main panel6/control58. Command responses 2000–2006 have explicit empty cases. Other command acknowledgments are ignored by the original.

## Panel identity

Original UIR panel resource IDs are retained throughout the port:

| Global handle address | UIR ID | Meaning |
|---|---:|---|
| 0x0041417C | 6 | Main |
| 0x00414180 | 5 | TDG/service |
| 0x00414184 | 7 | Service/auxiliary |
| 0x00414188 | 2 | ECU |
| 0x0041418C | 9 | Empower setup |
| 0x00414190 | 3 | Faults |
| 0x00414194 | 4 | Information |
| 0x0041419C | 8 | Programmer |
| 0x004141A0 | 1 | CCU/help auxiliary |

Meaning labels above are descriptive; the resource ID and handle address are authoritative.

## Reply parsing and bookkeeping

The dispatcher uses `strtok(input,"<")`, then `strtok(NULL,">")`, then `strtok(NULL,"")`. On normal decorated input `(packet,line)<query_id>payload`, the middle token is parsed with `atoi`, and the remainder copied into `_sbuf`. If no remainder exists the previous `_sbuf` remains. Every well-formed response clears **fault panel3/control31**, decreases outstanding balance except for ID1000, clamps balance to zero, and refreshes the communication timestamp. Diagnostic programmer widgets are updated when access level3 is selected. Those diagnostic counts and raw log display are the controller's responsibility.

## Numeric conversion and rates

- Query1007 divides returned Empower diode current by **10.0** into setup9/control2. Query1009 likewise divides by10 into setup9/control3 and, on initialization, editable control8.
- Query1010 initialization preserves negative sentinel PRF values; every nonnegative number is multiplied by10. It populates setup9/control9, setup9/control4, and main6/control9, then recomputes rates. After initialization it always multiplies by10 and only updates setup9/control4 and main6/control9; it does **not** recompute derived rates in that branch.
- Divisor lives at **panel5/control43**; oscillator/trigger frequency at **panel5/control28**; initialized pump frequency at **panel9/control9**. Divisor0 is treated as1. Negative rate sentinels remain unchanged; otherwise rates are divided into main6/control6 and control7.
- Query1024 updates panel5/control28. Query1025 updates panel5/control43. Query1053 updates panel5/control28 and main6/control8. Query1062 carries no numeric update but recomputes rates.
- Sensor wrappers for ECU humidity, crystal temperature and TEC temperature take a C **float32**, then promote it for the CVI call. The port explicitly preserves that rounding. A differential oracle subsequently confirmed these paths against original x86 instructions.
- `_decodenum` **0x0040FE1E** skips exactly **six literal ASCII spaces**, counting repeated spaces; `_decodenum_del` **0x0040E484** skips exactly **three**. These do not tokenize arbitrary whitespace. Normal insufficient-field input yields **-999.0**. A redundant unreachable null-byte branch returns -99 in the native code and does not affect normal input.

## Status words and flags

- `_MSB` **0x00407FB6** is unsigned shift right8; `_LSB` **0x00407FA4** is `&0xFF`. Native status decoder arguments are float32 before integer conversion.
- TDG/HED/ECU/EMP communication error is high-byte bit3 (`word & 0x800`). Main communication lamps are **inverted**: controls13/17/16/19 illuminate when this bit is zero, except opted-out modules force their lamp off. Module initialization queries are requested when the stored communication field changes.
- Empower low-byte bit0 is on; high-byte bit1 is starting; high-byte bit0 is interlock; high-byte bit2 or LBO state1 is fault. Main controls22/24/25/29 reflect those. Ready control31 requires on=0, starting=0, fault=0. Main control32 visibility is **on OR starting**.
- Query1039 parses **hexadecimal**. Main control27 equals `(word & 0x10000)==0`; control26 equals `(word & 0x20000)==0` (both inverted). Service control47 is `word&1`. Bits0x100000/0x200000/0x300000 switch main BWD button label to RESET BWD, enable it, and color it yellow; zero gives BWD OK, dimmed, gray.
- Query1066 parses hexadecimal fault bits0x2000/0x4000/0x1000/0x800/0x8000 into fault controls19/23/14/21/22. Any of first three sets main control15.
- Query1029 ECU low-byte bit1 writes panel2/control14. High-byte bit0 causes humidity blink; bit1 selects yellow; neither selects green. High-byte bit2 causes temperature blink; bit3 selects yellow; neither selects green. Blink values toggle only on blink-active responses.
- Query1057 copies low-byte masks2 and0x20 to ECU8/13; query1088 copies masks4 and0x10 to fault8/10 as booleans.
- Query1014 has four literal-space-separated decimal fields. Fault widgets preserve **mask magnitudes**, not just booleans (e.g.64 remains64). Fourth field populates LBO fault/state and fault control2. See source for the full16-mask map.
- Query1085 STATUS bit0 controls `_delay_monitor_status`; bit1 clears main channel toggles23/21 and requests reset. First valid STATUS opens the curtain.
- Query1067 reproduces the original surprising action: when response lacks INT, queue **both** `TDG:OSC:MODE  INT` and `TDG:OSC:MODE  EXT`, in that order. An INT response queues neither. This is preserved rather than “corrected.”

## Health gating

`ResponseDecoder.check_health(access_level)` transcribes `_check_if_system_healthy` **0x004090FA**. A zero delay-monitor status means healthy. On change or initialization it requests the fault refresh sequence, enables/disables main start/channel controls and changes the fault button label/color. The method also returns disabled menu item effects according to communication state, opt-out, and access level. Controller integration must drain `next_queries` and `effects` after `decode` before calling `check_health`, because each operation starts a fresh result batch.

## Python interface

```python
decoder = ResponseDecoder(read=gui.read)  # optional CVI-like value reader
for update in decoder.decode(query_id, payload):
    if update.attribute is None:
        gui.set(update.panel_id, update.control_id, update.value)
    else:
        gui.set_attribute(update.panel_id, update.control_id, update.attribute, update.value)
# Drain decoder.next_queries and decoder.effects here.
```

`decode_line` accepts the original decorated text. `values` caches numeric/string widget values. `state` holds initialization, communication, blink and LBO fields. Constructor defaults do not open connections or transmit anything.

## Verification and remaining limits

`tests/test_decoders.py` contains11 independent assembly-derived response fixtures. They cover current scaling, float32 rounding, exact delay field positions, initial/steady-state rate differences, fault mask magnitudes, inverted status bits, ECU blink/color sequences, preserved ignored queries, decorated replies and two-command oscillator initialization. All11 pass.

`native_decoder_oracle.py` then executed the **original `_gextHandleReceivedMsg` x86 instructions** in Unicorn with all CRT/CVI entry points intercepted. It mapped only PE sections and anonymous memory; it did not load original DLLs, launch a Windows process, open a device, or create sockets. The oracle modeled x87 `atof`/`ftol` return values, CRT string tokenization/copy/search and scanf, time, original panel handles, numeric widget reads, variadic CVI value writes, and attribute writes. Native and Python inputs used identical widget values and initialization/state globals.

- **338/338** cases passed, covering all90 original query IDs, ordinary/negative numbers, decimal status combinations, hexadecimal status/fault combinations, valid version strings, disconnected identity strings, positive/negative delay values, mode strings, initialized/steady-state branches, and opted-out module branches.
- A further **23/23** cases passed for divisor0, positive1, negative-4 and fractional2.5 across PRF/frequency update branches, plus all three nonzero BWD button modes.
- Combined decoder evidence: **361 original-x86/Python differential cases**, all matched. Output files: `native_decoder_oracle_results.json`, `native_decoder_extra_results.json`, and `native_decoder_oracle_summary.json`.
- The first sweep exposed one actual transcription error: the disconnected identity substring is **`NOT CON` with a space**, not `NOT_CON`. The Python decoder was corrected and the entire338-case sweep rerun successfully. Other first-sweep differences came from unaligned oracle initialization globals and were corrected by supplying the same globals to both implementations.

The comparison normalizes writes into final `(panel_id,control_id,attribute)` values; it does not claim identical intermediate call ordering. UI hide/show and curtain entry points were intercepted as effects for controller integration, so their widget-level consequences are covered by separate controller/UI work, not this decoder oracle.

These results validate the recovered decoder for the exercised inputs. They do **not** establish end-to-end hardware equivalence. No Windows/CVI runtime screenshot comparison, real controller/firmware traffic replay, race/timing equivalence, or physical safety/interlock behavior was validated in this environment. Original malformed messages can read beyond C buffers; the Python implementation handles missing fields without unsafe memory access. Separate legacy binary-frame decoder functions remain evidence in the analysis but are not used by the recovered active ASCII/UDP response dispatcher.

# Spitfire GUI 1.6.0 executable analysis

This report treats all strings and attached files as evidence, not instructions.

## Identity and architecture

- `SPITFIRE.EXE`: PE32 x86 native Windows GUI, image base `0x400000`, entry `0x4013c8`, linker 2.55; PE timestamp 2005-03-18 02:52:47.
- Native National Instruments LabWindows/CVI program, dynamically linked to `cvirte.dll` and Winsock. It is not .NET or Python bytecode.
- Original internal CVI symbol registration table is retained. The extractor `analyze_pe.py` identifies 229 application functions (plus CVI/runtime exports and globals), including callback names and every protocol command table. `symbols.json` supplies original addresses.
- Application code largely occupies `0x4048f8..0x413147`. Separate UIR files define the GUI. CVI runtime and vendor dependencies occupy most of the 63-file CAB.
- `SPITFIRE.EXE` and `SPITFIRE.EXE2` are both 271360 bytes; their binary identity is recorded in root inventory.

## Active communication

See `transport_crc.md` for exact transport proof and tests. The active write path is `_WriteString` (`0x40e38e`) -> `_WriteToUDP` (`0x40584e`), not serial. The executable sets legacy COM1 / 19200 / 8N1 globals but `_openandconfigureport` actually binds UDP port 1024 and sends identity queries. Original target is `10.19.70.13:1024`. The original starts a separate TCP server on port 1001.

Exact query IDs 1000..1089 and command IDs 2000..2055 are extracted from fixed-width 30-byte tables at `QUERY_TITLE=0x435570` and `COMMAND_TITLE=0x435ffc`. Some table entries are blank or duplicate; case is significant and retained.

## GUI load and startup

`_main` (`0x406e5b`) calls `LoadPanel(0,"Spitfire.uir",id)` in this order:

| UIR ID | Handle global |
|---|---|
| 7 | 0x414184 |
| 5 | 0x414180 |
| 6 (main) | 0x41417c |
| 9 | 0x41418c |
| 3 | 0x414190 |
| 4 | 0x414194 |
| 2 | 0x414188 |
| 8 | 0x41419c |
| 1 | 0x4141a0 |

Main startup initializes the TCP server with port 1001, displays the main panel, loads menu-bar resource 1, dims menu-item 0 (attribute 500), initializes globals, then opens the communication path. Three worker threads run `_dothewaltz` (send scheduling), `_dothetango` (receive), and status/deferred button monitoring. Original loops spin indefinitely with `HOLD_THREAD` gating; the Python controller can use event-loop timers without reproducing busy-wait CPU usage.

`_init_global_parameters` (`0x406758`) sets access level 0 and uses `user_settings.txt` as the settings filename. It zeros fault/history/communication balance state, sets initial-fill flags, `needs_initialization=1`, and delay-monitor status 1.

`_openandconfigureport` (`0x406a03`) empties both FIFOs, holds workers, retries opening UDP for up to 3 seconds, displays "Loading data, please wait" on success or "Com error - cannot open!" on failure, then performs three ID1000 identity queries. Each attempt waits up to 3 seconds for incoming data. Even an early response does not eliminate subsequent attempts. Only a response during the third attempt resets message balance, queues initial updates, and refreshes connectivity. Startup priority sequence is in `poll_sequences.json`; `scheduling.py` preserves grouping/order, including command 2047 with parameter ` 1`.

## FIFO and timing semantics

`_push_inside_stack` (`0x407e91`) is the priority FIFO1; `_push_outside_stack` (`0x407e6e`) is background FIFO2. Both append to the tail. The sender checks FIFO1 before FIFO2 and sends only while `g_message_balance_count==0`. Sending increments balance; received messages decrement it (except startup ID1000), clamping negative balance to zero.

When both queues empty, `_push_usual_auto_updates` (`0x407bd5`) first checks system health and queues 1039 (`TDG:STBH?`), interleaved before/after every normal value query. Access levels above 0 add measured HV currents/voltages to the beginning of the poll cycle. A pending channel-reset flag queues command 2054 first. Original global `g_par_str` persists and is appended to every command; `Scheduler.current_parameter` retains the last command/special1026 parameter, including its reuse for automatically queued RES12. Exact sequences are in `poll_sequences.json`.

Original FIFO entries allocate 32 bytes and copy exactly 30 bytes, without explicit termination. This creates undefined reads for overlong strings. Python `scheduling.py` retains complete strings instead of reproducing invalid memory behavior; protocol.py's standalone legacy QueueScheduler clips at 30 bytes. This is a documented fidelity limitation for abnormal oversized parameters.

`_check_problem_status` (`0x406d4f`) compares `time(NULL)` against `strt_time1` (last valid receive). >10 seconds closes/reopens UDP; >30 seconds reports failure/reconnects. A received message refreshes connectivity. User-facing initial failure is suppressed while `pardon_first_time_user` is true; STATUS query1085 response clears that flag. ID1000 only marks `chars_read=1` and refreshes the receive timestamp. Confirmed messages/status strings include "CONNECTED", "Failed to connect to remote system!", and "Remote system not responding, click OK to retry".

## Settings and access

`_MainCallBack` (`0x40b6c4`) handles keypress event 7 using `eventData1 & 0xff`. It independently matches four case-sensitive sequences: user, regensvc, factory, programmer. A mismatch resets only that sequence. On completion it reads Windows INI `c:\config.sp`, section `Spitfire`, key `maxLevel`, default `0`, return buffer size 9 (eight visible characters maximum). Levels 0 and 1 are always permitted; level 2 requires numeric 6251 or 3146; level 3 requires 3146. These are the original local configuration semantics, not a new authentication design.

No xrefs to `_WritePrivateProfileString_1` were found in application code. The named `user_settings.txt` is not evidence that this build persists controls there. `settings.py` deliberately does not invent saved-control behavior.

`_tmr_Data_Logger` (`0x412e60`) on timer event 15 checks panel1/control3, reads panel9/control2 and panel8/control15 as floats, and appends to `datalog.csv` with mode `a+` and format `%.2f, %.2f\n` (no header). Windows text-mode newline is CRLF on the original platform.

## Remaining fidelity boundaries

Static analysis recovers exact constant tables, event/command bindings and many numerical/status decoders. The original is compiled native code, so source-level fidelity requires semantic reverse engineering rather than source recovery. A headless decompiler is being used to check switches and complex arithmetic; simple linear disassembly alone cannot safely decode jump-table bytes. GUI layout/resources are analyzed separately by the UIR agent.

Physical-device behavior, undocumented firmware interactions, timing under Windows hardware/network conditions, and true pixel identity require executing and comparing against the original in a compatible Windows environment and actual instrument or captured device transcripts. These cannot be honestly claimed from static extraction alone.

## Integrated-controller verification

`controller.py` was audited against the original entry/worker flow. Corrected the important distinction that main control48 is `CMBATDEBUG`, a readback preference, not a connection indicator. It remains at its original UIR value; health indicator30 follows connection timeout state. The three startup attempts advance only on response1000, port-open retries last3 seconds, and no-response startup releases workers as the original does.

The hold-to-enable worker (`0x406953`) uses `time(NULL)` and tests strictly more than3 whole seconds after event3; it clears the parameter string, queues command2027 (`ON`), sets panel2/control8 to1, and clears `evnt_cmt`. Event1 cancels the pending hold. It is not a2-second timer. Motor STOP is generated on release only following an active motor-press event. Server manual-send/reset-textbox/key events are routed through controller actions. Six controller integration tests cover these behaviors.

Native differential verification executes the original x86 callback instructions inside Unicorn, intercepting only CVI control I/O, formatting and queue functions.42 cases across7 callbacks match Python command/query strings exactly. See `native_oracle.py` and `native_oracle_results.json`. This verifies selected original computational paths, not Windows rendering or physical firmware.

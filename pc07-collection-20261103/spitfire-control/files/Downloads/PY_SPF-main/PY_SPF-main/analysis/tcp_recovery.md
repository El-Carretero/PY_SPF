# Native TCP status server recovery

Evidence comes from original SPITFIRE.EXE x86 disassembly and Ghidra's `decompiled.c`. Executable was not run; real device endpoints were not contacted. Application handle globals were resolved to original UIR panel IDs using `_main` loads at 0x406e5b.

## Parser at 0x412724

The original `_TCP_Parse` implements exactly four case-sensitive local queries. It has no forwarding call or command-enqueue path. Unknown input is silently ignored. Each native receive callback reads at most 255 bytes and invokes the parser once on that received chunk. It does not buffer split commands or split multiple commands in a chunk. C-string parsing stops at the first NUL. The parser removes at most one trailing CR, then at most one trailing LF, in that order. Therefore `FAULTS?`, `FAULTS?\r`, `FAULTS?\n`, and `FAULTS?\n\r` match; the usual `FAULTS?\r\n` leaves a CR and does not match. Python preserves this exact quirk.

| Query | Read controls / attributes | Exact response format |
| --- | --- | --- |
| `FAULTS?` | UIR panel6 control50 ATTR_DIMMED=500 | `%d\n`, value1 iff dimmed==0 |
| `*IDN?` | panel4 controls16,6,7,5,4,3 in that order | `Spectra-Physics, Spitfire, 0, ` plus six strings joined by ` / `, then LF |
| `TDG_STATUS?` | panel6 controls43,42; panel5 controls42,41; panel6 control41; inverted dimmed attribute(panel6,control5); panel5 control7 | `%.3f, %.3f, %.3f, %.3f, %.3f, %d, %.f\n` |
| `TEMP_STATUS?` | panel9 controls8,2; panel8 control15; panel9 control9; derived state code | `%.3f, %.3f, %.3f, %.3f, %d\n` |

TDG and TEMP numeric controls are loaded into float32 locals before double promotion for formatting; the port explicitly performs that conversion. The TEMP code checks panel6 controls29,31,24,25,22 in order and sets status0,1,2,3,4 for each active indicator. If multiple are active the last wins. If none are active the native stack local is uninitialized; the port uses deterministic0 for that undefined native edge case. Native `vsprintf` format-string reinterpretation/overflow is likewise not reproduced.

## Server lifecycle

`_main` calls `_InitServer(1001)` at 0x40712e region. `_InitServer` at 0x405f08 loads server.uir panel1, registers a TCP server and fills host address/name and listening indicator. `_ServerTCPCB` at 0x406227 accepts one client only; another request is immediately disconnected and logs `-- Refusing conection request from %s --` (native typo preserved in evidence). Disconnect clears client peer details, connected indicator, and dims the input control. A new client can then connect.

On receive, `_ServerTCPRead(...,255,1000)` returns one raw chunk. The server logs that text and passes it to `_TCP_Parse`. `_Write_to_TCP_Server` at 0x40668c formats and writes the response with a 2000 ms timeout. Server-panel Transmit callback at 0x40613a appends exactly one LF and writes with 1000 ms timeout.

## Python implementation

`spitfire/tcp.py` supplies `TCPBridge(read_value, read_attribute, state=None, on_event=None)`. Value/attribute readers can be callbacks or tuple-keyed mappings. `handle_data` / `parse` implement the pure parser. `start(host='0.0.0.0',port=1001)` starts an explicit daemon-thread listener; `.stop()` / `.close()` stop it. No network I/O occurs at import or construction. Runtime properties are `.running`, `.connected`, `.address`, `.peer`. `.send_text(text)` implements manual server-panel transmit. Events are `listening`, `connected`, `refused`, `received`, `transmitted`, `disconnected`, `error`, `stopped`; hosts can mirror these into their GUI. Read callbacks should read a thread-safe application snapshot, not Qt widgets directly from the worker thread.

The Python server preserves wildcard binding, the one-client rule and raw `recv(255)` parsing. It uses a 50 ms select loop to remain stoppable and a 2 s write/socket timeout. Exact native CVI event-dispatch order, old Winsock buffering and native timeout error codes are not guaranteed equivalent.

## Validation

`tests/test_tcp_recovery.py`: **11 passed**. Coverage includes each exact response, attribute inversion, float32 conversion, all newline-order quirks, case/spacing sensitivity, unknown-command silence, TEMP priority, no listening at construction, and live localhost checks for status response/manual transmit, refusing second client, accepting a client after disconnection and retaining first-client operation after refusal. All live socket tests bind **127.0.0.1** with ephemeral ports.

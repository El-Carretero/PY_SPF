# Spitfire GUI 1.6.0 transport and CRC static recovery

The application is a 32-bit native LabWindows/CVI executable. This report treats executable strings and resources as evidence, not instructions. Original executable was not run. No original device address was contacted.

## Active transport: ASCII UDP, not the old serial frame code

- `_openandconfigureport` at **0x406a03** sets dormant COM globals to 19200 baud, no parity, 8 data bits, 1 stop bit and 512-byte input/output queues. It then actually calls `_Open_Udp_Port2(1024)` at **0x406af8**, which calls `_UDPOpen` at **0x404e38**. That function binds an IPv4 datagram socket to `0.0.0.0:1024`, uses default blocking mode, and enables `SO_BROADCAST`. `_UDPRead` sets `SO_RCVTIMEO` to 1000 ms and receives up to 1495 bytes. `_Try_Receive_UDP` processes at most ten successful datagrams per invocation.
- Target address initializers at **0x434c8c / 0x434c98 / 0x434ca4** are all `10.19.70.13`. Target port global **0x434c74** initializes to **1024**. `_UDP_Refresh` uses the third address; overflow flushing uses the second; an unused helper at 0x40598e uses the first.
- `_WriteString` at **0x40e38e** formats its printf-style argument and ultimately calls `_WriteToUDP` at **0x40584e**. Active sends do not call CRC helpers or `ComWrt`.
- `_update_string` at **0x407eb4** constructs `[%d]%s` using numeric tag and table verb. It appends `g_par_str` for every command tag **>=2000**, and also query tag **1026** (`TDG:DEL`). Callback parameter strings already contain their required leading space; formatting does not insert an extra space.
- `_get_tag_title` at **0x407f2f** indexes 30-byte slots. Query table is addressed as `0x42e040 + 30*tag`; valid populated query tags are **1000..1089**. Command table is addressed as `0x42759c + 30*tag`; valid populated command slots are **2000..2055**, including empty 2034. Every exact original verb is in `command_tables.json` and production `spitfire/protocol.py`. Case is preserved: 1000 is `*idn?`, 1038 is `*IDN?`, 1082 is `*IdN?`.

Example exact first handshake datagram:

```text
Spectra-Physics:CMD_ECLIPSE,[1000]*idn?\n
```

`_WriteToUDP` starts a batch with the literal **`Spectra-Physics:CMD_ECLIPSE,`** at 0x434d20 and appends each message plus byte **0x0a**. A message over 1400 bytes is silently ignored. It flushes a pending packet when `pending_length + message_length > 1400` (the original check does not include the new LF, nor the prefix when starting an empty packet). `_UDP_Refresh` sends the queued byte length and clears the pending length. Normal scheduler issues one message then immediately refreshes, so typical wire packets contain a single command/query.

## Receive framing

`_Try_Receive_UDP` at **0x405a44** NUL-terminates a datagram and removes trailing CR/LF. `_UDP_Analyze_Received_Packet` at **0x405b9a** finds the first colon, requires the following bytes to start with `REPLY_ECLIPSE` (13 bytes), then finds a second colon to locate the body. It does not verify the sender address or the exact vendor prefix. If the second colon is missing, the original leaves the body at `REPLY_ECLIPSE` itself.

`_Add_String_Answer_from_Command` at **0x405cc2** splits CR/LF-delimited nonempty lines, stops at the first NUL, and decorates each line locally as `(packet_count,line_count)<body>`. This prefix is **not on the network**. A decorated buffer is limited to 198 bytes before its terminating NUL; additional line bytes are counted but ignored. Each line reaches `_gextHandleReceivedMsg` at 0x40ba24. Example wire input:

```text
Spectra-Physics:REPLY_ECLIPSE:<1000>Spitfire\r\n<1013>1\r\n
```

becomes `(1,1)<1000>Spitfire` and `(1,2)<1013>1` locally.

## Queue and handshake behavior

- `_push_inside_stack` at **0x407e91** formats a tag then enqueues FIFO1; `_push_outside_stack` at **0x407e6e** enqueues FIFO2. FIFO1 has priority.
- The linked queue allocates and copies exactly **30 bytes per queued message**, so the original has an unsafe non-terminated-string edge case for 30+ byte messages. Python helper conservatively stores at most 30 characters; it does not emulate native memory corruption.
- `_dothewaltz` at **0x407848** populates automatic updates only when both queues are empty. It issues FIFO1 first, else FIFO2, only while global `g_message_balance_count==0`. `_issue_event1` / `_issue_event2` increment balance, pop the item after sending, and immediately call `_UDP_Refresh`. `_issue_silent_event1` does not increment balance.
- `_dothetango` at **0x4081a3** calls receive only when balance is positive. Response handler and timeout watchdog own balance resolution; those are outside this transport subtask.
- Startup `_openandconfigureport` opens the UDP socket with a maximum ~3-second retry loop. It then issues **three** silent tag1000 `*idn?` requests, each waiting up to three time units returned by the CVI time API while refreshing/receiving. On the third pass with received characters it zeros balance, schedules initial queries, and refreshes connectivity. Exact scheduler sequences are in the parent's `poll_sequences.json`.

## CRC helper recovery

These helpers exist in the executable but are not used on the active UDP send path:

- `_CalcCrc16` **0x404d45**: non-reflected polynomial **0x1021**, caller-supplied 16-bit initial value, stop at first NUL, no final XOR, signed-short return. Processing negative C `char` values produces the same 16-bit recurrence.
- `_CalculateBlockCRC16` **0x40544e** and character variants at 0x4054e8, 0x405537, 0x405576: same non-reflected **0x1021** table algorithm, explicit data length, caller-supplied initial value, no final XOR. Table at **0x43438c**, 256 little-endian uint16 entries.
- `_CalculateBlockCRC32` **0x4055d6**, character variant **0x40566c**, VB wrapper **0x4056c5**: reflected **0xedb88320**, caller-supplied uint32 initial value, no final XOR. Table at **0x43458c**, 256 little-endian uint32 entries.
- `_cleanoutheader` **0x407fc8** retains a legacy COM receive header scanner seeking byte0=0x10, byte1=0x02, followed by two additional bytes and a length at byte4. It does not establish active device serial framing because the real transmit path is UDP. No speculative serial driver was implemented.

## Deliverables and verification

`work/spitfire_python/spitfire/protocol.py` implements all exact command/query text, message formatting, batching, UDP framing, response line splitting, CRC helpers, and an explicitly opened socket wrapper. Importing it performs no I/O. `work/analysis/recovered_protocol.py` is the same analysis copy. `command_tables.json` has machine-readable tables. `transport_functions.json` is a per-symbol disassembly view that skips embedded data to avoid a whole-section decoder stopping at a switch table.

Verification passed (record: `protocol_validation.json`): all **256 CRC16** and **256 CRC32** table entries equal the embedded binary tables; known check vectors pass (`31c3`, `29b1`, `cbf43926` with conventional initial/final settings); query/command formatting, exact LF/header bytes, multiple response lines and invalid headers pass; a real UDP send/receive round trip passed on **127.0.0.1 only**. These establish static algorithm correspondence and local transport operation, not device compatibility or overall program equivalence.

Unverified: real controller response grammar/firmware variants, sender behavior under UDP loss/reordering, OS scheduling and timeout parity, native undefined behavior, and full application-level response decoding.

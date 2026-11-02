# 6. Evidence, reproducibility, and unknowns

This chapter separates recovered application behavior, saved physical-device observations, and behavior that has not been measured. The primary evidence labels are **CODE VERIFIED**, **XP/LOG VERIFIED**, **MANUAL**, **INFERRED**, and **UNKNOWN**. A label applies to a particular claim and test boundary; it does not certify the entire controller or laser.

## Reading the evidence labels

| Primary label | Required interpretation |
|---|---|
| **CODE VERIFIED** | The cited current Python source establishes the application behavior. This alone does not establish device execution or optical behavior. |
| **XP/LOG VERIFIED** | State whether the reference is **original x86 disassembly/emulation**, a **physical-device application log**, a **historical read-only capture**, or a **Native runtime test without a device**. Original x86 analysis is not a physical XP-PC test. The label alone must never imply that the original application was exercised on Windows XP with the physical device. |
| **MANUAL** | Identify the document, revision, model scope, and printed/PDF page. A manual for another model is contextual evidence, not a validated SASC firmware specification. |
| **INFERRED** | The conclusion follows from identified code, observations, or a manual, but the complete causal path has not been measured. State the missing step. |
| **UNKNOWN** | The required observation or authoritative specification is unavailable. A simulator result or an empty ACK cannot fill that gap. |

The [source registry](evidence/source_registry.json) adds provenance kinds: `E-STATIC`, `E-EMULATED`, `E-SYNTHETIC`, `E-NATIVE-NO-DEVICE`, `E-PHYSICAL-READONLY`, `E-PHYSICAL-CONTROL-LOG`, `E-PHYSICAL-WRAPPED`, `E-MANUAL`, and `E-UNKNOWN`. `E-PUBLICATION-STANDARD` identifies the separate formatting authority and carries no device-behavior claim. Availability is recorded separately. Tracked source and a tracked curated summary are different from a private raw record that a repository reader cannot inspect. Original-source hashes and the immutable branch baselines are recorded in [source_manifest.json](evidence/source_manifest.json) and [branch_baselines.json](evidence/branch_baselines.json).

## Evidence register

| Stable source ID | Label and provenance | Repository reference / retained source | What it supports; boundary |
|---|---|---|---|
| `SRC-ORIG` | **XP/LOG VERIFIED — original x86 disassembly**, `E-STATIC` | [Original PE](../../analysis/reference/SPITFIRE.EXE), [transport recovery](../../analysis/transport_crc.md), [command tables](../../analysis/command_tables.json), [poll sequences](../../analysis/poll_sequences.json) | Application-side UDP framing, verbs, queues, callback and decoder instructions. This is not a physical XP-PC test or a complete firmware protocol specification. |
| `ORACLE-X86` | **XP/LOG VERIFIED — emulated original x86**, `E-EMULATED` | [Callback oracle](../../analysis/native_oracle.py), [decoder oracle](../../analysis/native_decoder_oracle.py), [logging oracle](../../analysis/native_logging_oracle.py), and their saved results | Selected original functions execute in Unicorn with CVI/CRT calls intercepted. Callback results include 42 initial and 395 extended cases; decoder suites contain 338 and 23 additional cases. These are separate suites, not a count of independent physical tests. |
| `UDP-LOCAL` | **CODE VERIFIED**, `E-STATIC` / `E-SYNTHETIC` | [Protocol validation](../../analysis/protocol_validation.json), [synthetic examples](../../tests/fixtures/optout_protocol.json), [offline verifier](../../analysis/verify_optout_capture.py) | CRC tables, exact byte examples, response splitting, and localhost UDP behavior. The fixture explicitly contains synthetic examples; its historical name does not make it a physical capture. |
| `NATIVE-CRT` | **XP/LOG VERIFIED — Native runtime, no device**, `E-NATIVE-NO-DEVICE` | [NI CRT validation](../../analysis/post2_native_crt_validation.json), [GUI environment record](../../analysis/native_gui_validation.json) | The bundled NI runtime accepted a prefixed hexadecimal `%x` value and sentinel GUI values. The GUI environment record uses Wine/QEMU and a simulator. Neither is an XP physical-device run. |
| `P01-COLLECTOR` | **XP/LOG VERIFIED — historical read-only capture**, `E-PHYSICAL-READONLY` | Private initial/ending JSON captures, Primary/Continuation wire JSONL, and execution-scope report; identities and hashes in the registry | Actual UDP payloads collected at at most four queries per second. The NI observer consumed response files; this was not the unmodified production Native application running continuously. |
| `P01-NATIVE-SOAK` | **XP/LOG VERIFIED — physical Native read-only**, `E-PHYSICAL-READONLY` | [Curated release validation](evidence/release_validation.json); historical [release report](../../analysis/release_1_0_validation.json) | A production Native 30-minute observation and the exercised menu-loop case, with source hashes. It does not exercise every NI modal interaction or actuator write. |
| `P01-FAULT-BURST` | **XP/LOG VERIFIED — physical normal-control log**, `E-PHYSICAL-CONTROL-LOG`; offline causal check is **CODE VERIFIED**, `E-SYNTHETIC` | Curated [Fault Reset burst evidence](evidence/fault_burst_summary.json); private reset findings and original Native events | Eight queued Fault Reset groups, normal ACKs, delayed STATUS, stale GUI state, and cancellation of the last reset. Offline replay demonstrates the queue path without proving device-side reset semantics. |
| `P01-RESET-RETEST` | **XP/LOG VERIFIED — physical bounded wrapper**, `E-PHYSICAL-WRAPPED` | [Reset evidence](evidence/reset_retest_summary.json); private per-mode wire and summary records | One BWD reset and one four-command Fault Reset through the Native adapter path, with every other write blocked. Windows mouse delivery and NI runtime event dispatch were outside this test. |
| `P01-BWD-HISTORY` | **XP/LOG VERIFIED — retained physical logs**, mixed physical provenance | [BWD history summary](evidence/bwd_history_summary.json); private time-ordered CSV, scan manifest, identity records, and ACK pairs | What the retained 1039/1066 responses and reset receipts actually contain. The sampling and session gaps prevent an all-times state claim. |
| `MAN-330A` | **MANUAL**, `E-MANUAL` | User-provided PDF attachment, identified below and in the manifest; full PDF is not redistributed here | Documented operating principles for the named manual/model scope. Applicability to the installed SASC hardware/firmware requires a matching model and revision. |
| `STD-XL` | Publication standard; no device-evidence grade | User-provided xLaPPLAs technical-publication standard, identified below and in the manifest | Formatting and publication authority only; it supplies no evidence about laser operation or firmware. |

### Manual identity and page conventions

`MAN-330A` is the **Spitfire Pro User Manual, 330A Rev A**, 110 PDF pages, SHA256 `d9bb260827f78a2ed67477043cb3036a26b771aaf19a0c3ec9aa6649449d5e29`. Example page anchors used in this guide are printed 4-4 / PDF 50, 6-1 / PDF 61, 6-9 / PDF 69, 6-10 / PDF 70, and 8-3 / PDF 89. `STD-XL` is **XL-STD-DOC-001 xLaPPLAs Technical Publications Standards, Rev A**, 63 PDF pages, SHA256 `3a59e249677683bc373a0a1f4ee35fbfb9e677310c49f778806a961654663157`. It governs document presentation and is not an operating manual or firmware specification.

PDF page means the one-based file page index, not the printed section-page number. The original attachments remain with the project owner; document identities and limited technical citations are retained here. The operating manual's presence does not establish that the installed hardware is the model or revision described. A claim about the current firmware still needs a matching specification or measurement.

## Physical observations and their exact limits

### BWD history: no stored clear response

The PC1 scan covered 84 JSONL files under the two preserved application log roots and added two direct-query JSON captures. After excluding synthetic sessions, recorded-value replay, identical file copies, partial transfers, a copied Native prefix, and the diagnostic view of an existing wire log, the retained set contains **10,464 response lines from 19 sources**: 10,063 for `1039 TDG:STBH?` and 401 for `1066 TDG:STBHFLT?`. Five identical repeated response lines share their source receive record, leaving 10,459 source records. These numbers must not be described as independent new device measurements.

There are 10,204 lines containing `0x00330409` and 260 containing `0x00334408`. Both values satisfy `word & 0x300000 == 0x300000`. **No retained valid response clears either `0x100000` or `0x200000`.** The earliest included response is 2026-11-02 03:13:55.059996 UTC; the latest is 08:12:48.504 UTC. These endpoints do not describe uninterrupted observation. An unobserved clear-and-relatch between samples cannot be excluded.

The same retained history contains **44 `2018 TDG:RESBWD` transmissions and 44 same-tag empty ACKs**, with paired delays of 6–88 ms: 42 in the regular Native log and two in bounded physical diagnostics. This supports receipt of a matching response, not BWD clearance or a successful physical reset. The BWD button is decoded from **1039**, while the button callback's immediate follow-up query is **1066**. A 1066 receipt alone is not a new measurement of the main BWD button's input. [BWD history; reset callback and decoder references below.]

All 1,166 apparent zero-word responses in the unfiltered candidate set came from localhost or simulator menu tests. Another 1,257 candidate lines replayed previously recorded values. Neither group is evidence that the physical device reached BWD OK.

### Fault Reset: normal ACKs can coexist with stale STATUS

In the normal-control record, eight Fault Reset groups queued 112 priority requests. Of 32 reset writes, **31 were sent and acknowledged**, and the last `2050 RESET` was canceled when STATUS became stale. Consecutive actual STATUS replies were 41.122 seconds apart; GUI readiness was false for approximately 11.117 seconds. The saved record shows no UDP error, expired write ACK, or full reconnection in that interval.

An offline one-versus-eight-request replay reproduced priority-queue starvation: the single group retained readiness, while eight groups delayed STATUS and canceled the final reset. This supports the application queue explanation for this observed episode. It does not establish a USB-adapter fault, prove that an adapter can never fail, or establish every firmware effect of `RESET`.

The separate bounded retest sent `2044`, `2049`, `2052`, and `2050` once each. ACK delays were approximately 13.930, 34.579, 21.427, and 87.424 ms. During 60.039 seconds after the last write, `STATUS` changed from 3 to 2 and `COMSTATUS` from 1 to 0; BWD remained set. The session had four recovered query retries, two before and two after reset, with no exhausted query timeout or reconnection. Do not rewrite this as “no retries,” “every fault cleared,” or a complete physical output test.

### Native read-only soak: keep the measurement windows separate

The release completion snapshot is **1,800.553 seconds**, with 6,816 transmissions, 6,754 matched responses, 62 query retries, and no exhausted query timeout or reconnection. The later private analysis covers **1,813.567 seconds**, with 6,867 transmissions and 6,804 matches plus one request still in flight at the snapshot. These are two windows of the same session, not additional independent passes.

The later window includes 3,490 analyzed 1039 state samples without a change. Its two 1066 samples and one 1068 sample came from initialization. Therefore, “no observed BWD transition” is supported for those samples; “1066 and Opt-out were continuously re-queried for 30 minutes” is not. Read-only mode sent no device writes. The exercised menu test kept communication progressing, but does not certify every dialog or OS event path.

## Reproducibility and access

The original PE/UIR, recovered tables, oracle scripts, synthetic fixtures, and compact validation reports are tracked. Repository-only reproduction can inspect them and run the offline regression/oracle tools. For example, `analysis/verify_optout_capture.py` forbids socket creation and compares synthetic examples; its optional original-code oracle still runs emulated x86 with intercepted APIs. Running a replay does not create new physical evidence.

The logger oracle's 14 cases include 13 Python comparisons and one original-only file-open failure case. Its NI formatter and Windows text-mode newline behavior are intercepted. The decoder oracle compares selected final GUI updates and shares some parsing helpers with the Python implementation. These checks are useful correspondence evidence, not independent validation of the full scheduler, callback order, sensor calibration, or physical units.

Private raw source files and diagnostic wrappers are identified through the registry and curated manifest. They are not silently treated as repository attachments. Hashes identify retained bytes; they do not make an unavailable private file independently inspectable. Historical reports describe their own code and test snapshot. The 219 tests and seven subtests in the release validation are a release-time result, not a promise that the current documentation branch has that exact test count.

## Unknowns that remain open

| Topic | Label | Missing evidence / boundary |
|---|---|---|
| Wireshark or NIC-level packet capture | **UNKNOWN** | No PCAP or PCAPNG is present in the material available for this guide. JSONL/CSV records are application-level UDP evidence, not packet-capture files. They cannot locate loss or duplication inside the firmware, OS, network, or adapter. |
| Actual Windows XP whole-application/device run | **UNKNOWN** | The original x86 oracle is emulation; Native Windows 10/11 and Wine/QEMU results are different environments. XP GUI event delivery and device timing are not certified. |
| BWD bit-to-detector/channel wiring | **UNKNOWN** | The decoder establishes the two-bit BWD mask. A verified nameplate, matching circuit/wiring document, and measurements tying each raw bit to a physical detector/channel are absent. Do not invent a PC1/PC2 or PD1/PD2 assignment. |
| BWD reset conditions in this installed firmware | **UNKNOWN** | Matching ACKs with retained set bits do not reveal which physical prerequisite, latch, sensor input, or firmware rule prevented clearance. A manual from another model does not close this gap. |
| Complete SASC firmware protocol | **UNKNOWN** | The observed SASC identity and recovered GUI commands are not an authoritative firmware implementation/specification for every module revision. Unsupported `-99` and empty replies are not valid zero measurements. |
| Installed replacement pump and wiring | **UNKNOWN** | The installed replacement-pump model, trigger/shutter/interlock wiring, electrical levels, and fault propagation have not been verified. Matching model and wiring documents plus supervised measurements are needed to establish the installed hardware path. |
| Actual optical output and calibration | **UNKNOWN** | No independent optical detector, pulse-energy measurement, oscilloscope trace, or sensor calibration is part of this evidence. A button, LED, ACK, or numeric display is not that measurement. |
| Arbitrarily delayed same-tag replies | **UNKNOWN** | Replies have no unique transaction identifier. A late response carrying the currently requested tag cannot always be distinguished; successful bounded tests do not remove this protocol limit. |
| Unobserved intervals and reset transients | **UNKNOWN** | The retained set has sampling and session gaps. “No clear response stored” does not mean that BWD was set at every instant. |

## Citation anchors

- Original application identity: `SPITFIRE.EXE` SHA256 `8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b`; immutable baseline and other resource hashes are in the manifest. Original `_gextHandleReceivedMsg` at `0x40ba24`, `_BW_reset` at `0x40f0b7`, and Reset callback at `0x412428` are executable-address citations, not Windows event traces.
- Release 1.0 implementation baseline: [`cebcc284` callbacks, line 203](https://github.com/El-Carretero/PY_SPF/blob/cebcc28490f48e9e5d4d1c2e2feef34d638244e7/spitfire/callbacks.py#L203) and [fault follow-up sequence, line 321](https://github.com/El-Carretero/PY_SPF/blob/cebcc28490f48e9e5d4d1c2e2feef34d638244e7/spitfire/callbacks.py#L321); [decoder BWD mask and labels, line 323](https://github.com/El-Carretero/PY_SPF/blob/cebcc28490f48e9e5d4d1c2e2feef34d638244e7/spitfire/decoders.py#L323). Use the [branch baselines](evidence/branch_baselines.json) for the other immutable object IDs.
- Reset-history source anchors: the two bounded 2018 sends are raw-wire lines 296/297 and 293/294 in the respective diagnostic sources; regular Native entries retain their own source line numbers. The curated manifest identifies source hashes; a private line reference is not a claim that the raw log is tracked.
- Manual claims elsewhere in this guide must cite the registered document ID plus both printed and PDF page numbers. They retain the **MANUAL** label until a code or matching physical observation independently supports a claim about this installed system.

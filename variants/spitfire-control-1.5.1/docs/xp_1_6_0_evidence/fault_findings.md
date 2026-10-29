# XP 1.6.0 fault/status review (read-only binary analysis)

The supplied ZIP contains installers and compiled NI LabWindows/CVI EXE/UIR resources, not C source. No original binary was executed and no hardware was accessed. This is static control/data-flow evidence, not runtime equivalence certification.

## Reproducible inputs

- ZIP SHA-256: bd35c7b4ffe8bc2cb663c3914bd37217fb04f67abf8ef3730f0bfd49dd8b59d8.
- SPITFIRE.EXE (and identical SPITFIRE.EXE2): 271360 bytes, SHA-256 8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b.
- SPITFIRE.UIR: 152636 bytes, SHA-256 1c5b82a8cf528934bffffe0989a73312059b07a15fc3056df8fbeb41607bd67b.
- Reproduction script: extract_fault_evidence.py. Output: fault_binary_evidence.json.
- Command strings: 90 query slots at EXE file offset 0x30b70, 56 write slots at 0x315fc, each 30 bytes. All 146 exactly match current commands.py. Matching strings alone does not prove matching program behavior.

## P1: old fault mapping used the wrong UIR control number

UIR record IDs are one less than the runtime control IDs passed to SetCtrlVal. Independent crosschecks:

| Reply / action | EXE runtime ID | UIR stored ID and tag |
| --- | ---: | --- |
| 1021 HV state | INFO 34 | 33 HV_ON |
| 1025 divisor | INFO 43 | 42 DIV_ST |
| 1065 measured oscillator | INFO 7 | 6 OSC_ST |
| 1039 BWD reset display | MAIN 5 | 4 CMD_BWD_RESET |
| TDG communication indicator | MAIN 13 | 12 COMM_TDG |
| Empower RUN indication | MAIN 22 | 21 LEDRUN |

The old Python FAULT_WORD_BITS used stored IDs directly. This shifted fault labels and incorrectly made EMP:FAULT? look like a mixture containing TDG/TCU faults. In the original decoder, all identified 1014 fields are Empower indicators. Hardware protection faults must be obtained from their actual separate status queries.

`_decode_faults` at VA 0x40a5c5 parses four decimal fields using atoi, then applies these mappings (word index starts at zero):

| Word | Mask / value | Runtime control | Actual UIR tag |
| ---: | --- | ---: | --- |
| 0 | 0x40 | 18 | LEDVSWR |
| 0 | 0x20 | 11 | LEDQSWUTEMP |
| 0 | 0x10 | 16 | LEDPROT |
| 0 | 0x08 | 24 | LEDOVERPWR |
| 0 | 0x02 | 25 | LEDDROVERTEMP |
| 0 | 0x01 | 32 | LEDARRAYOT |
| 1 | 0x80 | 6 | LEDH2O |
| 1 | 0x40 | 7 | LEDDOOR |
| 1 | 0x20 | 13 | LEDKEYSW |
| 1 | 0x10 | 34 | LEDKILLSW |
| 1 | 0x08 | 30 | LEDOVERVOLT |
| 1 | 0x04 | 12 | LEDOVERCURR |
| 1 | 0x02 | 17 | LEDUNDERFREQ |
| 2 | 0x10 | 15 | LEDCOMM |
| 2 | 0x02 | 3 | LEDLBOUNDTEMP |
| 2 | 0x01 | 35 | LEDARRAYOP |
| 3 | entire nonzero scalar | 2 | LEDLBOSTABILITY |

The fourth value is also assigned to `_LBO_STAB_FAULT`, independently confirming its meaning. It is not established as an 8-bit mask; code must not truncate it to 0xff. No 1014 mapping for checksum was recovered. Unmapped values should not acquire invented labels.

## P1/P2: TDG status replies are hexadecimal

Original reply cases 1039 at 0x40cb20 and 1066 at 0x40cb4b call sscanf with `%x` strings at 0x436b80 and 0x436b7c. Python generic decimal parsing was wrong for a bare numeric-looking hex response (e.g. `2000`) and rejected hex containing A-F.

Use bounded unsigned 32-bit hexadecimal parsing for those IDs. Preserve the raw string. Do not change 1013, 1015, 1019, 1028, 1029, 1057 or 1088 to hexadecimal: those original cases use atof_FLTREG_ at 0x403ca0. 1089 uses decimal atoi. Mixed 1014 uses four decimal atoi fields.

## Actual protection sources

`_decode_tdg_stbh_nom` at 0x410053, called by 1066:

| Hex bit | Runtime control | Tag |
| --- | ---: | --- |
| 0x0800 | 21 | TDG_SYS |
| 0x1000 | 14 | TDG_HEAD |
| 0x2000 | 19 | TDG_USER |
| 0x4000 | 23 | TDG_KEY |
| 0x8000 | 22 | TDG_RELAY |

`_ecu_stbh_decode_fault` at 0x4099d9, called by decimal 1088:

| Bit in low byte | Runtime control | Tag |
| --- | ---: | --- |
| 0x04 | 8 | TECOVERTEMP |
| 0x10 | 10 | HUMIDITY_LATCH |

1088 is an ECU status register, not a pure fault word. Do not treat every nonzero status bit as a fault without evidence.

1089 COMSTATUS decimal handler at 0x40c343:

| Bit | Runtime control | Tag |
| --- | ---: | --- |
| 0x01 | 20 | MAIN_COM |
| 0x02 | 5 | TDG_COM |
| 0x04 | 9 | EMP_COM |
| 0x08 | 4 | TCU_COM |

Both 1014 LEDCOMM and 1089 EMP_COM are distinct original indicators; a consolidated Empower communication display should combine their information without allowing one zero to erase the other fault. External Pump can exclude the Empower-specific communication bit after profile exclusion, but must retain main/TDG/TCU bits and unknown communication bits.

## BWD and PD indication

1039 handler calls `_decode_tdg_stbh` at 0x41023e:

- `status & 0x00300000 == 0`: original labels MAIN control 5 `BWD OK`; nonzero selects `RESET BWD`.
- `status & 0x00010000 == 0`: lights PD1 (runtime MAIN 27, stored UIR 26).
- `status & 0x00020000 == 0`: lights PD2 (runtime MAIN 26, stored UIR 25).
- Combined mask 0x00330000 covers the proven latch/PD failure conditions.
- These are protection indicators, not a measurement of phase lock or optical pump arrival.

The 1019 module communication bit remains 0x800: original `_MSB` shifts right 8 and `_tdg_stb_decode` ANDs with 8. The same byte-extraction method is used by other module status decoders.

## Scope and remaining uncertainty

The original UI does not define the firmware's behavior at 10 Hz or prove optical synchronization. No supported raw-measurement semantics for TDG:TRIG? were recovered here. Preserve unrecognized status values and clearly mark unavailable data. Source-level checks and simulator tests cannot certify timing jitter, pulse energy, interlocks, or firmware opt-out behavior on the actual apparatus.

# Spitfire GUI resource recovery

The uploaded installer contains a native 32-bit LabWindows/CVI application. The GUI is completely represented by SPITFIRE.UIR and SERVER.UIR. No source instructions were executed. Callback strings were treated as program metadata.

## Verified inventory

SPITFIRE.UIR has nine panels, 230 controls, one menu bar with three menus and six items, 89 data-binding records, and two timer records. SERVER.UIR has one panel and 14 controls. The original application uses global resource IDs in RSRC, but loaded CVI controls use `local_index + 1`. The separate server panel therefore shares numerical control IDs with application panels; the Python adapter uses the `server` namespace.

| Resource ID | Constant | Title | Width × height |
|---|---|---|---|
| 1 | PROG | Programmer | 375 × 275 |
| 2 | WdCCU | Temperature Control | 480 × 250 |
| 3 | WdFAULTS | Active Faults | 720 × 580 |
| 4 | WdHELP | Help | 500 × 277 |
| 5 | WdINFO | Timing and High Voltage | 390 × 446 |
| 6 | WdMAIN | Spitfire | 895 × 550 |
| 7 | WdSECRETS | Compressor | 259 × 267 |
| 8 | WdSECRETS2 | Empower Service | 640 × 375 |
| 9 | WdSETUP | Empower Setup | 544 × 222 |
| SERVER 1 | MAINPNL | TCP Server Console | 383 × 465 |

Application startup and access-level changes subsequently resize panels and change visible controls. These resource dimensions are the original defaults, not all final application states.

## Static resource format

The UIR files use a big-endian NI RSRC container. The file header stores the resource-map offset at byte 16 and the data-section offset at byte 24. Each resource type has a list of 20-byte entries containing resource ID, name offset, flags, data offset, and a preserved pointer field. Resource payloads are length-prefixed.

The DLG3 payload stores a compression flag, uncompressed size, another preserved integer, then zero-mask8 compressed data. The first `ceil(uncompressed_size / 8)` compressed bytes are presence masks, one least-significant-first bit per uncompressed byte. Remaining bytes are the nonzero values. This was validated by consuming every encoded byte and exactly reproducing every stated uncompressed length.

The decoded DLG3 panel header stores the control count at byte 64. Records start at byte 68 and contain a total length, aligned Pascal class name, child count, and length/tag child records such as DDOD, Labl, MLbl, BCos, and Cosm. The terminal permutation maps a control's one-based local index to drawing index as:

`drawing_index = control_count - 1 - permutation[local_index - 1]`

All 230 mappings were checked against expected control labels/classes. Labl and MLbl have different font metadata offsets and string encodings; these are decoded in build_gui_spec.py. pVAl supplies typed defaults/ranges and ring choices. The ring lists preserve both labels and their numerical values (e.g. motor FAST=90, NORMAL=30, SLOW=10, VERY SLOW=5).

Native callback names are cleared only in copied resources so Python can install callbacks after LoadPanel. Framed metadata records have a checksum `((sum(body_bytes) & 0xffffff) << 8) | (body_length & 0xff)`, where body starts after the 12-byte length/checksum/tag header. The patch preserves payload lengths, resource offsets, constants, drawings, and bitmap data. The native runtime successfully loaded the patched resources.

## Runtime verification and implementation

The supplied CVI runtime has an embedded attribute symbol table; extract_runtime_attrs.py recovered 317 attribute IDs and types. A separate agent ran the original 32-bit runtime under Wine/QEMU and exported all panel/control attributes, native control sprites, both Boolean values, blank-label button backgrounds, and the server panel. The measured metadata is merged into `spitfire/resources/gui_spec.json` and `server_gui_spec.json`.

`spitfire/gui.py` implements the portable Qt view. It retains original positions and native static artwork. Main-panel coordinates include the CVI menu bar, which requires subtracting the Qt menu height inside the canvas. Its public API uses runtime control IDs. Real Qt input events emit original CVI event numbers: commit 1, left click 3, left double-click 4, right click 5, right double-click 6. Release signals stop held motor movement; Escape emits the original escape byte.

The unmodified initial Qt main panel matched 99.699378% of the original runtime capture's panel pixels, with mean absolute RGB error 0.219548/255, excluding the platform-specific menu bar. This validates initial placement/artwork, not complete behavioral equivalence. The portable view uses Qt for changing text, numeric values, dragging, and selection, and therefore is a preview/fallback rather than a complete native rendering replacement. The root agent's Windows CVI adapter is the fidelity backend.

Seven Qt tests pass: original-runtime snapshot, run hold/release, stop/Escape, motor reverse/forward/stop/jog, numeric drag/commit, dynamic labels/colors/visibility/menu state, and server transmit/reset with its separate panel namespace. No physical laser connection was used.

## Artifacts

- `work/analysis/parse_uir.py`: generic resource parser.
- `work/analysis/build_gui_spec.py`: decoded drawing/defaults/control mapping.
- `work/analysis/prepare_native_resources.py`: callback-free copied UIR and binding recovery.
- `work/analysis/extract_runtime_attrs.py`: runtime attribute table extraction.
- `work/analysis/merge_runtime_gui.py`: measured-attribute/native-sprite merge.
- `work/spitfire_python/spitfire/gui.py`: Qt view.
- `work/spitfire_python/tests/test_qt_interactions.py`: actual event integration checks.
- `work/spitfire_python/tests/test_qt_snapshot.py`: original runtime pixel baseline.

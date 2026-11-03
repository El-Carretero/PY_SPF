# Resource callback coverage audit

Audit input: recovered `resources/callback_bindings.json`, `resources/gui_spec.json`, original executable's callback functions, and current `callbacks.py` / `controller.py`.

- **100 resource bindings, 89 distinct callback names.**
- **100/100 bindings resolve to implemented Python dispatcher paths.**
- **No missing dispatcher names and no unhandled emitted action kinds in `Controller.apply`.**
- Both timer callbacks explicitly support event15. Main panel key handling supports event7, server close supports event11. Menu callbacks use their original no-control-event semantics.
- `hide_emp_controls` / `show_emp_controls` set main control19 visibility. `hide_ecu_controls` / `show_ecu_controls` mutate main16, ECU16, ECU15 visibility and always enqueue query1032, exactly as functions0x40fef5..0x410053.
- MainCallBack event7 emits `key_pressed` with eventData1's low byte; controller delegates to the original access-sequence handler. The panel callback ignores unrelated events, matching the executable.
- SERVER TransmitCB, ClearScreenCB, and MainPanelCB have paths for transmit, reset-text-box, and close. Controller now handles server_write/reset_textbox/key_pressed explicitly.

The executable's runtime control IDs differ from the UIR archive's resource IDs. Runtime control ID = `local_index + 1`. Examples: ECU SET_TEMP resource9 -> runtime7; main mouse timer resource137 -> runtime4; info divisor resource129 -> runtime43. The extraction scripts and final callback bindings have been corrected to retain both `control` (runtime) and `resource_id`.

`SERVER.UIR` panel1 is a separate panel from `SPITFIRE.UIR` programmer panel1. GUI adapters must preserve the resource namespace; passing a distinct server panel identifier through dispatch/read/set is supported. SERVER normalized IDs are string input3, transmit echo2, received text4, clear7, escape12. Evidence is `server_gui_spec.json`.

`callback_coverage.json` provides one record per binding, its source namespace, source/runtime IDs, tested activation events, emitted action kinds, and unresolved action kinds (currently none). The audit invokes only pure Python callback translation with values0/1 and connected states0/1. It verifies binding completeness and adapter dispatch coverage; it does not establish original-vs-port behavior equivalence or hardware conformance. Rendering adapters are being integrated separately.

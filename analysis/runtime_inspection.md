# Native GUI inspection and Python backend

The supplied Windows x86 CVI runtime successfully loaded and rendered the original drawing resources under Python. `spitfire/native.py` implements the native view used by the Python controller, without executing SPITFIRE.EXE or its application callbacks.

## Proven initialization and ABI

- `ctypes.WinDLL(cvirte.dll)` for fixed-argument CVI functions (stdcall).
- `ctypes.CDLL(cvirte.dll)` for `SetCtrlVal`, `SetCtrlAttribute`, `SetPanelAttribute`, and `SetMenuBarAttribute` (C varargs).
- `InitCVIRTDll(GetModuleHandleW(NULL), NULL, 0, NULL, 0, NULL, 0, NULL, 0, NULL, NULL)` returned 1.
- `LoadPanel(0, callback_free_original_UIR, resource_panel_id)` loaded every original panel.
- Python callbacks use `CFUNCTYPE` (cdecl), matching original callbacks' plain RET instructions. Control callback: six arguments; panel callback: five; menu callback: four.
- CVI event 7 is keypress; original MainCallBack reads its low byte. Event 8 is focus, not close. Original server MainPanelCB handles close event 11.
- Native menu IDs: EXITx 3, SETUPx 5, FAULTSx 6, INFOx 7, ECUx 8, ABOUTx 10.
- Main timer control 64: DataLogger, interval 1.0 seconds, enabled. Main control 4: mouse timer, interval 0.05 seconds, initially disabled. Native timers suppress synthesized controller timer events.

## Runtime resources without an administrator install

CVI expects `bin/cvirte.rsc`, message files, and `fonts/ni7seg.ttf` / `fonts/nisystem.ttf`. A temporary process-local `RegOverridePredefKey` view supplies the original legacy runtime locator `Software\National Instruments\CVI Run-Time Engine\4.0.1`, value `cvidir`. It restores the process registry view and removes its temporary HKCU branch after initialization; it does not write HKLM or the Windows system directory. This was tested with the Wine system CVI resource directory absent.

If package resources are read-only, the backend copies the runtime into `LOCALAPPDATA/SpitfirePython/runtime-7.1`. A read-only source-directory smoke test verified both required resource subdirectories in the cache.

## Final integrated verification

See the retained [Native GUI validation record](native_gui_validation.json), including the CLI proof, shutdown result and environment.

- All nine original Spitfire panels plus the original TCP Server Console loaded, displayed, and hid.
- Access levels 0, 1, 2, and 3 applied without CVI attribute errors.
- Python controller connected to its development simulator and updated original controls.
- Real XTest mouse input on the native motor control generated exactly one `[2009]HED:MOTOR:REW` and one `[2013]HED:MOTOR:STOP` on release.
- Real native menu input invoked `exit_from_menu`; the final CLI closed normally with exit code 0.
- Separate real UI tests invoked `show_help` through Help/About and `[2028]OFF` through STOP.
- Final CLI proof reports no CVI callback errors.
- No physical instrument was connected or tested. Simulator output does not establish physical firmware behavior.

The native CLI preserves the original bootstrap's lifecycle: stop controller, close CVI panels/runtime, flush streams, then Win32 `ExitProcess(code)`. Errors print a traceback and use code 1; keyboard interruption uses 130. This native process boundary matters because normal Python finalization after an interactive session could fault under this emulator with the legacy NI runtime. `NativeGui.close()` itself remains callable without terminating an embedding process. A standalone load/close smoke test exited 0.

## Extraction artifacts

- `work/runtime/gui_export/gui_attributes.json`: all nine panels and 230 control attributes.
- `work/runtime/gui_export_states`: original control sprites plus 0/1 state variants for 114 controls (459 files including metadata).
- `work/runtime/server_export`: the original SERVER.UIR panel, control attributes, and sprites.
- `work/runtime/gui_export_blank`: command button sprites with their labels cleared, preserving native gradients for dynamic Qt labels.
- `work/runtime/main-reference.png`: the original native drawing resource loaded directly in Python.
- `work/runtime/python-native-connected.png`: the original drawing engine driven by the Python controller in simulator mode.

The UI extraction agent merged these attributes and sprites into the portable Qt backend.

## Reproducible environment

The host is Debian 13 with no native IA32 execution. Direct WoW64 execution faults before the PE entrypoint, so inspection used Kron4ek Wine 10.0 x86, Debian QEMU user 10.0.13, Windows CPython 3.11.9 x86 from NuGet, and Xorg 1.21.1.16 with the dummy driver on display :97. QEMU 7.2 could not handle Wine's syscall path; QEMU 10 resolved it. An explicit Wine preloader and a small guest `execv` shim keep child Wine processes under QEMU.

The final validator executed the actual `native.run(opts)` path using:

```sh
DISPLAY=:97 \
WINEPREFIX=/workspace/work/runtime/prefix32 WINEARCH=win32 \
WINEDLLOVERRIDES=mscoree,mshtml= WINEDEBUG=-all \
QEMU_SET_ENV=LD_PRELOAD=/workspace/work/runtime/execshim.so \
PYTHONHOME='Z:\workspace\work\runtime\pythonx86\tools' \
work/runtime/wine-10.0-x86/bin/wine \
  'Z:\workspace\work\runtime\pythonx86\tools\python.exe' \
  'Z:\workspace\work\runtime\native_cli_validate.py'
```

The validator wraps the view only to record evidence and exercise access levels/panels. Normal Windows use is `python -m spitfire --backend native --demo --tcp-port 0` with 32-bit Python. Neither Qt nor Wine/QEMU is a native Windows runtime dependency.

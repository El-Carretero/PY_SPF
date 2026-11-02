# Supplied vendor runtime and resources

`spitfire/resources/runtime/` contains National Instruments runtime files and fonts extracted from the user's uploaded installer. `SPITFIRE.UIR` and `SERVER.UIR` originate in that same installer; only callback bindings have been adapted. Original binary hashes are recorded in `analysis/cab_manifest.json`.

These vendor files retain their existing ownership and license terms. This reconstruction does not relicense them. Ghidra, Wine, QEMU, Unicorn and other analysis executables are not included in the application package. PySide6 is an optional separately installed GUI dependency; it is not required by the native Windows adapter.

## Standalone Windows distribution

The Native Windows bundle also contains CPython and the PyInstaller bootloader.
The build copies the selected Python distribution's `LICENSE.txt` and the actual
PyInstaller license/bootloader exception text into `THIRD_PARTY_NOTICES/` beside
the executable. `bundle-manifest.json` identifies the exact build tools, sources,
DLL imports and file hashes. These packaging notices do not change the ownership
or license terms of the supplied NI runtime, fonts or UIR resources.

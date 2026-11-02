# Native-only, app-local Windows x86 distribution. Build through build.ps1.
from pathlib import Path
import struct
import sys


if sys.platform != "win32" or struct.calcsize("P") != 4:
    raise SystemExit("Build PY_SPF with 32-bit Windows Python.")

ROOT = Path(SPECPATH).resolve().parents[1]
PACKAGE = ROOT / "spitfire"
RESOURCES = PACKAGE / "resources"
ENTRYPOINT = ROOT / "packaging" / "windows" / "native_app.py"
if not ENTRYPOINT.is_file():
    raise SystemExit(f"Missing native entrypoint: {ENTRYPOINT}")

datas = [(str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")]
for name in ("SPITFIRE.UIR", "SERVER.UIR", "gui_spec.json", "server_gui_spec.json",
             "cvi_attributes.json", "callback_bindings.json"):
    datas.append((str(RESOURCES / name), "spitfire/resources"))

# Diagnostics identifies these exact sources on disk even in a frozen build.
for name in ("native.py", "native_ticker.py", "controller.py", "protocol.py"):
    datas.append((str(PACKAGE / name), "spitfire"))

vendor_dlls = []
for source in sorted((RESOURCES / "runtime").rglob("*")):
    if not source.is_file():
        continue
    destination = Path("spitfire/resources/runtime") / source.relative_to(RESOURCES / "runtime")
    if source.suffix.lower() == ".dll":
        vendor_dlls.append((destination.as_posix(), str(source), "DATA"))
    else:
        datas.append((str(source), destination.parent.as_posix()))

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["spitfire.native", "spitfire.native_ticker",
                   "spitfire.frozen", "spitfire.packaged_check"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "PyQt6", "PyQt5", "shiboken6", "spitfire.gui",
              "tkinter", "matplotlib", "numpy", "pytest", "unicorn", "capstone"],
    noarchive=False,
    optimize=0,
)

# Append after Analysis: PyInstaller otherwise reclassifies PE data as binaries
# and may resolve optional NI plugin imports from an installed system runtime.
# Keep the supplied vendor tree intact without collecting host-installed NI.
vendor_names = {Path(row[0]).name.casefold() for row in vendor_dlls}
foreign_ni_names = {"nidscmem.dll", "instrsup.dll", "cvi_lvrt.dll", "cvi.dll"}
for destination, source, kind in a.binaries:
    if Path(destination).name.casefold() in vendor_names | foreign_ni_names:
        raise SystemExit(f"Refusing a vendor DLL collected from the host: {destination}")
a.datas.extend(vendor_dlls)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PY_SPF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    contents_directory="_internal",
    uac_admin=False,
    manifest=str(ROOT / "packaging" / "windows" / "native.manifest"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PY_SPF")

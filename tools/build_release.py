"""Build the current reconstruction's wheel, source ZIP and SHA256 manifest.

Run with the development venv Python from a Git checkout. No app is launched.
The source ZIP excludes old releases, local environments and ignored files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    version = re.search(r'^version = "([^"]+)"',
                        (ROOT / "pyproject.toml").read_text(), re.M)[1]
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    wheel_name = f"spitfire_gui_reconstruction-{version}-py3-none-any.whl"
    wheel = output / wheel_name
    if wheel.exists():
        wheel.unlink()
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps",
                    "--wheel-dir", str(output), str(ROOT)], check=True)
    if not wheel.is_file():
        raise RuntimeError(f"Expected wheel was not produced: {wheel_name}")
    with zipfile.ZipFile(wheel) as installed:
        # The native backend needs the complete bundled resource tree, not
        # only Python modules. Check nested runtime bin/fonts as well.
        for resource in (ROOT / "spitfire/resources").rglob("*"):
            if resource.is_file() and "__pycache__" not in resource.parts:
                name = resource.relative_to(ROOT).as_posix()
                if installed.read(name) != resource.read_bytes():
                    raise RuntimeError(f"Wheel resource differs: {name}")

    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")
    archive = output / f"PY_SPF_{version}.zip"
    prefix = f"PY_SPF_{version}/"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(set(paths)):
            if not name or name.startswith("output/") or not (ROOT / name).is_file():
                continue
            data = (ROOT / name).read_bytes()
            if name.endswith(".bat"):
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            bundle.writestr(prefix + name, data)
        bundle.write(wheel, prefix + "output/" + wheel.name)
        bundle.write(output / "README.md", prefix + "output/README.md")
    installer_fix = output / f"PY_SPF_{version}_installer_fix.zip"
    with zipfile.ZipFile(installer_fix, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in ("install.bat", "run_native.bat", "run_demo.bat", "tools/install_windows.ps1"):
            data = (ROOT / name).read_bytes()
            if name.endswith(".bat"):
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            bundle.writestr(name, data)
        bundle.writestr("README-install-fix.txt",
                        "Extract into the existing PY_SPF project folder and replace files.\r\n"
                        "Run install.bat again. Keep existing Python and venv folders.\r\n")
    manifest = {}
    for artifact in (archive, wheel, installer_fix):
        data = artifact.read_bytes()
        manifest[artifact.name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    (output / "SHA256.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

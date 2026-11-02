[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OutputDirectory,
    [string]$BuildDirectory,
    [string]$BuildEnvironment,
    [string]$InnoCompilerPath,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This build requires Windows and an existing 32-bit Python 3.11 or 3.13."
}
$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $PSScriptRoot "dist" }
if (-not $BuildDirectory) { $BuildDirectory = Join-Path $PSScriptRoot "build" }
if (-not $BuildEnvironment) { $BuildEnvironment = Join-Path $RepoRoot ".venv-build-win32" }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$BuildDirectory = [IO.Path]::GetFullPath($BuildDirectory)
$BuildEnvironment = [IO.Path]::GetFullPath($BuildEnvironment)

function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    $Executable = (Get-Command -Name $File -CommandType Application -ErrorAction Stop | Select-Object -First 1).Path
    $PreviousErrorAction = $ErrorActionPreference
    $NativeExitCode = $null
    # Windows PowerShell 5 turns redirected stderr into NativeCommandError
    # records. PyInstaller writes ordinary INFO messages there; its exit code
    # still determines success. Clear the old code so launch failure cannot
    # accidentally inherit a previous successful command's zero.
    $global:LASTEXITCODE = $null
    try {
        $ErrorActionPreference = "Continue"
        & $Executable @Arguments
        $NativeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousErrorAction
    }
    if ($null -eq $NativeExitCode) { throw "$File did not return a native exit code." }
    if ($NativeExitCode -ne 0) { throw "$File failed with exit code $NativeExitCode" }
}

$ProbeCode = "import json,struct,sys; print(json.dumps(dict(bits=struct.calcsize('P')*8,major=sys.version_info.major,minor=sys.version_info.minor,venv=sys.prefix!=sys.base_prefix)))"
$ProbeText = & $Python -I -c $ProbeCode
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect the selected Python interpreter." }
$RuntimeInfo = ($ProbeText -join "`n") | ConvertFrom-Json
if ($RuntimeInfo.bits -ne 32 -or $RuntimeInfo.major -ne 3 -or $RuntimeInfo.minor -notin @(11, 13)) {
    throw "Select 32-bit Windows Python 3.11 or 3.13 with -Python C:\path\python.exe."
}
$BuildPython = Join-Path $BuildEnvironment "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $BuildPython -PathType Leaf)) {
    Invoke-Checked -File $Python -Arguments @("-I", "-m", "venv", $BuildEnvironment)
}
$VenvText = & $BuildPython -I -c $ProbeCode
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect the private build venv." }
$VenvInfo = ($VenvText -join "`n") | ConvertFrom-Json
if (-not $VenvInfo.venv -or $VenvInfo.bits -ne 32 -or $VenvInfo.minor -ne $RuntimeInfo.minor) {
    throw "The existing build venv does not match the selected x86 interpreter; select a new -BuildEnvironment."
}
if (-not $SkipDependencyInstall) {
    Invoke-Checked -File $BuildPython -Arguments @("-I", "-m", "pip", "--disable-pip-version-check", "--require-virtualenv", "install", "-r", (Join-Path $RepoRoot "requirements-build.txt"))
}
Invoke-Checked -File $BuildPython -Arguments @("-I", "-c", "import PyInstaller; assert PyInstaller.__version__=='6.16.0', 'Use the pinned build requirements'")
New-Item -ItemType Directory -Force -Path $OutputDirectory, $BuildDirectory | Out-Null

# Generated helper is a build artifact; it does not install or register anything.
$AuditScript = Join-Path $BuildDirectory "audit_bundle.py"
@'
from pathlib import Path
from importlib import metadata
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import pefile

root, bundle = map(Path, sys.argv[1:3])
if not (bundle / "PY_SPF.exe").is_file():
    raise SystemExit("Missing onedir executable")
# CVI checks EXE-adjacent cvirte resources before any system/registry runtime.
# PyInstaller's normal data destination is _internal, so stage these explicitly.
private_resources = {
    "bin": ("cvirte.rsc", "msgrte.txt", "cvierror.txt"),
}
for folder, names in private_resources.items():
    for name in names:
        source = root / "spitfire/resources/runtime" / folder / name
        target = bundle / "cvirte" / folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise SystemExit(f"Private EXE-adjacent CVI resource differs: {folder}/{name}")
# CVI's old AddFontResourceA registers disk fonts globally and can leave font
# cache locks after a normal exit. The frozen entrypoint instead loads these
# unmodified vendor fonts privately from memory before loading CVI. Existing
# regular-file placeholders satisfy CVI's file-existence check; they are not
# fonts, so its legacy global AddFontResourceA call fails harmlessly.
font_source = ast.parse((root / "spitfire/private_fonts.py").read_text(encoding="utf-8"))
font_placeholder = next(ast.literal_eval(node.value) for node in font_source.body
                        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "FONT_PLACEHOLDER" for target in node.targets))
if not isinstance(font_placeholder, bytes) or not font_placeholder:
    raise SystemExit("The private font placeholder must be a nonempty bytes literal")
for name in ("ni7seg.ttf", "nisystem.ttf"):
    source = root / "spitfire/resources/runtime/fonts" / name
    original = bundle / "_internal/spitfire/resources/runtime/fonts" / name
    if not original.is_file() or original.read_bytes() != source.read_bytes():
        raise SystemExit(f"Private memory font source missing or changed: {name}")
    target = bundle / "cvirte/fonts" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(font_placeholder)
    if target.read_bytes() != font_placeholder:
        raise SystemExit(f"CVI font compatibility placeholder differs: {name}")
notices = bundle / "THIRD_PARTY_NOTICES"
notices.mkdir(exist_ok=True)
shutil.copyfile(root / "THIRD_PARTY_NOTICES.md", bundle / "THIRD_PARTY_NOTICES.md")
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if not python_license.is_file():
    raise SystemExit("Cannot locate the selected Python redistribution license")
shutil.copyfile(python_license, notices / "Python-LICENSE.txt")
dist = metadata.distribution("PyInstaller")
licenses = [p for p in dist.files or () if p.name.casefold() in {"copying.txt", "license.txt", "license"}]
if not licenses:
    raise SystemExit("Cannot locate the PyInstaller bootloader license")
for index, license_file in enumerate(licenses):
    shutil.copyfile(dist.locate_file(license_file), notices / f"PyInstaller-{index}-{license_file.name}")

system = set("advapi32 bcrypt cabinet cfgmgr32 comctl32 comdlg32 crypt32 cryptbase cryptsp dbghelp dnsapi dwmapi gdi32 imm32 iphlpapi kernel32 kernelbase mpr mscoree msasn1 msvcp60 msvcrt ncrypt netapi32 normaliz ntdll ole32 oleacc oleaut32 pdh powrprof propsys psapi rpcrt4 secur32 setupapi shell32 shcore shlwapi sspicli ucrtbase user32 userenv version win32u windowscodecs winhttp wininet winmm winsock winspool ws2_32 wsock32 wtsapi32".split())
vendor = root / "spitfire/resources/runtime"
bundled_names = {p.name.casefold() for p in bundle.rglob("*") if p.is_file()}
foreign_ni = {"nidscmem.dll", "instrsup.dll", "cvi_lvrt.dll", "cvi.dll"} & bundled_names
if foreign_ni:
    raise SystemExit(f"Unexpected host NI dependency in bundle: {sorted(foreign_ni)}")
pe_records, missing = [], []
for path in sorted(bundle.rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(bundle).as_posix()
    if any(name in relative.casefold() for name in ("pyside", "pyqt", "shiboken")):
        raise SystemExit(f"Unexpected Qt dependency in Native-only bundle: {relative}")
    if path.suffix.casefold() not in {".exe", ".dll", ".pyd"}:
        continue
    pe = pefile.PE(str(path), fast_load=True)
    if pe.FILE_HEADER.Machine != 0x14c or pe.OPTIONAL_HEADER.Magic != 0x10b:
        raise SystemExit(f"Non-x86 PE in bundle: {relative}")
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"], pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
    imported = sorted({entry.dll.decode("ascii").casefold() for table in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT") for entry in getattr(pe, table, ())})
    pe.close()
    for dll in imported:
        if dll in bundled_names or Path(dll).stem in system or dll.startswith(("api-ms-win-", "ext-ms-win-")):
            continue
        record = dict(file=relative, dependency=dll)
        # Supplied optional USI plugin is not an import of cvirte.dll. Do not
        # resolve it from host-installed NI software or claim it is complete.
        if path.name.casefold() == "cviusi.dll" and dll == "nidscmem.dll":
            record["disposition"] = "unresolved supplied optional USI plugin; not collected from host"
            missing.append(record)
        else:
            raise SystemExit(f"Unresolved non-system dependency: {relative} -> {dll}")
    pe_records.append(dict(file=relative, machine="I386", optional_header="PE32", imports=imported))
for source in sorted(vendor.glob("*.dll")):
    target = bundle / "_internal/spitfire/resources/runtime" / source.name
    if not target.is_file() or target.read_bytes() != source.read_bytes():
        raise SystemExit(f"Vendor DLL missing or changed: {source.name}")
try:
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
except (OSError, subprocess.CalledProcessError):
    commit = None
source_paths = sorted((root / "spitfire").glob("*.py")) + [root / "packaging/windows/native_app.py", root / "packaging/windows/native.manifest", root / "packaging/windows/PY_SPF.spec", root / "packaging/windows/build.ps1", root / "requirements-build.txt"]
files = [dict(path=p.relative_to(bundle).as_posix(), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(bundle.rglob("*")) if p.is_file() and p.name != "bundle-manifest.json"]
manifest = dict(schema=1, application="PY_SPF", package_version="1.0.0", original_ni_gui_version="1.6.0", layout="onedir", architecture="x86", font_strategy="original vendor TTFs retained internally for process-private memory loading; EXE-adjacent .ttf names are non-font ASCII compatibility placeholders", python=sys.version, build_tools={name:metadata.version(name) for name in ("PyInstaller", "pyinstaller-hooks-contrib", "altgraph", "packaging", "pefile", "pywin32-ctypes", "setuptools")}, source_commit=commit, source_sha256={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}, files=files, pe_files=pe_records, unresolved_optional_dependencies=missing, validation_scope="static build audit only; execution/install/uninstall verification is separate")
(bundle / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Audited {len(files)} files and {len(pe_records)} x86 PE images; manifest: bundle-manifest.json")
'@ | Set-Content -LiteralPath $AuditScript -Encoding UTF8

$OldConfigDirectory = [Environment]::GetEnvironmentVariable("PYINSTALLER_CONFIG_DIR", "Process")
try {
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildDirectory "pyinstaller-cache"
    Push-Location $RepoRoot
    try {
        Invoke-Checked -File $BuildPython -Arguments @("-I", "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $OutputDirectory, "--workpath", $BuildDirectory, (Join-Path $PSScriptRoot "PY_SPF.spec"))
    } finally { Pop-Location }
    $BundlePath = Join-Path $OutputDirectory "PY_SPF"
    Invoke-Checked -File $BuildPython -Arguments @("-I", $AuditScript, $RepoRoot, $BundlePath)
    if ($InnoCompilerPath) {
        $Compiler = (Resolve-Path -LiteralPath $InnoCompilerPath).Path
        $InstallerScript = Join-Path $PSScriptRoot "installer.iss"
        $InstallerDirectory = Join-Path $OutputDirectory "installer"
        New-Item -ItemType Directory -Force -Path $InstallerDirectory | Out-Null
        Invoke-Checked -File $Compiler -Arguments @("/DPayloadDir=$BundlePath", "/DAppVersion=1.0.0", "/DInstallerOutputDir=$InstallerDirectory", $InstallerScript)
    }
    Write-Host "Native x86 bundle: $BundlePath"
    Write-Host "No application was launched; execution and installer tests are separate."
} finally {
    [Environment]::SetEnvironmentVariable("PYINSTALLER_CONFIG_DIR", $OldConfigDirectory, "Process")
}

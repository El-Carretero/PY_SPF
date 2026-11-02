# Native PY_SPF 1.0 Windows installer

`PY_SPF_1.0_Setup_x86.exe` installs the Native application for the current Windows
user. Python, the Python packages, the original Native GUI resources and its
private runtime are carried in the application bundle. Running the installer does
not require a Python installation, a venv, `pip`, or administrator permission.

The minimum Windows version supports the application's process-local UTF-8
manifest for Unicode user names and paths. No system locale is changed. Keep
the normal default installation path where possible. The original Native runtime
has a 258-byte UTF-8 limit for the full `PY_SPF.exe` path, including its filename;
this is a byte limit rather than a character count. The packaged entrypoint
checks it before Native initialization and stops with a clear error if a shorter
installation path is needed. Arbitrarily long paths are not supported.

This is the Native PY_SPF 1.0 packaging. The installer does not change the
controller's RUN, reset, polling or opt-out logic.

## Install and open

1. Run the installation EXE on Windows 10 version 1903 (build 18362) or newer,
   or Windows 11.
2. Keep the default application folder, or choose a new empty folder. The default
   is `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0`.
3. Finish installation. **Start Native PY_SPF** is unchecked by default.
4. Open **Native PY_SPF 1.0 Demo (no equipment)** from the Start menu to inspect
   the Native interface without contacting equipment. Open **Native PY_SPF 1.0**
   for the configured equipment connection.

The desktop shortcut is optional and unchecked by default. The installer uses an
English interface; the installed notes are supplied in English and Korean.

A hardware connection still uses the PC's existing device, cable, adapter and
network configuration. The installer does not discover equipment, change an IP
address, open a firewall port or apply instrument commands. Native startup can
contact the configured equipment only when the application is explicitly opened.

## What is isolated

| Item | Location or behavior |
|---|---|
| Application and private runtime | `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0` by default |
| Private configuration | `%LOCALAPPDATA%\PY_SPF_1.0\settings\config.sp` |
| Application data | `%LOCALAPPDATA%\PY_SPF_1.0\data` |
| Session logs | `%LOCALAPPDATA%\PY_SPF_1.0\logs\<UTC>_<UUID>` |
| Existing Python and venvs | Not installed into, selected or modified |
| `PATH`, file associations and NI registration | Not changed |
| Drivers, adapters, firewall and network settings | Not changed |

User data is created by the application, separately from its installed program
files. Existing source folders, `config.sp` files and communication logs are not
imported or overwritten by the installer. Keep the entire installed folder
together; the standalone EXE uses its bundled `_internal` files and the adjacent
`cvirte` resource folder. The original vendor runtime looks for
`cvirte\bin` and `cvirte\fonts` beside the EXE before its system or registry
resource locations. The three bin resources retain their original bytes. The
two adjacent `.ttf` paths contain clearly identified, non-font loader placeholders.
The unmodified original TTFs remain in `_internal` and are supplied through
`AddFontMemResourceEx` before NI initialization. These memory fonts are private
to this process; the vendor's file-existence check succeeds, while its attempted
session-wide font registration of the non-font placeholders fails harmlessly.
This avoids registering fonts for other applications and retaining font-file
locks after exit. The Native self-test selects each face and checks its actual
GDI font-data hash against the original TTF. Vendor DLLs are unmodified.

The preflight rejects missing private resources or unexpected placeholders even
if NI software is installed. Private runtime DLLs remain under `_internal`; no
NI registration or system-runtime replacement is performed. Bundled third-party
notices are retained in `_internal\THIRD_PARTY_NOTICES.md`.

## Updates and uninstall

Updates in this installer family use the same private AppId and the previously
registered application directory. An unrelated nonempty directory is rejected;
the installer never deletes or adopts an old source tree. Close this application
explicitly before updating or uninstalling. An application-owned mutex blocks
setup and uninstall while this packaged application is running. The installer
does not stop or restart an instrument-control process automatically.

Uninstall through Windows **Installed apps** / **Apps & features**. This removes
the installer-managed program files, its shortcuts and its own uninstall record.
Private settings, application data and session logs remain by default. Other
Python installations, venvs and software remain in place. The uninstaller has no
command that removes the separate user-data directory.

## Build contract

The build agent supplies a complete x86 PyInstaller onedir payload, normally:

```text
packaging/windows/dist/PY_SPF/
  PY_SPF.exe
  cvirte/
    bin/cvirte.rsc
    bin/msgrte.txt
    bin/cvierror.txt
    fonts/ni7seg.ttf     # generated loader placeholder
    fonts/nisystem.ttf  # generated loader placeholder
  _internal/
    ... bundled Python, packages, Native GUI resources and private runtime ...
```

Compile `installer.iss` with Inno Setup 6.4 or newer. The installer compiler is a
build dependency, not something installed on the target PC. `PayloadDir` is
required and must point to the whole onedir folder. Compilation checks the
private Python library, Native UIR files, NI runtime/resource files and GUI fonts,
including the three EXE-adjacent bin resources and both font placeholders;
an EXE-only or incomplete payload is rejected. `AppVersion` defaults to
`1.0.0`. `InstallerOutputDir` defaults to `dist\installer` relative to
`installer.iss`, which is `packaging/windows/dist/installer` in the repository.

```powershell
& $InnoCompilerPath `
  "/DPayloadDir=$PayloadDir" `
  "/DInstallerOutputDir=$InstallerOutputDir" `
  "/DAppVersion=1.0.0" `
  "packaging\windows\installer.iss"
```

Output: `PY_SPF_1.0_Setup_x86.exe`.

Shortcut arguments are fixed:

- Native: `--backend native`.
- Demo: `--demo --tcp-port 0 --local-port 0`.

Installation copies files only below the selected application directory, creates
per-user shortcuts and Inno Setup's private uninstall entry. There are no Python
installers, package-manager calls, registry registration scripts, shared DLL
registration, firewall commands, adapter commands or broad deletion rules.
Default and silent installations launch no application. Target-PC verification
must test the installed Demo and Native GUI resources; producing an installer
alone is not a completed execution test. Hardware operation is a separate test.

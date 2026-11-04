; Native PY_SPF 1.2 private, per-user installer.
; Compile-time inputs are supplied by build.ps1; payload must be a complete
; PyInstaller onedir, not just its executable.
#ifndef PayloadDir
  #error PayloadDir is required and must contain the complete PY_SPF onedir.
#endif
#if !FileExists(PayloadDir + "\PY_SPF.exe")
  #error PayloadDir does not contain PY_SPF.exe.
#endif
#if !FileExists(PayloadDir + "\_internal\base_library.zip")
  #error PayloadDir does not contain the private Python standard library.
#endif
#if !FileExists(PayloadDir + "\_internal\spitfire\resources\SPITFIRE.UIR") || !FileExists(PayloadDir + "\_internal\spitfire\resources\SERVER.UIR")
  #error PayloadDir does not contain the complete Native UIR resources.
#endif
#if !FileExists(PayloadDir + "\_internal\spitfire\resources\runtime\cvirte.dll") || !FileExists(PayloadDir + "\_internal\spitfire\resources\runtime\cvintwrk.dll")
  #error PayloadDir does not contain the private NI runtime libraries.
#endif
#if !FileExists(PayloadDir + "\_internal\spitfire\resources\runtime\bin\cvirte.rsc")
  #error PayloadDir does not contain the private NI panel resource data.
#endif
#if !FileExists(PayloadDir + "\_internal\spitfire\resources\runtime\bin\msgrte.txt") || !FileExists(PayloadDir + "\_internal\spitfire\resources\runtime\bin\cvierror.txt")
  #error PayloadDir does not contain the complete private NI bin text resources.
#endif
#if !FileExists(PayloadDir + "\_internal\spitfire\resources\runtime\fonts\ni7seg.ttf") || !FileExists(PayloadDir + "\_internal\spitfire\resources\runtime\fonts\nisystem.ttf")
  #error PayloadDir does not contain the private NI GUI fonts.
#endif
#if !FileExists(PayloadDir + "\cvirte\bin\cvirte.rsc") || !FileExists(PayloadDir + "\cvirte\bin\msgrte.txt") || !FileExists(PayloadDir + "\cvirte\bin\cvierror.txt")
  #error PayloadDir does not contain the EXE-adjacent private CVI bin resources.
#endif
#if !FileExists(PayloadDir + "\cvirte\fonts\ni7seg.ttf") || !FileExists(PayloadDir + "\cvirte\fonts\nisystem.ttf")
  #error PayloadDir does not contain the EXE-adjacent private CVI fonts.
#endif
#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif
#ifndef InstallerOutputDir
  #define InstallerOutputDir "dist\installer"
#endif

[Setup]
; This identity belongs only to this installer family. Keep it stable for updates.
AppId={{A772B846-AB4E-487B-A1DD-03E19D5880E9}
AppName=Native PY_SPF 1.2
AppVersion={#AppVersion}
AppVerName=Native PY_SPF 1.2
AppPublisher=PY_SPF
AppMutex=Local\PY_SPF.Native1_0.A772B846AB4E487BA1DD03E19D5880E9
DefaultDirName={localappdata}\Programs\Native_PY_SPF_1.0
DefaultGroupName=Native PY_SPF 1.2
PrivilegesRequired=lowest
ArchitecturesAllowed=x86compatible
MinVersion=10.0.18362
UsePreviousAppDir=yes
UsePreviousGroup=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
WizardStyle=modern
OutputDir={#InstallerOutputDir}
OutputBaseFilename=PY_SPF_1.2_Setup_x86
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\PY_SPF.exe
UninstallDisplayName=Native PY_SPF 1.2
ChangesEnvironment=no
ChangesAssociations=no
; Never stop or restart a running instrument-control process automatically.
CloseApplications=no
RestartApplications=no
AlwaysRestart=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Native PY_SPF desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; Private files only: no sharedfile, regserver, restartreplace, or system folders.
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}\docs"; DestName: "INSTALL.en.md"; Flags: ignoreversion
Source: "README.ko.md"; DestDir: "{app}\docs"; DestName: "INSTALL.ko.md"; Flags: ignoreversion

[Icons]
Name: "{group}\Native PY_SPF 1.2"; Filename: "{app}\PY_SPF.exe"; Parameters: "--backend native"; WorkingDir: "{app}"
Name: "{group}\Native PY_SPF 1.2 Demo (no equipment)"; Filename: "{app}\PY_SPF.exe"; Parameters: "--demo --tcp-port 0 --local-port 0"; WorkingDir: "{app}"
Name: "{autodesktop}\Native PY_SPF 1.2"; Filename: "{app}\PY_SPF.exe"; Parameters: "--backend native"; WorkingDir: "{app}"; Tasks: desktopicon

[InstallDelete]
; Only exact legacy app shortcut names, and only for a verified previous AppId.
; Keep any other files in the old group; dirifempty never removes their folder.
Type: files; Name: "{userprograms}\Native PY_SPF 1.0\Native PY_SPF 1.0.lnk"; Check: RemoveLegacyShortcuts
Type: files; Name: "{userprograms}\Native PY_SPF 1.0\Native PY_SPF 1.0 Demo (no equipment).lnk"; Check: RemoveLegacyShortcuts
Type: files; Name: "{autodesktop}\Native PY_SPF 1.0.lnk"; Check: RemoveLegacyShortcuts
Type: dirifempty; Name: "{userprograms}\Native PY_SPF 1.0"; Check: RemoveLegacyShortcuts

[Run]
; Native startup may contact configured equipment. Only an explicit checked box
; launches it; silent installations never launch anything.
Filename: "{app}\PY_SPF.exe"; Parameters: "--backend native"; WorkingDir: "{app}"; Description: "Start Native PY_SPF (uses the configured equipment connection)"; Flags: nowait postinstall skipifsilent unchecked

; No [Registry], [UninstallDelete] or [UninstallRun] entries. [InstallDelete]
; above is restricted to known shortcuts from a verified earlier installation.
; Inno Setup owns only its private uninstall record, copied files and shortcuts.
; User settings, data and logs are created by the application outside {app} and
; are deliberately never part of the installer's removal list.

[Code]
const
  PrivateUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A772B846-AB4E-487B-A1DD-03E19D5880E9}_is1';

var
  PreviousOwnedInstallation: Boolean;

function InitializeSetup(): Boolean;
var
  PreviousDirectory: String;
begin
  PreviousOwnedInstallation := False;
  PreviousDirectory := '';
  if not RegQueryStringValue(HKCU, PrivateUninstallKey,
    'InstallLocation', PreviousDirectory) then
    RegQueryStringValue(HKCU, PrivateUninstallKey,
      'Inno Setup: App Path', PreviousDirectory);
  if PreviousDirectory <> '' then
    PreviousOwnedInstallation := FileExists(
      AddBackslash(ExpandFileName(PreviousDirectory)) + 'PY_SPF.exe');
  Result := True;
end;

function RemoveLegacyShortcuts(): Boolean;
begin
  Result := PreviousOwnedInstallation;
end;

function DirectoryHasContent(const Directory: String): Boolean;
var
  Item: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Directory) + '*', Item) then
  begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') then
        begin
          Result := True;
          Break;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

function IsThisInstallDirectory(const Directory: String): Boolean;
var
  PreviousDirectory: String;
begin
  Result := False;
  if not RegQueryStringValue(HKCU, PrivateUninstallKey,
    'InstallLocation', PreviousDirectory) then
    if not RegQueryStringValue(HKCU, PrivateUninstallKey,
      'Inno Setup: App Path', PreviousDirectory) then
      Exit;
  if PreviousDirectory <> '' then
    Result := CompareText(AddBackslash(ExpandFileName(Directory)),
      AddBackslash(ExpandFileName(PreviousDirectory))) = 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Destination: String;
begin
  Result := '';
  Destination := ExpandConstant('{app}');
  if DirectoryHasContent(Destination) and
    not IsThisInstallDirectory(Destination) then
    Result := 'The destination already contains files and is not registered ' +
      'as this Native PY_SPF installation. Choose a new, empty application ' +
      'folder. Existing files will not be deleted or adopted.';
end;

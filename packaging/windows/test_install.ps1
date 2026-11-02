[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SetupPath,
    [string]$OutputDirectory,
    [string]$InstallDirectory,
    [ValidateSet('NetSecurity', 'Registry')][string]$FirewallRuleProbe = 'NetSecurity',
    [ValidateRange(30, 600)][int]$SetupTimeoutSeconds = 180
)

# Windows PowerShell 5.1 compatible. No instrument transport, system repair,
# Python installation, network mutation, or global keyboard/mouse input.
# Run on an interactive desktop. OutputDirectory and InstallDirectory must be
# new/empty, and no installation from this AppId may already be registered.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This installer validation requires Windows 10/11 and an interactive desktop.'
}

$RunId = [Guid]::NewGuid().ToString('N')
$UnicodeName = 'PY_SPF_' + [char]0xAC80 + [char]0xC99D + '_' + $RunId
if (-not $InstallDirectory) { $InstallDirectory = Join-Path ([IO.Path]::GetTempPath()) $UnicodeName }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path ([IO.Path]::GetTempPath()) ('PY_SPF_install_proof_' + $RunId) }
$InstallDirectory = [IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\')
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
$UserData = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'PY_SPF_1.0'
$UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A772B846-AB4E-487B-A1DD-03E19D5880E9}_is1'
$Executable = Join-Path $InstallDirectory 'PY_SPF.exe'
$ReportPath = Join-Path $OutputDirectory 'install-validation.json'
$ProofPath = Join-Path $OutputDirectory 'native-self-test.json'
$BitmapPath = Join-Path $OutputDirectory 'native-self-test.bmp'
$script:Checks = New-Object 'System.Collections.Generic.List[object]'
$script:Errors = New-Object 'System.Collections.Generic.List[object]'
$script:PythonPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$Report = [ordered]@{
    schema_version = 1
    scope = 'Per-user install, private Native GUI simulator, regular Demo entry, uninstall, selected persistent-setting isolation. No equipment operation.'
    physical_device_io = $false
    started_utc = [DateTime]::UtcNow.ToString('o')
    run_id = $RunId
    setup_sha256 = $null
    install_directory = $InstallDirectory
    output_directory = $OutputDirectory
    settings_exported = 'Digests/counts only; no raw environment or registry values.'
    firewall_rule_probe = [ordered]@{
        mode = $FirewallRuleProbe
        automatic_fallback = $false
        registry_hive = 'HKLM'
        registry_views = @('Registry32', 'Registry64')
        registry_targets = @('SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\FirewallRules', 'SOFTWARE\Policies\Microsoft\WindowsFirewall')
        scope = 'NetSecurity mode reads selected persistent rule properties; Registry mode hashes only the explicit persistent registry targets, including verified absence.'
    }
    fingerprints = [ordered]@{}
    install = $null
    manifest = $null
    native_self_test = $null
    normal_demo = $null
    uninstall = $null
    userdata = $null
    checks = @()
    errors = @()
    passed = $false
    not_tested = @('Physical instrument/optical output', 'Running-app update/uninstall refusal', 'Installer rejection of a foreign nonempty directory', 'Every machine file and every firewall rule filter')
}
if ($FirewallRuleProbe -eq 'Registry') {
    $Report.not_tested += @('Full NetSecurity firewall-rule provider inspection', 'WFP filters and effective/active firewall policy')
}
$InstallAttempted = $false
$InstallVerified = $false
$ManifestVerified = $false
$NativeVerified = $false
$DemoVerified = $false
$UninstallVerified = $false
$IsolationVerified = $false
$UserDataVerified = $false
$OutputOwned = $false
$script:PoisonEnvironment = $null
$Before = $null
$DataBefore = $null
$DataBeforeUninstall = $null
$Sentinel = $null
$Stage = 'preflight'

function Add-Check {
    param([string]$Name, [bool]$Passed, [string]$Detail, [switch]$ContinueOnFailure)
    $script:Checks.Add([PSCustomObject]@{ name = $Name; passed = $Passed; detail = $Detail })
    if (-not $Passed -and -not $ContinueOnFailure) { throw ('Check failed: ' + $Name + '. ' + $Detail) }
}
function Add-Error {
    param([string]$Phase, $Failure)
    $script:Errors.Add([PSCustomObject]@{ phase = $Phase; error = [string]$Failure })
}
function Get-TextHash {
    param([string]$Text)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '').ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}
function Get-RowsDigest {
    param([object[]]$Rows)
    if ($null -eq $Rows) { $Rows = [object[]]@() }
    $json = ConvertTo-Json -InputObject $Rows -Depth 16 -Compress
    return [PSCustomObject]@{ available = $true; sha256 = Get-TextHash $json; records = $Rows.Count }
}
function Get-EnvironmentDigest {
    param([EnvironmentVariableTarget]$Target)
    $values = [Environment]::GetEnvironmentVariables($Target)
    [string[]]$names = @($values.Keys)
    [Array]::Sort($names, [StringComparer]::Ordinal)
    $rows = New-Object 'System.Collections.Generic.List[object]'
    foreach ($name in $names) { $rows.Add([ordered]@{ name = $name; value = [string]$values[$name] }) }
    return Get-RowsDigest -Rows $rows.ToArray()
}
function Read-RegistryTree {
    param($Key, [string]$Path, $Rows, [bool]$CollectPython)
    $Rows.Add([ordered]@{ key = $Path; present = $true })
    [string[]]$names = $Key.GetValueNames()
    [Array]::Sort($names, [StringComparer]::Ordinal)
    foreach ($name in $names) {
        $kind = $Key.GetValueKind($name).ToString()
        $value = $Key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        if ($value -is [byte[]]) { $value = [Convert]::ToBase64String($value) }
        $Rows.Add([ordered]@{ key = $Path; name = $name; kind = $kind; value = $value })
        if ($CollectPython -and $value -is [string]) {
            if ($Path -match '\\InstallPath$' -and $name -eq '') { [void]$script:PythonPaths.Add($value) }
            if ($name -in @('ExecutablePath', 'WindowedExecutablePath') -and $value.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) {
                [void]$script:PythonPaths.Add($value)
            }
        }
    }
    [string[]]$children = $Key.GetSubKeyNames()
    [Array]::Sort($children, [StringComparer]::Ordinal)
    foreach ($child in $children) {
        $next = $Key.OpenSubKey($child, $false)
        if ($null -eq $next) { throw ('Cannot read registry key: ' + $Path + '\' + $child) }
        try { Read-RegistryTree -Key $next -Path ($Path + '\' + $child) -Rows $Rows -CollectPython $CollectPython }
        finally { $next.Dispose() }
    }
}
function Get-RegistryDigest {
    param(
        [string[]]$Roots,
        [bool]$CollectPython = $false,
        [Microsoft.Win32.RegistryHive[]]$Hives = @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)
    )
    $rows = New-Object 'System.Collections.Generic.List[object]'
    foreach ($hive in $Hives) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
            try {
                foreach ($root in $Roots) {
                    $path = $hive.ToString() + '/' + $view.ToString() + '/' + $root
                    $key = $base.OpenSubKey($root, $false)
                    if ($null -eq $key) { $rows.Add([ordered]@{ key = $path; present = $false }); continue }
                    try { Read-RegistryTree -Key $key -Path $path -Rows $rows -CollectPython $CollectPython }
                    finally { $key.Dispose() }
                }
            } finally { $base.Dispose() }
        }
    }
    return Get-RowsDigest -Rows $rows.ToArray()
}
function Get-AppRegistrations {
    $entries = New-Object 'System.Collections.Generic.List[object]'
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32, [Microsoft.Win32.RegistryView]::Registry64)) {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
            try {
                $key = $base.OpenSubKey($UninstallKey, $false)
                if ($null -ne $key) {
                    try { $entries.Add([PSCustomObject]@{ hive = $hive.ToString(); view = $view.ToString() }) }
                    finally { $key.Dispose() }
                }
            } finally { $base.Dispose() }
        }
    }
    # The caller explicitly wraps output in @(); no unary-comma array return.
    foreach ($entry in $entries) { $entry }
}
function Get-FileDigest {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return [PSCustomObject]@{ available = $true; exists = $false; sha256 = Get-TextHash 'ABSENT'; records = 0 } }
    $item = Get-Item -LiteralPath $Path -Force
    return [PSCustomObject]@{ available = $true; exists = $true; sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant(); records = 1; bytes = $item.Length }
}
function Get-PythonFilesDigest {
    foreach ($command in @(Get-Command python.exe, pythonw.exe, py.exe -All -CommandType Application -ErrorAction SilentlyContinue)) {
        if ($command.Path) { [void]$script:PythonPaths.Add($command.Path) }
    }
    $selected = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($candidate in $script:PythonPaths) {
        $expanded = [Environment]::ExpandEnvironmentVariables($candidate)
        if (Test-Path -LiteralPath $expanded -PathType Leaf) { [void]$selected.Add([IO.Path]::GetFullPath($expanded)); $folder = Split-Path -Parent $expanded }
        elseif (Test-Path -LiteralPath $expanded -PathType Container) { $folder = $expanded }
        else { continue }
        foreach ($name in @('python.exe', 'pythonw.exe', 'pyvenv.cfg')) {
            $file = Join-Path $folder $name
            if (Test-Path -LiteralPath $file -PathType Leaf) { [void]$selected.Add([IO.Path]::GetFullPath($file)) }
        }
        foreach ($file in @(Get-ChildItem -LiteralPath $folder -Filter 'python*.dll' -File -ErrorAction Stop)) { [void]$selected.Add($file.FullName) }
    }
    $rows = New-Object 'System.Collections.Generic.List[object]'
    foreach ($file in @($selected | Sort-Object)) {
        $item = Get-Item -LiteralPath $file -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            # Windows App Execution Aliases are not a Python runtime file. Their
            # content cannot be opened normally; fingerprint metadata, never follow.
            $rows.Add([ordered]@{ path = $file; kind = 'reparse-point-metadata-only'; attributes = [string]$item.Attributes; bytes = $item.Length })
        } else { $rows.Add([ordered]@{ path = $file; kind = 'regular-file'; digest = Get-FileDigest $file }) }
    }
    return Get-RowsDigest -Rows $rows.ToArray()
}
function Invoke-SelectedCimQuery {
    param([scriptblock]$Query)
    try { & $Query }
    catch {
        # A DHCP-only computer can legitimately have no persistent addresses or
        # routes. Only the cmdlet's explicit no-match result means an empty set.
        if ($_.CategoryInfo.Category -eq 'ObjectNotFound' -and $_.FullyQualifiedErrorId -like 'CmdletizationQuery_NotFound*') { return }
        throw
    }
}
function Get-FirewallRuleDigest {
    if ($FirewallRuleProbe -eq 'Registry') {
        # Explicit alternative, never an automatic response to access denial.
        # OpenSubKey is read-only; access errors fail, absent roots are recorded.
        $digest = Get-RegistryDigest -Roots @('SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\FirewallRules', 'SOFTWARE\Policies\Microsoft\WindowsFirewall') -Hives @([Microsoft.Win32.RegistryHive]::LocalMachine)
    } else {
        $digest = Get-RowsDigest -Rows @(Get-NetFirewallRule -PolicyStore PersistentStore -ErrorAction Stop | Sort-Object Name | Select-Object Name, Enabled, Direction, Action, Profile, EdgeTraversalPolicy)
    }
    Add-Member -InputObject $digest -NotePropertyName probe_method -NotePropertyValue $FirewallRuleProbe
    return $digest
}
function Get-IsolationSnapshot {
    $observations = [ordered]@{}
    $probes = [ordered]@{
        machine_environment_including_path = { Get-EnvironmentDigest ([EnvironmentVariableTarget]::Machine) }
        user_environment_including_path = { Get-EnvironmentDigest ([EnvironmentVariableTarget]::User) }
        python_and_ni_registry = { Get-RegistryDigest -Roots @('Software\Python', 'Software\National Instruments', 'Software\WOW6432Node\Python', 'Software\WOW6432Node\National Instruments') -CollectPython $true }
        associations = { Get-RegistryDigest -Roots @('Software\Classes\.py', 'Software\Classes\.pyw', 'Software\Classes\.uir', 'Software\Classes\Python.File', 'Software\Classes\Python.NoConFile', 'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.py', 'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pyw', 'Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.uir') }
        existing_python_selected_files = { Get-PythonFilesDigest }
        root_config_sp = { Get-FileDigest 'C:\config.sp' }
        adapter_configuration = { Get-RowsDigest -Rows @(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Sort-Object InterfaceGuid | Select-Object InterfaceGuid, Name, InterfaceDescription, AdminStatus, MacAddress) }
        adapter_bindings = { Get-RowsDigest -Rows @(Get-NetAdapterBinding -Name '*' -AllBindings -IncludeHidden -ErrorAction Stop | Sort-Object Name, ComponentID | Select-Object Name, ComponentID, Enabled) }
        persistent_ip_interfaces = { Get-RowsDigest -Rows @(Invoke-SelectedCimQuery { Get-NetIPInterface -PolicyStore PersistentStore -ErrorAction Stop } | Sort-Object InterfaceIndex, AddressFamily | Select-Object InterfaceIndex, AddressFamily, Dhcp, InterfaceMetric, NlMtu, Forwarding, WeakHostSend, WeakHostReceive, RouterDiscovery) }
        persistent_ip_addresses = { Get-RowsDigest -Rows @(Invoke-SelectedCimQuery { Get-NetIPAddress -PolicyStore PersistentStore -ErrorAction Stop } | Sort-Object InterfaceIndex, AddressFamily, IPAddress | Select-Object InterfaceIndex, AddressFamily, IPAddress, PrefixLength, PrefixOrigin, SuffixOrigin) }
        persistent_routes = { Get-RowsDigest -Rows @(Invoke-SelectedCimQuery { Get-NetRoute -PolicyStore PersistentStore -ErrorAction Stop } | Sort-Object InterfaceIndex, DestinationPrefix, NextHop | Select-Object InterfaceIndex, DestinationPrefix, NextHop, RouteMetric, Protocol) }
        dns_servers = { Get-RowsDigest -Rows @(Get-DnsClientServerAddress -ErrorAction Stop | Sort-Object InterfaceIndex, AddressFamily | Select-Object InterfaceIndex, AddressFamily, ServerAddresses) }
        firewall_profiles = { Get-RowsDigest -Rows @(Get-NetFirewallProfile -PolicyStore PersistentStore -ErrorAction Stop | Sort-Object Name | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction, AllowInboundRules, AllowLocalFirewallRules, AllowLocalIPsecRules, NotifyOnListen) }
        firewall_rule_settings = { Get-FirewallRuleDigest }
    }
    foreach ($name in $probes.Keys) {
        try { $observations[$name] = & $probes[$name] }
        catch { $observations[$name] = [PSCustomObject]@{ available = $false; error = $_.Exception.Message }; Add-Error ('fingerprint/' + $name) $_.Exception.Message }
    }
    return $observations
}
function Compare-Isolation {
    param($Baseline, $Current, [string]$Phase)
    $good = $true
    foreach ($name in $Baseline.Keys) {
        $same = $Baseline[$name].available -and $Current[$name].available
        if ($same -and $name -eq 'firewall_rule_settings') { $same = $Baseline[$name].probe_method -eq $Current[$name].probe_method }
        if ($same) { $same = $Baseline[$name].sha256 -eq $Current[$name].sha256 }
        Add-Check -Name ($Phase + '/' + $name) -Passed ([bool]$same) -Detail 'Selected persistent-state digests must match.' -ContinueOnFailure
        if (-not $same) { $good = $false }
    }
    return $good
}
function Get-TreeRecords {
    param([string]$Directory)
    $records = @{}
    if (-not (Test-Path -LiteralPath $Directory)) { return $records }
    $root = Get-Item -LiteralPath $Directory -Force
    if ($root.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'User-data root must not be a reparse point for this test.' }
    foreach ($item in @(Get-ChildItem -LiteralPath $Directory -Force -Recurse -ErrorAction Stop)) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'User-data tree contains a reparse point; no test was authorized through it.' }
        if (-not $item.PSIsContainer) { $records[$item.FullName] = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
    return $records
}
function Test-RetainedFiles {
    param($Records)
    foreach ($path in $Records.Keys) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Records[$path]) { return $false }
    }
    return $true
}
function Quote-WindowsArgument {
    param([string]$Value)
    if ($Value.IndexOf([char]0) -ge 0) { throw 'NUL is not a valid process argument.' }
    # CommandLineToArgvW/CRT quoting, including quotes and terminal backslashes.
    $builder = New-Object Text.StringBuilder
    [void]$builder.Append([char]34)
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq [char]92) { $slashes++; continue }
        if ($character -eq [char]34) {
            [void]$builder.Append(([string][char]92) * (2 * $slashes + 1))
        } else { [void]$builder.Append(([string][char]92) * $slashes) }
        [void]$builder.Append($character)
        $slashes = 0
    }
    [void]$builder.Append(([string][char]92) * (2 * $slashes))
    [void]$builder.Append([char]34)
    return $builder.ToString()
}
function Start-OwnedProcess {
    param([string]$File, [string[]]$Arguments, [switch]$PoisonPythonEnvironment)
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $File
    $info.Arguments = (($Arguments | ForEach-Object { Quote-WindowsArgument $_ }) -join ' ')
    $info.WorkingDirectory = Split-Path -Parent $File
    $info.UseShellExecute = $false
    if ($PoisonPythonEnvironment) {
        if ($null -eq $script:PoisonEnvironment) { throw 'Child-only Python environment fixture was not prepared.' }
        foreach ($name in $script:PoisonEnvironment.Keys) { $info.EnvironmentVariables[$name] = $script:PoisonEnvironment[$name] }
    }
    return [Diagnostics.Process]::Start($info)
}
function Wait-OwnedProcess {
    param($Process, [int]$Seconds)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $timedOut = -not $Process.WaitForExit($Seconds * 1000)
    if ($timedOut) {
        # Never taskkill by image name, recurse into foreign processes, or stop a device app.
        try { $Process.Kill(); [void]$Process.WaitForExit(5000) } catch { Add-Error 'owned-process-timeout' $_.Exception.Message }
    }
    $code = $null
    if ($Process.HasExited) { $code = $Process.ExitCode }
    return [PSCustomObject]@{ pid = $Process.Id; exit_code = $code; timed_out = $timedOut; elapsed_seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3) }
}
function Invoke-OwnedProcess {
    param([string]$File, [string[]]$Arguments, [int]$Seconds, [switch]$PoisonPythonEnvironment)
    $process = Start-OwnedProcess -File $File -Arguments $Arguments -PoisonPythonEnvironment:$PoisonPythonEnvironment
    try { return Wait-OwnedProcess -Process $process -Seconds $Seconds }
    finally { $process.Dispose() }
}
function Assert-EmptyDirectory {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw ('Not a plain new/empty directory: ' + $Path) }
        if (@(Get-ChildItem -LiteralPath $Path -Force).Count -ne 0) { throw ('Refusing an existing nonempty test directory: ' + $Path) }
    }
}
function Test-UnderDirectory {
    param([string]$Child, [string]$Parent)
    return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or $Child.StartsWith($Parent.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}
function Initialize-WindowProbe {
    if ('InstallerNativeWindowProbe' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class InstallerNativeWindowProbe {
  public sealed class WindowRecord {
    public long Handle;
    public uint ProcessId;
    public bool Visible;
    public string Title;
  }
  delegate bool EnumWindowProc(IntPtr hwnd, IntPtr parameter);
  [DllImport("user32.dll", SetLastError=true)] static extern bool EnumWindows(EnumWindowProc callback, IntPtr parameter);
  [DllImport("user32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)] static extern int GetWindowTextW(IntPtr hwnd, System.Text.StringBuilder text, int capacity);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
  [DllImport("user32.dll", SetLastError=true)] public static extern bool PostMessageW(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
  [DllImport("shell32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CommandLineToArgvW(string text, out int count);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)] static extern uint GetLongPathNameW(string path, System.Text.StringBuilder result, uint capacity);
  [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr value);
  public static WindowRecord ReadWindow(IntPtr hwnd) {
    uint pid;
    GetWindowThreadProcessId(hwnd, out pid);
    var title = new System.Text.StringBuilder(2048);
    GetWindowTextW(hwnd, title, title.Capacity);
    return new WindowRecord { Handle=hwnd.ToInt64(), ProcessId=pid, Visible=IsWindowVisible(hwnd), Title=title.ToString() };
  }
  public static WindowRecord[] WindowsForProcess(uint pid) {
    var windows = new System.Collections.Generic.List<WindowRecord>();
    EnumWindowProc callback = delegate(IntPtr hwnd, IntPtr parameter) {
      uint owner;
      GetWindowThreadProcessId(hwnd, out owner);
      if (owner == pid) {
        var window = ReadWindow(hwnd);
        if (window.ProcessId == pid) windows.Add(window);
      }
      return true;
    };
    if (!EnumWindows(callback, IntPtr.Zero)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    GC.KeepAlive(callback);
    return windows.ToArray();
  }
  public static string ExistingLongPath(string path) {
    string full = System.IO.Path.GetFullPath(path);
    if (!System.IO.File.Exists(full) && !System.IO.Directory.Exists(full)) throw new System.IO.FileNotFoundException("Expected installed path does not exist", full);
    var result = new System.Text.StringBuilder(32768);
    uint length = GetLongPathNameW(full, result, (uint)result.Capacity);
    if (length == 0) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    if (length >= result.Capacity) throw new System.IO.PathTooLongException("Cannot canonicalize installed path");
    string value = result.ToString();
    if (value.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase)) value = @"\\" + value.Substring(8);
    else if (value.StartsWith(@"\\?\", StringComparison.Ordinal)) value = value.Substring(4);
    return value.TrimEnd(System.IO.Path.DirectorySeparatorChar);
  }
  public static string[] Split(string text) {
    int count;
    IntPtr pointer = CommandLineToArgvW(text, out count);
    if (pointer == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
    try {
      string[] result = new string[count];
      for (int i=0; i<count; i++) result[i] = Marshal.PtrToStringUni(Marshal.ReadIntPtr(pointer, i*IntPtr.Size));
      return result;
    } finally { LocalFree(pointer); }
  }
}
'@
}
function Convert-HeartbeatUtc {
    param($Value)
    if ($Value -is [DateTimeOffset]) { return $Value.UtcDateTime }
    if ($Value -is [DateTime]) {
        if ($Value.Kind -eq [DateTimeKind]::Unspecified) { throw 'Heartbeat timestamp has no verifiable timezone.' }
        return $Value.ToUniversalTime()
    }
    return [DateTimeOffset]::Parse([string]$Value, [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
}
function Test-DemoWindow {
    param($Window, [int]$ExpectedPid)
    return $Window.ProcessId -eq $ExpectedPid -and $Window.Visible -and $Window.Title.StartsWith('Spitfire [', [StringComparison]::Ordinal) -and $Window.Title.IndexOf('DEMO', [StringComparison]::OrdinalIgnoreCase) -ge 0
}

try {
    Assert-EmptyDirectory $OutputDirectory
    Assert-EmptyDirectory $InstallDirectory
    if ((Test-UnderDirectory $OutputDirectory $InstallDirectory) -or (Test-UnderDirectory $InstallDirectory $OutputDirectory) -or (Test-UnderDirectory $OutputDirectory $UserData) -or (Test-UnderDirectory $InstallDirectory $UserData)) {
        throw 'Output, installation and default user-data paths must be separate.'
    }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $OutputOwned = $true
    $poisonDirectory = Join-Path $OutputDirectory 'python-environment-poison'
    New-Item -ItemType Directory -Path $poisonDirectory | Out-Null
    [IO.File]::WriteAllText((Join-Path $poisonDirectory 'sitecustomize.py'), "raise RuntimeError('mustnotimport')`n", [Text.Encoding]::ASCII)
    $script:PoisonEnvironment = @{
        PATH = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32'
        PYTHONHOME = Join-Path $poisonDirectory 'nonexistent-python-home'
        PYTHONPATH = $poisonDirectory
    }
    $Report['child_environment_test'] = [ordered]@{ applies_to = @('native-self-test', 'regular-demo'); process_start_info_only = $true; restricted_path = $true; nonexistent_pythonhome = $true; raising_sitecustomize_on_pythonpath = $true; persistent_environment_modified = $false }
    Initialize-WindowProbe
    $quoteCases = @('', 'simple', 'with space', ('quote' + [char]34 + 'inside'), ('C:' + [char]92 + 'tail' + [char]92), ('two' + [char]92 + [char]92 + [char]34 + 'quotes'), $UnicodeName)
    $roundTrip = [InstallerNativeWindowProbe]::Split('probe.exe ' + (($quoteCases | ForEach-Object { Quote-WindowsArgument $_ }) -join ' '))
    $quoteCorrect = $roundTrip.Length -eq $quoteCases.Count + 1
    if ($quoteCorrect) {
        for ($index = 0; $index -lt $quoteCases.Count; $index++) {
            if (-not [string]::Equals($roundTrip[$index + 1], $quoteCases[$index], [StringComparison]::Ordinal)) { $quoteCorrect = $false }
        }
    }
    Add-Check 'windows-argv-roundtrip' $quoteCorrect 'System CommandLineToArgvW must preserve empty, Unicode, quoted and terminal-backslash arguments.'
    $SetupPath = (Resolve-Path -LiteralPath $SetupPath).Path
    Add-Check 'setup-exists' (Test-Path -LiteralPath $SetupPath -PathType Leaf) 'Caller supplies the already built installer; no download occurs.'
    $Report.setup_sha256 = (Get-FileHash -LiteralPath $SetupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Add-Check 'private-native-path-byte-limit' ([Text.Encoding]::UTF8.GetByteCount($Executable) -lt 259) 'Full installed EXE path must fit the original private-runtime limit.'
    Add-Check 'no-existing-installation' (@(Get-AppRegistrations).Count -eq 0) 'Refuse to update or uninstall any existing user/machine installation from this AppId.'
    $existingMutex = $null
    try { $existingMutex = [Threading.Mutex]::OpenExisting('Local\PY_SPF.Native1_0.A772B846AB4E487BA1DD03E19D5880E9') }
    catch [Threading.WaitHandleCannotBeOpenedException] { }
    if ($null -ne $existingMutex) { $existingMutex.Dispose(); throw 'An existing packaged PY_SPF instance is running; it will not be closed.' }
    $DataBefore = Get-TreeRecords $UserData
    $Before = Get-IsolationSnapshot
    $Report.fingerprints['before'] = $Before
    Add-Check 'baseline-complete' (@($Before.Values | Where-Object { -not $_.available }).Count -eq 0) 'Missing or inaccessible observations prevent an isolation PASS.'
    $Stage = 'userdata-sentinel'
    $dataFolder = Join-Path $UserData 'data'
    New-Item -ItemType Directory -Path $dataFolder -Force | Out-Null
    $Sentinel = Join-Path $dataFolder ('installer-retention-' + $RunId + '.txt')
    $stream = [IO.File]::Open($Sentinel, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $bytes = [Text.Encoding]::UTF8.GetBytes('Owned installer-test retention sentinel ' + $RunId); $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
    $sentinelHash = (Get-FileHash -LiteralPath $Sentinel -Algorithm SHA256).Hash.ToLowerInvariant()

    $Stage = 'install'
    $InstallAttempted = $true
    $Report.install = Invoke-OwnedProcess -File $SetupPath -Arguments @('/CURRENTUSER', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/DIR=' + $InstallDirectory), ('/LOG=' + (Join-Path $OutputDirectory 'installer.log'))) -Seconds $SetupTimeoutSeconds
    Add-Check 'silent-install-exit' (-not $Report.install.timed_out -and $Report.install.exit_code -eq 0) 'Silent per-user setup must exit0 without launching the application.'
    Add-Check 'installed-executable' (Test-Path -LiteralPath $Executable -PathType Leaf) 'Installed Native executable must exist.'
    $registrations = @(Get-AppRegistrations)
    Add-Check 'per-user-uninstall-registration' ($registrations.Count -gt 0 -and @($registrations | Where-Object { $_.hive -eq 'LocalMachine' }).Count -eq 0) 'Only the application-owned HKCU uninstall entry is expected.'
    $unexpected = @(Get-CimInstance Win32_Process -Filter "Name='PY_SPF.exe'" -ErrorAction Stop | Where-Object { $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath).Equals($Executable, [StringComparison]::OrdinalIgnoreCase) })
    Add-Check 'silent-install-did-not-launch' ($unexpected.Count -eq 0) 'No installed executable process exists before this harness launches it.'
    $InstallVerified = $true
    $afterInstall = Get-IsolationSnapshot
    $Report.fingerprints['after_install'] = $afterInstall
    Add-Check 'install-isolation' (Compare-Isolation $Before $afterInstall 'after_install') 'Installer may create only its app-owned files, shortcuts and uninstall registration within the tested scope.'
    Add-Check 'existing-userdata-after-install' (Test-RetainedFiles $DataBefore) 'All preexisting user-data files must retain their hashes.'

    $Stage = 'bundle-manifest'
    $manifestPath = Join-Path $InstallDirectory 'bundle-manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Add-Check 'manifest-identity' ($manifest.application -eq 'PY_SPF' -and $manifest.layout -eq 'onedir' -and $manifest.architecture -eq 'x86' -and @($manifest.files).Count -gt 0) 'Require a complete Native x86 onedir payload manifest.'
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $verified = 0
    foreach ($entry in $manifest.files) {
        $relative = [string]$entry.path
        if ([IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[/\\])\.\.([/\\]|$)|:' -or -not $seen.Add($relative)) { throw 'Manifest contains an unsafe or duplicate payload path.' }
        $file = [IO.Path]::GetFullPath((Join-Path $InstallDirectory $relative.Replace('/', '\')))
        if (-not (Test-UnderDirectory $file $InstallDirectory) -or -not (Test-Path -LiteralPath $file -PathType Leaf)) { throw ('Missing payload file: ' + $relative) }
        $item = Get-Item -LiteralPath $file -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Unexpected payload reparse point: ' + $relative) }
        if ($item.Length -ne $entry.bytes -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) { throw ('Payload digest/length mismatch: ' + $relative) }
        $verified++
    }
    $Report.manifest = [ordered]@{ sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant(); payload_files_verified = $verified; source_commit = $manifest.source_commit }
    Add-Check 'every-manifest-payload-file' ($verified -eq @($manifest.files).Count) 'Every listed payload file was read and hashed after installation.'
    $ManifestVerified = $true

    $Stage = 'native-self-test'
    $Report.native_self_test = Invoke-OwnedProcess -File $Executable -Arguments @('--self-test-native', '--output', $ProofPath, '--snapshot', $BitmapPath, '--duration', '20') -Seconds 45 -PoisonPythonEnvironment
    Add-Check 'native-self-test-exit' (-not $Report.native_self_test.timed_out -and $Report.native_self_test.exit_code -eq 0) 'Only the owned simulator self-test PID is bounded; no real transport is requested.'
    $proof = Get-Content -LiteralPath $ProofPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Add-Check 'native-self-test-simulator-only' ($proof.mode -eq 'in-memory simulator only' -and $proof.physical_device_io -eq $false -and $proof.frozen -eq $true -and $proof.python_bits -eq 32 -and $proof.acp -eq 65001 -and $proof.exit_code -eq 0) 'Require frozen x86, process UTF-8 and explicit no-equipment proof.'
    Add-Check 'frozen-python-isolation' ($proof.ignore_python_environment -eq $true -and $proof.ignore_user_site -eq $true -and $proof.transport_class -eq 'TestTransport' -and $proof.tcp_server_enabled -eq $false) 'The poisoned child must ignore Python environment/user site and use only its in-memory transport, without a TCP server.'
    $pythonDll = [InstallerNativeWindowProbe]::ExistingLongPath($proof.python_dll_loaded_from)
    $privatePythonDirectory = [InstallerNativeWindowProbe]::ExistingLongPath((Join-Path $InstallDirectory '_internal'))
    Add-Check 'private-python-dll' ([IO.Path]::GetDirectoryName($pythonDll).Equals($privatePythonDirectory, [StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($pythonDll) -match '^python[0-9]+\.dll$' -and $pythonDll.Equals([InstallerNativeWindowProbe]::ExistingLongPath($proof.expected_python_dll), [StringComparison]::OrdinalIgnoreCase)) 'GetModuleFileName must identify the bundled Python DLL inside this installation, with existing 8.3 aliases normalized.'
    Add-Check 'native-self-test-readiness' ($proof.panel_count -eq 10 -and $proof.connected -and $proof.gui_ready -and $proof.optout -eq 1 -and $proof.displayed_optout -eq 1 -and $proof.menu_dimmed -eq 0 -and @($proof.callback_errors).Count -eq 0 -and $proof.phases -contains 'native_simulator_validation_passed' -and $proof.phases -contains 'native_closed') 'Native panels, fresh simulated status, callbacks and clean teardown must be proven.'
    $expectedDll = Join-Path $InstallDirectory '_internal\spitfire\resources\runtime\cvirte.dll'
    $expectedBin = Join-Path $InstallDirectory 'cvirte\bin'
    Add-Check 'private-ni-dll-and-resources' ([InstallerNativeWindowProbe]::ExistingLongPath($proof.cvirte_loaded_from).Equals([InstallerNativeWindowProbe]::ExistingLongPath($expectedDll), [StringComparison]::OrdinalIgnoreCase) -and [InstallerNativeWindowProbe]::ExistingLongPath($proof.resource_directory).Equals([InstallerNativeWindowProbe]::ExistingLongPath($expectedBin), [StringComparison]::OrdinalIgnoreCase) -and $proof.cvirte_sha256 -eq (Get-FileHash -LiteralPath $expectedDll -Algorithm SHA256).Hash) 'Loaded NI DLL and EXE-adjacent resource directory must be this install, never a global NI cache; existing 8.3 aliases are normalized.'
    Add-Check 'native-visible-controls' ($proof.visibility.curtain_visible -eq 0 -and $proof.visibility.loading_visible -eq 0 -and $proof.visibility.run_visible -eq 1 -and $proof.visibility.stop_visible -eq 1) 'Actual Native visibility attributes must match the ready simulator screen.'
    $bmp = [IO.File]::ReadAllBytes($BitmapPath)
    Add-Check 'native-bmp-written' ($bmp.Length -gt 54 -and $bmp[0] -eq 66 -and $bmp[1] -eq 77) 'Native bitmap capture must exist and carry a BMP header.'
    $NativeVerified = $true

    $Stage = 'regular-demo'
    $demo = Start-OwnedProcess -File $Executable -Arguments @('--demo', '--tcp-port', '0', '--local-port', '0') -PoisonPythonEnvironment
    try {
        $demoStartedUtc = $demo.StartTime.ToUniversalTime()
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $ready = $false
        $heartbeat = $null
        $window = [IntPtr]::Zero
        $lastHeartbeat = $null
        $Report.normal_demo = [ordered]@{ pid = $demo.Id; started_utc = $demoStartedUtc.ToString('o'); ready = $false; windows = @(); matching_windows = 0; heartbeat = $null }
        while ($watch.Elapsed.TotalSeconds -lt 20 -and -not $demo.HasExited) {
            $heartbeat = $null # Do not reuse a formerly ready sample while waiting for a window.
            $demo.Refresh()
            foreach ($candidate in @(Get-ChildItem -LiteralPath (Join-Path $UserData 'logs') -Filter 'heartbeat.json' -Recurse -File -ErrorAction Stop)) {
                try { $sample = Get-Content -LiteralPath $candidate.FullName -Raw -Encoding UTF8 | ConvertFrom-Json }
                catch { continue } # Atomic replacement can race a read; retry within the bounded window.
                if ($sample.pid -ne $demo.Id) { continue }
                try {
                    $writtenUtc = Convert-HeartbeatUtc $sample.utc
                    $sampledUtc = Convert-HeartbeatUtc $sample.sampled_utc
                } catch { continue }
                $nowUtc = [DateTime]::UtcNow
                $lastHeartbeat = [ordered]@{ pid = $sample.pid; utc = $writtenUtc.ToString('o'); sampled_utc = $sampledUtc.ToString('o'); written_age_seconds = ($nowUtc - $writtenUtc).TotalSeconds; sampled_age_seconds = ($nowUtc - $sampledUtc).TotalSeconds; connected = [bool]$sample.connected; gui_ready = [bool]$sample.gui_ready; running = [bool]$sample.running; closed = [bool]$sample.closed; main_loop_progress_age_seconds = $sample.main_loop_progress_age_seconds }
                if ($writtenUtc -ge $demoStartedUtc -and $sampledUtc -ge $demoStartedUtc -and ($nowUtc - $writtenUtc).TotalSeconds -ge -2 -and ($nowUtc - $writtenUtc).TotalSeconds -lt 3 -and ($nowUtc - $sampledUtc).TotalSeconds -lt 3 -and $sample.gui_ready -and $sample.connected -and $sample.running -and -not $sample.closed -and $sample.main_loop_progress_age_seconds -lt 2) { $heartbeat = $sample; break }
            }
            $windows = @([InstallerNativeWindowProbe]::WindowsForProcess([uint32]$demo.Id))
            $matches = @($windows | Where-Object { Test-DemoWindow $_ $demo.Id })
            $Report.normal_demo.windows = $windows
            $Report.normal_demo.matching_windows = $matches.Count
            $Report.normal_demo.heartbeat = $lastHeartbeat
            if ($null -ne $heartbeat -and $matches.Count -eq 1) { $window = [IntPtr]$matches[0].Handle; $ready = $true; break }
            Start-Sleep -Milliseconds 200
        }
        $Report.normal_demo.ready = $ready
        Add-Check 'regular-native-demo-ready' $ready 'Default frozen Native entry must create an owned visible DEMO window and fresh ready/connected default session heartbeat.'
        $closingWindow = [InstallerNativeWindowProbe]::ReadWindow($window)
        Add-Check 'regular-native-demo-close-target' (Test-DemoWindow $closingWindow $demo.Id) 'Recheck exact HWND owner, visibility and Spitfire DEMO title immediately before WM_CLOSE.'
        Add-Check 'regular-native-demo-owned-close' ([InstallerNativeWindowProbe]::PostMessageW($window, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)) 'Send WM_CLOSE only to the verified own-PID Native window; no mouse/keyboard input.'
        $closed = Wait-OwnedProcess -Process $demo -Seconds 10
        $Report.normal_demo['visible_demo_window'] = $true
        $Report.normal_demo['gui_ready'] = [bool]$heartbeat.gui_ready
        $Report.normal_demo['connected'] = [bool]$heartbeat.connected
        $Report.normal_demo['default_diagnostics'] = $true
        $Report.normal_demo['exit_code'] = $closed.exit_code
        $Report.normal_demo['timed_out'] = $closed.timed_out
        Add-Check 'regular-native-demo-graceful-exit' (-not $closed.timed_out -and $closed.exit_code -eq 0) 'Normal Native window close must release the process and mutex without forced termination.'
        $DemoVerified = $true
    } finally {
        if (-not $demo.HasExited) { try { $demo.Kill(); [void]$demo.WaitForExit(5000) } catch { Add-Error 'regular-demo-cleanup' $_.Exception.Message } }
        $demo.Dispose()
    }
    Add-Check 'preexisting-userdata-after-demo' (Test-RetainedFiles $DataBefore) 'No preexisting default user-data file may be overwritten by the simulator phases.'
    $DataBeforeUninstall = Get-TreeRecords $UserData
} catch { Add-Error $Stage $_.Exception.Message }
finally {
    if ($InstallAttempted) {
        try {
            $uninstallers = @(Get-ChildItem -LiteralPath $InstallDirectory -Filter 'unins*.exe' -File -ErrorAction Stop)
            Add-Check 'owned-uninstaller-found' ($uninstallers.Count -eq 1) 'Use only the one uninstaller created in this previously empty test install.'
            if ($null -eq $DataBeforeUninstall) { $DataBeforeUninstall = Get-TreeRecords $UserData }
            $Report.uninstall = Invoke-OwnedProcess -File $uninstallers[0].FullName -Arguments @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/LOG=' + (Join-Path $OutputDirectory 'uninstaller.log'))) -Seconds $SetupTimeoutSeconds
            Add-Check 'silent-uninstall-exit' (-not $Report.uninstall.timed_out -and $Report.uninstall.exit_code -eq 0) 'Owned uninstall must exit0.'
            # Inno can finish removal from a temporary helper just after its launcher exits.
            $removeWatch = [Diagnostics.Stopwatch]::StartNew()
            while ((Test-Path -LiteralPath $Executable) -and $removeWatch.Elapsed.TotalSeconds -lt 10) { Start-Sleep -Milliseconds 100 }
            Add-Check 'app-executable-removed' (-not (Test-Path -LiteralPath $Executable)) 'The application-owned executable must be removed.'
            Add-Check 'app-registration-removed' (@(Get-AppRegistrations).Count -eq 0) 'The application-owned uninstall registration must be removed.'
            $UninstallVerified = $true
            $allRetained = (Test-RetainedFiles $DataBefore) -and (Test-RetainedFiles $DataBeforeUninstall) -and (Test-Path -LiteralPath $Sentinel -PathType Leaf)
            if ($allRetained) { $allRetained = (Get-FileHash -LiteralPath $Sentinel -Algorithm SHA256).Hash.ToLowerInvariant() -eq $sentinelHash }
            Add-Check 'default-userdata-retained' $allRetained 'Existing user files, newly created session files and the unique test sentinel must survive uninstall.'
            $Report.userdata = [ordered]@{ preexisting_files = $DataBefore.Count; files_before_uninstall = $DataBeforeUninstall.Count; preexisting_files_unchanged = [bool]$allRetained; new_session_files_retained = [bool]$allRetained; sentinel_retained = [bool]$allRetained; sentinel_sha256 = $sentinelHash; default_known_folder_used = $true }
            $UserDataVerified = $true
        } catch { Add-Error 'uninstall-and-retention' $_.Exception.Message }
    }
    if ($null -ne $Before) {
        $after = Get-IsolationSnapshot
        $Report.fingerprints['after_uninstall'] = $after
        $IsolationVerified = Compare-Isolation $Before $after 'after_uninstall'
    }
    $Report.checks = $script:Checks.ToArray()
    $Report.errors = $script:Errors.ToArray()
    $failed = @($script:Checks | Where-Object { -not $_.passed }).Count
    $Report.passed = $InstallVerified -and $ManifestVerified -and $NativeVerified -and $DemoVerified -and $UninstallVerified -and $IsolationVerified -and $UserDataVerified -and $failed -eq 0 -and $script:Errors.Count -eq 0
    $Report['completed_utc'] = [DateTime]::UtcNow.ToString('o')
    if ($OutputOwned -and (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
        $json = ConvertTo-Json -InputObject $Report -Depth 20
        [IO.File]::WriteAllText($ReportPath, $json + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    }
}
if ($Report.passed) { Write-Host ('PASS: ' + $ReportPath); exit 0 }
foreach ($failure in $script:Errors) {
    Write-Warning ('Validation error [' + $failure.phase + ']: ' + $failure.error)
}
foreach ($check in $script:Checks) {
    if (-not $check.passed) { Write-Warning ('Failed check [' + $check.name + ']: ' + $check.detail) }
}
if ($OutputOwned -and (Test-Path -LiteralPath $ReportPath -PathType Leaf)) {
    Write-Error ('Installer validation did not pass. See ' + $ReportPath) -ErrorAction Continue
} else {
    Write-Error 'Installer validation did not pass. No report was created; preflight rejected the paths before taking ownership. See the phase/error summary above.' -ErrorAction Continue
}
exit 1

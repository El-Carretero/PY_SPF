[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Python32,
    [Parameter(Mandatory = $true)][string]$SignedInstaller,
    [string]$HelperPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'tools\install_windows.ps1'),
    [string]$OutputPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'analysis\windows-installer-results.json')
)
# Run on Windows with a previously installed x86 Python and an authentic cached
# CPython installer. Installer execution and downloads are mocked; Python probes
# and Authenticode validation are real. No application or instrument is started.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($HelperPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw "Installer helper has PowerShell parse errors: $parseErrors" }
foreach ($definition in $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    Invoke-Expression $definition.Extent.Text
}
$script:checks = New-Object 'System.Collections.Generic.List[object]'
$script:pythonProbeResults = New-Object 'System.Collections.Generic.List[object]'
$script:fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('spitfire-installer-tests-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null
$script:signedFixture = (Resolve-Path -LiteralPath $SignedInstaller).Path
$script:actualPython32 = (Resolve-Path -LiteralPath $Python32).Path
$script:setupCalls = New-Object 'System.Collections.Generic.List[object]'
$script:scenario = ''

function Assert-Installer([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Run-InstallerCase([string]$Name, [scriptblock]$Body) {
    try {
        & $Body
        $script:checks.Add([PSCustomObject]@{name = $Name; passed = $true})
        Write-Host "PASS $Name"
    } catch {
        $message = $_.Exception.Message.Replace($script:fixtureRoot, '<test-directory>').Replace($script:actualPython32, '<python32>')
        $script:checks.Add([PSCustomObject]@{name = $Name; passed = $false; error = $message})
        Write-Host "FAIL $Name`: $message"
    }
}
function Set-InstallerFixture([string]$Name) {
    $script:scenario = $Name
    $script:project = Join-Path $script:fixtureRoot $Name
    $script:logs = Join-Path $script:project 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $script:setupCalls.Clear()
}
# These shadow cmdlets/functions only inside this test process. In particular,
# the signed setup executable is NEVER executed by this harness.
function script:Invoke-WebRequest {
    param($Uri, [string]$OutFile, [switch]$UseBasicParsing)
    Copy-Item -LiteralPath $script:signedFixture -Destination $OutFile
}
function script:Start-Process {
    param([string]$FilePath, [object[]]$ArgumentList, [switch]$Wait, [switch]$PassThru)
    Assert-Installer ((Split-Path -Leaf $FilePath) -eq 'python-3.13.9-win32.exe') 'Unexpected external process requested'
    $script:setupCalls.Add(@($ArgumentList))
    $isRepair = $ArgumentList -contains '/repair'
    $logName = if ($isRepair) { 'python32-repair.log' } else { 'python32-setup.log' }
    $oldDirectory = if ($script:scenario -eq 'log-derived-existing-location') { Split-Path -Parent $script:actualPython32 } else { Join-Path $script:project 'old-nested\.python32' }
    @(
        "[fixture] Setting string variable 'TargetDir' to value '$oldDirectory'",
        '[fixture] Setting numeric variable ''WixBundleInstalled'' to value 1',
        '[fixture] Applying execute package: exe_JustForMe, action: None',
        '[fixture] Apply complete, result: 0x0'
    ) | Set-Content -LiteralPath (Join-Path $script:logs $logName)
    $code = if ($script:scenario -eq 'restart-required') { 3010 } elseif ($isRepair -and $script:scenario -eq 'repair-failed') { 1603 } else { 0 }
    return [PSCustomObject]@{ExitCode = $code}
}
function script:Find-Python([int]$Bits) {
    if ($script:scenario -eq 'registered-existing-location') { return $script:actualPython32 }
    if ($script:scenario -eq 'stale-location-repaired' -and $script:setupCalls.Count -ge 2) { return $script:actualPython32 }
    return $null
}
try {
    Run-InstallerCase 'authentic-signed-installer-fixture' {
        $signature = Get-AuthenticodeSignature -LiteralPath $script:signedFixture
        Assert-Installer ($signature.Status -eq 'Valid') 'Fixture installer signature is invalid'
        Assert-Installer ($signature.SignerCertificate.Subject -match 'O=Python Software Foundation') 'Fixture publisher is not PSF'
    }
    Run-InstallerCase 'real-python32-isolated-from-poisoned-python-environment' {
        $savedHome = $env:PYTHONHOME
        $savedPath = $env:PYTHONPATH
        try {
            $env:PYTHONHOME = Join-Path $script:fixtureRoot 'nonexistent-python-home'
            $env:PYTHONPATH = Join-Path $script:fixtureRoot 'nonexistent-python-path'
            $probe = Get-PythonProbe $script:actualPython32 32
            Assert-Installer $probe.compatible ('Isolated interpreter probe failed: ' + $probe.stderr)
            Assert-Installer ($probe.exit_code -eq 0) 'Isolated interpreter probe did not exit successfully'
            $metadata = $probe.stdout | ConvertFrom-Json
            Assert-Installer ($metadata.bits -eq 32) 'Probe did not identify x86 interpreter'
            Invoke-Python -Executable $script:actualPython32 -Arguments @('-c', 'import struct; assert struct.calcsize(chr(80)) == 4')
        } finally { $env:PYTHONHOME = $savedHome; $env:PYTHONPATH = $savedPath }
    }
    Run-InstallerCase 'probe-reports-missing-and-wrong-architecture' {
        $missing = Get-PythonProbe (Join-Path $script:fixtureRoot 'missing-python.exe') 32
        Assert-Installer (-not $missing.compatible -and -not $missing.exists -and [bool]$missing.reason) 'Missing interpreter was not diagnosed'
        $wrong = Get-PythonProbe $script:actualPython32 64
        Assert-Installer (-not $wrong.compatible -and $wrong.exit_code -ne 0 -and [bool]$wrong.stdout) 'Wrong interpreter bitness was not diagnosed'
    }
    $script:stubExecutable = Join-Path $script:fixtureRoot ('spitfire-probe-' + [Guid]::NewGuid().ToString('N') + '.exe')
    Add-Type -OutputAssembly $script:stubExecutable -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Reflection;
using System.Threading;
public class InstallerProbeStub {
    public static void Main() {
        string mode = Environment.GetEnvironmentVariable("SPITFIRE_PROBE_STUB_MODE");
        if (mode == "child") { Thread.Sleep(60000); return; }
        if (mode == "hang") {
            var child = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location);
            child.UseShellExecute = false;
            child.CreateNoWindow = true;
            child.EnvironmentVariables["SPITFIRE_PROBE_STUB_MODE"] = "child";
            Process.Start(child);
            Thread.Sleep(60000);
        }
    }
}
'@
    Run-InstallerCase 'zero-exit-without-python-identity-is-not-compatible' {
        $probe = Get-PythonProbe $script:stubExecutable 32
        Assert-Installer ($probe.exit_code -eq 0 -and -not $probe.compatible) 'An executable returning zero without Python identity was accepted'
    }
    Run-InstallerCase 'probe-timeout-kills-owned-child-tree-and-returns-within-bound' {
        $savedMode = $env:SPITFIRE_PROBE_STUB_MODE
        try {
            $env:SPITFIRE_PROBE_STUB_MODE = 'hang'
            $watch = [Diagnostics.Stopwatch]::StartNew()
            $probe = Get-PythonProbe $script:stubExecutable 32
            $watch.Stop()
            Assert-Installer (-not $probe.compatible -and $probe.reason -match 'timed out|timeout') 'Hanging interpreter was not diagnosed as timed out'
            Assert-Installer ($watch.Elapsed.TotalSeconds -lt 20) 'Probe exceeded its timeout and bounded output-read allowance'
            $remaining = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($script:stubExecutable)) -ErrorAction SilentlyContinue)
            Assert-Installer ($remaining.Count -eq 0) 'Timed-out probe left an owned descendant running'
        } finally {
            $env:SPITFIRE_PROBE_STUB_MODE = $savedMode
            Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($script:stubExecutable)) -ErrorAction SilentlyContinue | Stop-Process -Force
        }
    }
    Run-InstallerCase 'setup-accepts-working-registered-location' {
        Set-InstallerFixture 'registered-existing-location'
        $python = Install-ProjectPython32
        Assert-Installer ($python -eq $script:actualPython32) 'Registered working interpreter was not reused'
        Assert-Installer ($script:setupCalls.Count -eq 1) 'Working registered interpreter triggered unnecessary repair'
    }
    Run-InstallerCase 'setup-log-retains-old-working-location' {
        Set-InstallerFixture 'log-derived-existing-location'
        $python = Install-ProjectPython32
        Assert-Installer ($python -eq $script:actualPython32) 'Old working TargetDir from setup log was not reused'
        Assert-Installer ($script:setupCalls.Count -eq 1) 'Log-derived working interpreter triggered unnecessary repair'
    }
    Run-InstallerCase 'maintenance-noop-then-one-repair-restores-registered-interpreter' {
        Set-InstallerFixture 'stale-location-repaired'
        $python = Install-ProjectPython32
        Assert-Installer ($python -eq $script:actualPython32) 'Repaired registered interpreter was not rediscovered'
        Assert-Installer ($script:setupCalls.Count -eq 2) 'Expected exactly one setup and one repair'
        Assert-Installer ($script:setupCalls[1] -contains '/repair') 'Recovery did not request repair'
        Assert-Installer (-not ($script:setupCalls[1] -match '^TargetDir=')) 'Repair must preserve registered install location'
    }
    Run-InstallerCase 'unrecoverable-install-has-bounded-repair-and-diagnostic-log-links' {
        Set-InstallerFixture 'unrecoverable'
        $failure = ''
        try { $null = Install-ProjectPython32 } catch { $failure = $_.Exception.Message }
        Assert-Installer ([bool]$failure) 'Unrecoverable setup unexpectedly succeeded'
        Assert-Installer ($script:setupCalls.Count -eq 2) 'Unrecoverable setup did not stop after one repair'
        Assert-Installer ($failure -match 'python-probes\.json' -and $failure -match 'python32-repair\.log') 'Failure lacks diagnostic log locations'
    }
    Run-InstallerCase 'restart-required-status-is-visible-without-reboot' {
        Set-InstallerFixture 'restart-required'
        $failure = ''
        try { $null = Install-ProjectPython32 } catch { $failure = $_.Exception.Message }
        Assert-Installer ($failure -match 'restart') 'Windows restart requirement was not surfaced'
        Assert-Installer ($script:setupCalls.Count -le 2) 'Restart case retried without bound'
    }
    Run-InstallerCase 'repair-failure-reports-exit-code-and-log' {
        Set-InstallerFixture 'repair-failed'
        $failure = ''
        try { $null = Install-ProjectPython32 } catch { $failure = $_.Exception.Message }
        Assert-Installer ($failure -match '1603' -and $failure -match 'python32-repair\.log') 'Repair failure lacks exit code/log'
    }
} finally {
    $report = [ordered]@{
        passed = @($script:checks | Where-Object { -not $_.passed }).Count -eq 0
        checks = @($script:checks.ToArray())
        setup_execution = 'Mocked; authentic signed fixture validated, no setup or repair process executed'
        python_execution = 'Actual x86 interpreter probes and isolated Python command; no application or instrument started'
        coverage = 'Maintenance no-op and repair scenarios are fixtures; they do not repair the unavailable user computer'
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    Remove-Item -LiteralPath $script:fixtureRoot -Recurse -Force
}
if (-not $report.passed) { exit 1 }
exit 0

[CmdletBinding()]
param(
    [ValidateSet("Offline", "Hardware")][string]$Mode = "Offline",
    [string]$HostAddress = "",
    [string]$LocalAddress = "0.0.0.0",
    [ValidateRange(1, 65535)][int]$RemotePort = 1024,
    [ValidateRange(0, 65535)][int]$LocalPort = 1024,
    [ValidateRange(1, 5)][int]$Cycles = 1,
    [string]$ExpectIdn = "",
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "validation_reports"),
    [string]$PythonExecutable = "",
    [string]$ExePath = ""
)
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Run this wrapper on Windows." }
if ($Mode -eq "Hardware" -and [string]::IsNullOrWhiteSpace($HostAddress)) {
    throw "Hardware mode requires -HostAddress with the controller's explicit IPv4 address."
}
if ($Mode -eq "Offline" -and -not [string]::IsNullOrWhiteSpace($HostAddress)) {
    throw "-HostAddress is only valid in Hardware mode."
}
if ($PythonExecutable) {
    $pythonCommand = $PythonExecutable
    $pythonPrefix = @()
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = "py"
    $pythonPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = "python"
    $pythonPrefix = @()
} else {
    throw "Python 3.10+ with Tk is required. See docs/AUTOMATED_VALIDATION.md."
}
$arguments = @((Join-Path $PSScriptRoot "validate_spitfire.py"), $Mode.ToLowerInvariant(), "--output", $OutputDirectory)
if ($ExePath) { $arguments += @("--exe", $ExePath) }
if ($Mode -eq "Hardware") {
    $arguments += @("--host", $HostAddress, "--local-host", $LocalAddress,
                    "--remote-port", "$RemotePort", "--local-port", "$LocalPort", "--cycles", "$Cycles")
    if ($ExpectIdn) { $arguments += @("--expect-idn", $ExpectIdn) }
}
# No elevation, installation, firewall/NIC change, device scanning or policy change.
& $pythonCommand @pythonPrefix @arguments
exit $LASTEXITCODE

$ErrorActionPreference = "Stop"
function Invoke-PythonStep {
    param([string[]]$Arguments)
    & py @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python build step failed (exit $LASTEXITCODE)." }
}
Push-Location $PSScriptRoot
try {
    Invoke-PythonStep -Arguments @("-m", "pip", "install", "--no-index", "--find-links", "$PSScriptRoot\release\vendor", "pyserial==3.5")
    Invoke-PythonStep -Arguments @("-m", "pip", "install", "-e", ".", "--no-deps")
    Invoke-PythonStep -Arguments @("-m", "pip", "install", "-r", "requirements-dev.txt")
    Invoke-PythonStep -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                                 "--name", "SpitfirePythonControl", "--collect-all", "serial", "--paths", "src", "run_spitfire.py")
    $exe = Join-Path $PSScriptRoot "dist\SpitfirePythonControl.exe"
    $manifest = [ordered]@{
        self_test_protocol = 1
        version = "1.3.0"
        file = "SpitfirePythonControl.exe"
        sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    # Hash record for accidental EXE mix-ups; not a digital signature.
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot "dist\SpitfirePythonControl.validation.json") -Encoding UTF8
    Write-Host "Built: $exe"
    Write-Host 'Validate with: .\validate_windows.ps1 -ExePath .\dist\SpitfirePythonControl.exe'
} finally {
    Pop-Location
}

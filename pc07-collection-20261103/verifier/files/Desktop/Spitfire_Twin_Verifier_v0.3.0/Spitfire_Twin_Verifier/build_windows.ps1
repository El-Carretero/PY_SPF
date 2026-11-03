[CmdletBinding()]
param([string]$Python = "py")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$venv = Join-Path $PSScriptRoot ".build-venv"
if ($Python -eq "py") {
    & py -3 -m venv $venv
} else {
    & $Python -m venv $venv
}
if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
$pythonExe = Join-Path $venv "Scripts\python.exe"
& $pythonExe -m pip install --upgrade pip setuptools pyinstaller
if ($LASTEXITCODE -ne 0) { throw "build dependency installation failed" }
& $pythonExe -m pip install .
if ($LASTEXITCODE -ne 0) { throw "package installation failed" }
& $pythonExe -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name SpitfireTwinVerifier --add-data "src/spitfire_twin_verifier/data:spitfire_twin_verifier/data" --paths src run_verifier.py
if ($LASTEXITCODE -ne 0) { throw "GUI EXE build failed" }
& $pythonExe -m PyInstaller --noconfirm --clean --onefile --console `
    --name SpitfireTwinVerifierCLI --add-data "src/spitfire_twin_verifier/data:spitfire_twin_verifier/data" --paths src run_verifier.py
if ($LASTEXITCODE -ne 0) { throw "CLI EXE build failed" }
& .\dist\SpitfireTwinVerifierCLI.exe --self-test --output build_verification_reports
if ($LASTEXITCODE -ne 0) { throw "Frozen EXE self-test failed" }
Write-Host "완료: dist\SpitfireTwinVerifier.exe, dist\SpitfireTwinVerifierCLI.exe"


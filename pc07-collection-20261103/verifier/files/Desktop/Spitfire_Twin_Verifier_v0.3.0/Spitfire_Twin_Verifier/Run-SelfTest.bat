@echo off
setlocal
cd /d "%~dp0"
if exist "dist\SpitfireTwinVerifierCLI.exe" (
  "dist\SpitfireTwinVerifierCLI.exe" --self-test --output verification_reports
) else (
  py -3 run_verifier.py --self-test --output verification_reports
)
pause
endlocal

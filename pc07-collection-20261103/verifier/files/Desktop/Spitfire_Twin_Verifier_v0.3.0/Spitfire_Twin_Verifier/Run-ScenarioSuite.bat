@echo off
setlocal
cd /d "%~dp0"
if exist "dist\SpitfireTwinVerifierCLI.exe" (
  "dist\SpitfireTwinVerifierCLI.exe" --scenario-suite --output verification_reports
) else (
  py -3 run_verifier.py --scenario-suite --output verification_reports
)
pause
endlocal

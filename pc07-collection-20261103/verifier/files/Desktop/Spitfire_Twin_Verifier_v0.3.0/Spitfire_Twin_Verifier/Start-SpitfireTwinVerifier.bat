@echo off
setlocal
cd /d "%~dp0"
if exist "dist\SpitfireTwinVerifier.exe" (
  start "" "dist\SpitfireTwinVerifier.exe"
  exit /b 0
)
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 run_verifier.py
) else (
  python run_verifier.py
)
if not %ERRORLEVEL% EQU 0 pause
endlocal

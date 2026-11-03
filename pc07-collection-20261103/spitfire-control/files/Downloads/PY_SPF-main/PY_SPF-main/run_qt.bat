@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run_spitfire.py --backend qt %*
set "SPF_RC=%ERRORLEVEL%"
if not "%SPF_RC%"=="0" pause
exit /b %SPF_RC%

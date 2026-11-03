@echo off
setlocal
cd /d "%~dp0"
if exist "dist\SpitfirePythonControl.exe" goto executable
if exist ".venv\Scripts\python.exe" (
  set "SPITFIRE_PY=.venv\Scripts\python.exe"
  goto launch
)
where py >nul 2>&1
if not errorlevel 1 (
  set "SPITFIRE_PY=py -3"
  goto launch
)
where python >nul 2>&1
if not errorlevel 1 (
  set "SPITFIRE_PY=python"
  goto launch
)
echo Python 3.10 or newer is required. Install Python, then run install_windows.cmd.
exit /b 1
:launch
echo External Pump: connecting to the configured TDG over UDP. DM1 is controlled separately.
%SPITFIRE_PY% run_spitfire.py --udp --pump-mode external %*
exit /b %errorlevel%
:executable
echo External Pump: connecting to the configured TDG over UDP. DM1 is controlled separately.
"dist\SpitfirePythonControl.exe" --udp --pump-mode external %*
exit /b %errorlevel%

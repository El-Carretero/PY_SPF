@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
  goto install
)
where python >nul 2>&1
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install Python with Tk support first.
  exit /b 1
)
python -m venv .venv
if errorlevel 1 exit /b 1
:install
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 'Python 3.10 or newer is required')"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --no-index --find-links "release\vendor" pyserial==3.5
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -c "import tkinter, serial; print('Installation complete. Run start_external_demo.cmd first.')"
exit /b %errorlevel%

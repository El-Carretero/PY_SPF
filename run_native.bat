@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install.bat native first.
    exit /b 1
)
".venv\Scripts\python.exe" run_spitfire.py --backend native %*
exit /b %errorlevel%

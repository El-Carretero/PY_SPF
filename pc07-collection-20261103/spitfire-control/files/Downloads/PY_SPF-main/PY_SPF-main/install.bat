@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "SPF_NO_PAUSE="
if /I "%~1"=="--no-pause" set "SPF_NO_PAUSE=1"
set "SPF_RC=1"

if not exist "pyproject.toml" (
  echo [ERROR] pyproject.toml was not found beside install.bat.
  goto finish
)
if exist ".venv\Scripts\python.exe" goto check_environment

echo [1/4] Creating a project virtual environment...
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys,struct;sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv ".venv"
    if errorlevel 1 goto create_failed
    goto check_environment
  )
)
where python >nul 2>&1
if not errorlevel 1 (
  python -c "import sys,struct;sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
  if not errorlevel 1 (
    python -m venv ".venv"
    if errorlevel 1 goto create_failed
    goto check_environment
  )
)
echo [ERROR] Install 64-bit Python 3.10 or newer, then run this file again.
echo Python download: https://www.python.org/downloads/windows/
goto finish

:create_failed
echo [ERROR] Failed to create .venv. Check the Python installation and folder permissions.
goto finish

:check_environment
".venv\Scripts\python.exe" -c "import sys,struct;print('Python:',sys.version.split()[0],str(struct.calcsize('P')*8)+'-bit');sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
  echo [ERROR] The existing .venv is not a usable 64-bit Python 3.10+ environment.
  echo Rename .venv to keep a backup, then run install.bat again.
  goto finish
)

echo [2/4] Updating Python packaging tools...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto install_failed

echo [3/4] Installing the project with Qt, test and analysis dependencies...
".venv\Scripts\python.exe" -m pip install --editable ".[qt,test,analysis]" "Pillow>=10"
if errorlevel 1 goto install_failed

echo [4/4] Checking package dependencies and imports...
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -c "import spitfire,PySide6,pytest,pefile,unicorn,capstone,PIL;from PySide6.QtWidgets import QApplication;print('Spitfire',spitfire.__version__,'/ Qt',PySide6.__version__);print('All declared optional dependencies imported successfully.')"
if errorlevel 1 goto install_failed

echo.
echo [OK] Installation complete.
echo To start the Qt GUI: run_qt.bat
echo To start the demo:   run_qt.bat --demo --tcp-port 0
echo The NI native backend needs a separate 32-bit Python environment.
set "SPF_RC=0"
goto finish

:install_failed
echo.
echo [ERROR] Installation or verification failed. Review the error above.
echo Check the internet connection and run install.bat again.

:finish
if not defined SPF_NO_PAUSE pause
exit /b %SPF_RC%

@echo off
setlocal
cd /d "%~dp0"

rem Usage: install.bat [auto^|qt^|native] [path-to-python.exe]
rem auto selects Qt on 64-bit Python and the original NI GUI on 32-bit Python.
set "SPITFIRE_MODE=%~1"
if not defined SPITFIRE_MODE set "SPITFIRE_MODE=auto"
if /i "%SPITFIRE_MODE%"=="auto" goto select_python
if /i "%SPITFIRE_MODE%"=="qt" goto select_python
if /i "%SPITFIRE_MODE%"=="native" goto select_python
echo Usage: install.bat [auto^|qt^|native] [path-to-python.exe]
exit /b 2

:select_python
set "SPITFIRE_PYTHON=%~2"
if defined SPITFIRE_PYTHON goto check_python
if /i "%SPITFIRE_MODE%"=="native" for /f "delims=" %%P in ('py -3-32 -c "import sys; print(sys.executable)" 2^>nul') do set "SPITFIRE_PYTHON=%%P"
if defined SPITFIRE_PYTHON goto check_python
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "SPITFIRE_PYTHON=%%P"
if defined SPITFIRE_PYTHON goto check_python
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "SPITFIRE_PYTHON=%%P"
if defined SPITFIRE_PYTHON goto check_python
echo ERROR: Python 3.10 or newer was not found. Install Python and run this file again.
exit /b 1

:check_python
"%SPITFIRE_PYTHON%" -c "import sys; raise SystemExit(sys.version_info < (3, 10))"
if errorlevel 1 goto python_error
if exist ".venv\Scripts\python.exe" goto check_venv
if exist ".venv" goto invalid_venv
if /i "%SPITFIRE_MODE%"=="native" (
    "%SPITFIRE_PYTHON%" -c "import struct; raise SystemExit(struct.calcsize('P') != 4)"
    if errorlevel 1 goto native_architecture_error
)
if /i "%SPITFIRE_MODE%"=="qt" (
    "%SPITFIRE_PYTHON%" -c "import struct; raise SystemExit(struct.calcsize('P') != 8)"
    if errorlevel 1 goto qt_architecture_error
)
"%SPITFIRE_PYTHON%" -m venv ".venv"
if errorlevel 1 goto failed

:check_venv
rem Check the environment actually used, including an existing installation.
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info < (3, 10))"
if errorlevel 1 goto python_error
set "SPITFIRE_BITS="
for /f %%B in ('.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"') do set "SPITFIRE_BITS=%%B"
if not defined SPITFIRE_BITS goto failed
if /i not "%SPITFIRE_MODE%"=="auto" goto check_architecture
set "SPITFIRE_MODE=qt"
if "%SPITFIRE_BITS%"=="32" set "SPITFIRE_MODE=native"

:check_architecture
if /i "%SPITFIRE_MODE%"=="native" if not "%SPITFIRE_BITS%"=="32" goto native_architecture_error
if /i "%SPITFIRE_MODE%"=="qt" if not "%SPITFIRE_BITS%"=="64" goto qt_architecture_error
echo Installing %SPITFIRE_MODE% dependencies in "%CD%\.venv" ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
if /i "%SPITFIRE_MODE%"=="native" goto install_package
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

:install_package
rem Native mode uses ctypes and the bundled NI resources; it needs no Qt wheel.
".venv\Scripts\python.exe" -m pip install .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
echo Installation completed. No instrument connection was opened.
echo Demo: run_demo.bat
if /i "%SPITFIRE_MODE%"=="native" echo Original NI GUI: run_native.bat
if /i "%SPITFIRE_MODE%"=="qt" echo Qt GUI: ".venv\Scripts\python.exe" run_spitfire.py --backend qt
exit /b 0

:native_architecture_error
echo ERROR: Native NI GUI requires 32-bit Python 3.10 or newer.
echo If .venv exists, move it aside; then run install.bat native with a 32-bit Python executable.
exit /b 1

:qt_architecture_error
echo ERROR: Qt mode requires 64-bit Python. PySide6 has no Windows x86 wheel.
echo Use install.bat native for 32-bit Python, or move .venv aside and select 64-bit Python.
exit /b 1

:invalid_venv
echo ERROR: .venv exists but has no Windows Python executable.
echo Move it aside before running install.bat again.
exit /b 1

:python_error
echo ERROR: A working Python 3.10 or newer is required.
exit /b 1

:failed
echo ERROR: Installation failed. Check the command output above.
exit /b 1

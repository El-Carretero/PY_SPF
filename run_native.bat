@echo off
setlocal
cd /d "%~dp0"
set "SPITFIRE_PYTHON=%~dp0.venv-native\Scripts\python.exe"
if exist "%SPITFIRE_PYTHON%" (
    "%SPITFIRE_PYTHON%" -c "import struct,sys; raise SystemExit(not (sys.version_info >= (3,10) and struct.calcsize('P') == 4))" >nul 2>&1
    if not errorlevel 1 goto launch
)
set "SPITFIRE_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%SPITFIRE_PYTHON%" (
    "%SPITFIRE_PYTHON%" -c "import struct,sys; raise SystemExit(not (sys.version_info >= (3,10) and struct.calcsize('P') == 4))" >nul 2>&1
    if not errorlevel 1 goto launch
)
call "%~dp0install.bat" native
if errorlevel 1 exit /b %errorlevel%
set "SPITFIRE_PYTHON=%~dp0.venv-native\Scripts\python.exe"
:launch
if not exist "logs" mkdir "logs"
>"logs\native-launch.log" echo Native launch: %date% %time%
"%SPITFIRE_PYTHON%" -u "%~dp0run_spitfire.py" --backend native %* 2>>"logs\native-launch.log"
set "SPITFIRE_RESULT=%errorlevel%"
if "%SPITFIRE_RESULT%"=="0" exit /b 0
echo Native GUI failed. Details are saved in logs\native-launch.log.
type "logs\native-launch.log"
if not "%SPITFIRE_NO_PAUSE%"=="1" pause
exit /b %SPITFIRE_RESULT%

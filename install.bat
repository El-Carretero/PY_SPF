@echo off
setlocal
cd /d "%~dp0"
rem Double-click installs the original NI GUI with its own 32-bit environment.
rem Optional: install.bat qt [path-to-64-bit-python.exe]
set "SPITFIRE_MODE=%~1"
if not defined SPITFIRE_MODE set "SPITFIRE_MODE=native"
if not exist "logs" mkdir "logs"
>"logs\install-bootstrap-errors.log" echo Installation start: %date% %time%
if not "%~2"=="" goto custom_python
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_windows.ps1" -Mode "%SPITFIRE_MODE%" 2>>"logs\install-bootstrap-errors.log"
goto finished
:custom_python
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_windows.ps1" -Mode "%SPITFIRE_MODE%" -PythonPath "%~2" 2>>"logs\install-bootstrap-errors.log"
:finished
set "SPITFIRE_RESULT=%errorlevel%"
if "%SPITFIRE_RESULT%"=="0" exit /b 0
echo Installation failed. See logs\install-%SPITFIRE_MODE%.log and logs\install-bootstrap-errors.log.
if exist "logs\install-bootstrap-errors.log" type "logs\install-bootstrap-errors.log"
if not "%SPITFIRE_NO_PAUSE%"=="1" pause
exit /b %SPITFIRE_RESULT%

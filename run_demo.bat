@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-native\Scripts\python.exe" goto native_demo
if exist ".venv\Scripts\python.exe" goto qt_demo
call "%~dp0install.bat" native
if errorlevel 1 exit /b %errorlevel%
:native_demo
call "%~dp0run_native.bat" --demo --tcp-port 0 %*
exit /b %errorlevel%
:qt_demo
if not exist "logs" mkdir "logs"
>"logs\demo-launch.log" echo Demo launch: %date% %time%
".venv\Scripts\python.exe" -u "%~dp0run_spitfire.py" --demo --tcp-port 0 %* 2>>"logs\demo-launch.log"
set "SPITFIRE_RESULT=%errorlevel%"
if "%SPITFIRE_RESULT%"=="0" exit /b 0
echo Demo failed. Details are saved in logs\demo-launch.log.
type "logs\demo-launch.log"
if not "%SPITFIRE_NO_PAUSE%"=="1" pause
exit /b %SPITFIRE_RESULT%

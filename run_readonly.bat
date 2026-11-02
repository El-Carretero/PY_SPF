@echo off
setlocal
cd /d "%~dp0"
call "%~dp0run_native.bat" --read-only --tcp-port 0 %*
exit /b %errorlevel%

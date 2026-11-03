@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0Setup-SpitfireXP.ps1"
set "setup_exit=%ERRORLEVEL%"
echo.
echo Setup helper exit code: %setup_exit%
echo 0 = VM prepared; 1 = error; 2 = required file not selected; 3 = restart needed.
pause
exit /b %setup_exit%

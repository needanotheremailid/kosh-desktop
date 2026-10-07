@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
    echo Setup stopped. Read the prerequisite error above; your data was not removed.
    pause
    exit /b 1
)
pause

@echo off
if not exist "%~dp0bin\ResearchDesktop.exe" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if not exist "%~dp0bin\ResearchDesktop.exe" exit /b 1
start "" "%~dp0bin\ResearchDesktop.exe"

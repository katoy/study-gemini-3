@echo off
REM Windows setup wrapper for Kindle to PDF
REM Calls setup_win.bat if present, otherwise suggests PowerShell script.

if exist "%~dp0setup_win.bat" (
  call "%~dp0setup_win.bat"
  exit /b %errorlevel%
)

echo setup_win.bat not found. Trying PowerShell script...
powershell -ExecutionPolicy Bypass -File "%~dp0setup_win.ps1"

exit /b 0

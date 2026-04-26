@echo off
REM Wrapper to run PowerShell runner (run_win.ps1)
powershell -ExecutionPolicy Bypass -File "%~dp0run_win.ps1" %*

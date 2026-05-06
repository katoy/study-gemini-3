@echo off
REM Kindle App to PDF - Run script (Windows)

setlocal enabledelayedexpansion

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Check uv availability
where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv not found.
    echo         Please install from: https://github.com/astral-sh/uv
    echo         or: winget install astral-sh.uv
    pause
    exit /b 1
)

echo === Kindle App to PDF (Windows) ===
echo.

REM Create virtual environment if not exists
if not exist ".venv" (
    echo Creating virtual environment...
    call uv venv
    echo.
)

REM Activate virtual environment
call .venv\Scripts\Activate.bat

REM Run
echo Open Kindle for PC, display the first page, and press Enter.
echo.

uv run python main.py %*

pause

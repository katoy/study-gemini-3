@echo off
REM Kindle App to PDF - Setup script (Windows batch version)

setlocal enabledelayedexpansion

echo === Kindle App to PDF - Windows Setup ===
echo.

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Please install from https://www.python.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo OK: %PYTHON_VERSION%

REM Check uv availability
where uv >nul 2>&1
if errorlevel 1 (
    echo Info: uv not installed.
    echo       For faster setup, install from: https://github.com/astral-sh/uv
    echo       or: winget install astral-sh.uv
    echo.
    echo Setting up with pip...
    echo.

    REM Setup with pip
    if not exist ".venv" (
        echo Creating virtual environment...
        python -m venv .venv
    )

    echo Activating virtual environment...
    call .venv\Scripts\Activate.bat

    echo Installing dependencies...
    python -m pip install --upgrade pip --quiet
    pip install -r requirements.txt
) else (
    for /f "tokens=*" %%i in ('uv --version 2^>^&1') do set UV_VERSION=%%i
    echo OK: %UV_VERSION%
    echo.
    echo [RECOMMENDED] Setting up with uv (faster)
    echo Creating virtual environment...
    call uv venv

    echo Activating virtual environment...
    call .venv\Scripts\Activate.bat

    echo Installing dependencies...
    call uv pip install -r requirements.txt
)

echo.
echo === Setup Complete ===
echo.
echo [Usage]
echo   1. Open Kindle for PC and display the first page you want to capture.
echo   2. Run:
echo.
echo      run.bat
echo.
echo      or:
echo      python main.py
echo      uv run python main.py
echo.
echo [Options]
echo   --direction {right^|left^|space}  : Page turn direction (default: right)
echo   --page-delay SECONDS            : Wait time after page turn (default: 1.5)
echo.
echo [Notes]
echo   - Do not interact with Kindle window during capture.
echo   - For high DPI environments, set Windows display scale to 100%%.
echo.
pause

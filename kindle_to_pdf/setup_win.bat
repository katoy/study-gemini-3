@echo off
rem Kindle to PDF - Windows 11 setup script (clean)
setlocal

rem Check Python availability
python --version >nul 2>&1 || (
  echo Python not found. Install Python 3.8+ from https://www.python.org/downloads/ and ensure "python" is on PATH.
  pause
  exit /b 1
)

rem Create virtualenv if missing
if not exist ".venv\Scripts\activate" (
  echo Creating virtual environment (.venv)...
  python -m venv .venv || (
    echo Failed to create virtualenv.
    pause
    exit /b 1
  )
)

rem Activate venv
call .venv\Scripts\activate
if errorlevel 1 (
  echo Failed to activate virtual environment.
  pause
  exit /b 1
)

echo Upgrading pip and installing Python packages...
python -m pip install --upgrade pip
if exist requirements.txt (
  pip install -r requirements.txt
) else (
  echo requirements.txt not found. Skipping pip install.
)

echo Installing Playwright browsers (Chromium)...
python -m playwright install chromium

echo.
echo Setup completed.
echo To run capture: call run.bat --run
echo Or: python main.py --launch-chrome

endlocal
pause
exit /b 0



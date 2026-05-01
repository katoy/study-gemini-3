@echo off
rem Kindle to PDF - Windows setup script
rem Requires uv: https://astral.sh/uv/
setlocal

rem Check uv availability
uv --version >nul 2>&1 || (
  echo uv not found. Install uv from https://astral.sh/uv/
  pause
  exit /b 1
)

echo --- Python dependencies ---
uv sync || (
  echo Failed to sync dependencies.
  pause
  exit /b 1
)

echo --- Playwright (Chromium) ---
uv run playwright install chromium || (
  echo Failed to install Playwright browsers.
  pause
  exit /b 1
)

echo.
echo Setup completed.
echo To run: run_win.bat --launch-chrome

endlocal
pause
exit /b 0

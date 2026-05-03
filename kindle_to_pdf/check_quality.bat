@echo off
REM Quality Check Script for Windows (Command Prompt)
REM Checks ruff, mypy, and test coverage (100%)

setlocal enabledelayedexpansion

echo 🔍 Starting quality checks...
echo.

REM ruff check
echo 📋 Running ruff...
call uv run ruff check .
if errorlevel 1 (
    echo ❌ ruff failed!
    exit /b 1
)
echo ✅ ruff passed!
echo.

REM mypy check
echo 📋 Running mypy...
call uv run mypy .
if errorlevel 1 (
    echo ❌ mypy failed!
    exit /b 1
)
echo ✅ mypy passed!
echo.

REM pytest with coverage
echo 📋 Running pytest with coverage...
call uv run pytest --cov=. --cov-report=term-missing --cov-fail-under=100
if errorlevel 1 (
    echo ❌ Tests or coverage failed!
    exit /b 1
)
echo ✅ All tests passed with 100%% coverage!
echo.

echo 🎉 All quality checks passed!

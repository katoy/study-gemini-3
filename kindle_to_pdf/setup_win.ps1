# Kindle to PDF — Windows PowerShell setup script (clean)
# Usage: powershell -ExecutionPolicy Bypass -File .\setup_win.ps1

param()
$ErrorActionPreference = 'Stop'
Write-Host "=== Kindle to PDF setup (Windows PowerShell) ==="

# Check python
try {
    & python --version > $null 2>&1
} catch {
    Write-Host "Python not found. Install Python 3.8+ and ensure 'python' is on PATH." -ForegroundColor Red
    exit 1
}

$venvPath = Join-Path $PSScriptRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

# Create venv if missing
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment (.venv)..."
    & python -m venv $venvPath
}

# Ensure venv python exists
if (-not (Test-Path $venvPython)) {
    Write-Host "Failed to create virtual environment or python not found in venv." -ForegroundColor Red
    exit 1
}

Write-Host "Upgrading pip and installing required packages..."
& $venvPython -m pip install --upgrade pip

$requirements = Join-Path $PSScriptRoot 'requirements.txt'
if (Test-Path $requirements) {
    & $venvPython -m pip install -r $requirements
} else {
    Write-Host "requirements.txt not found. Skipping pip install." -ForegroundColor Yellow
}

Write-Host "Installing Playwright browsers (Chromium)..."
& $venvPython -m playwright install chromium

Write-Host "=== Setup completed ===" -ForegroundColor Green
Write-Host "To run capture: .\run.bat --run" -ForegroundColor Cyan
Write-Host "Or: & '$venvPython' main.py --launch-chrome" -ForegroundColor Cyan
exit 0

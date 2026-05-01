# Kindle to PDF — Windows PowerShell setup script
# Usage: powershell -ExecutionPolicy Bypass -File .\setup_win.ps1

param()
$ErrorActionPreference = 'Stop'
Write-Host "=== Kindle to PDF setup (Windows PowerShell) ==="

# Check uv
try {
    & uv --version > $null 2>&1
} catch {
    Write-Host "'uv' not found. Please install uv: https://astral.sh/uv/" -ForegroundColor Red
    exit 1
}

Write-Host "--- Python dependencies ---"
& uv sync

Write-Host "--- Playwright (Chromium) ---"
& uv run playwright install chromium

Write-Host "=== Setup completed ===" -ForegroundColor Green
Write-Host "To run: .\run_win.bat --launch-chrome" -ForegroundColor Cyan
exit 0

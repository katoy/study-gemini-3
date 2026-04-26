# PowerShell runner for Kindle to PDF
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\run_win.ps1 --launch-chrome
# Accepts arbitrary arguments and forwards them to main.py

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = 'Stop'
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptRoot

Write-Host "=== run_win.ps1: Running Kindle to PDF (PowerShell) ==="

# Ensure system python available
try {
    & python --version > $null 2>&1
} catch {
    Write-Host "system 'python' not found. Please install Python 3.8+ and ensure 'python' is on PATH." -ForegroundColor Red
    exit 1
}

$venvPython = Join-Path $ScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment (.venv)..."
    & python -m venv .venv
    if (-not (Test-Path $venvPython)) {
        Write-Host "Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Using venv python: $venvPython"

# Upgrade pip quietly
& $venvPython -m pip install --upgrade pip | Out-Null

# Install required packages from requirements.txt if present, otherwise install defaults
$requirements = Join-Path $ScriptRoot 'requirements.txt'
if (Test-Path $requirements) {
    Write-Host "Installing packages from requirements.txt..."
    & $venvPython -m pip install -r $requirements
} else {
    Write-Host "requirements.txt not found. Installing essential packages (playwright, img2pdf)..."
    & $venvPython -m pip install playwright img2pdf
}

# Also ensure Playwright browsers are installed
Write-Host "Ensuring Playwright browsers (Chromium) are installed..."
& $venvPython -m playwright install chromium

# Forward args (use RemainingArgs when called via -File) or $args when executed directly
if ($RemainingArgs -and $RemainingArgs.Length -gt 0) {
    $forward = $RemainingArgs
} else {
    $forward = $args
}

# Build argument list to pass to Python
# Ensure unbuffered (-u) so interactive prompts appear immediately
$pyArgs = @('-u','main.py') + $forward

Write-Host "Running: $venvPython $($pyArgs -join ' ')"

# Run interactively so user can press Enter/q as main.py expects
$proc = Start-Process -FilePath $venvPython -ArgumentList $pyArgs -NoNewWindow -Wait -PassThru

exit $proc.ExitCode

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

# Ensure uv is available
try {
    & uv --version > $null 2>&1
} catch {
    Write-Host "'uv' not found. Please install uv: https://astral.sh/uv/" -ForegroundColor Red
    exit 1
}

# Ensure dependencies are synced
if (-not (Test-Path (Join-Path $ScriptRoot ".venv"))) {
    Write-Host "Virtual environment not found. Running setup..."
    & uv sync
    & uv run playwright install chromium
}

# Forward args
if ($RemainingArgs -and $RemainingArgs.Length -gt 0) {
    $forward = $RemainingArgs
} else {
    $forward = $args
}

# If no arguments given, default to --launch-chrome
if (-not $forward -or $forward.Length -eq 0) {
    $forward = @('--launch-chrome')
}

$pyArgs = @('run', 'python', '-u', 'main.py') + $forward

Write-Host "Running: uv $($pyArgs -join ' ')"

# Run interactively so user can press Enter/q as main.py expects
$proc = Start-Process -FilePath 'uv' -ArgumentList $pyArgs -NoNewWindow -Wait -PassThru

exit $proc.ExitCode

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

# Detect and optionally launch Chrome, and build argument list to pass to Python
# Ensure unbuffered (-u) so interactive prompts appear immediately
# If caller passed --launch-chrome, start Chrome here and remove that flag before forwarding
$launchChrome = $false
$forceKillChrome = $false
$argsList = $forward
if ($argsList -and ($argsList -contains '--launch-chrome')) {
    $launchChrome = $true
    $argsList = $argsList | Where-Object { $_ -ne '--launch-chrome' }
}
if ($argsList -and ($argsList -contains '--force-kill-chrome')) {
    $forceKillChrome = $true
    $argsList = $argsList | Where-Object { $_ -ne '--force-kill-chrome' }
}

if ($launchChrome) {
    Write-Host "Starting Chrome with remote debugging on port 9222..."
    $possible = @(
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
    )
    $chromePath = $possible | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $chromePath) {
        Write-Host "Chrome executable not found in standard locations." -ForegroundColor Yellow
    } else {
        $userData = Join-Path $env:TEMP "chrome-debug-profile"
        New-Item -ItemType Directory -Path $userData -Force | Out-Null
        $startArgs = @("--remote-debugging-port=9222","--user-data-dir=$userData","--no-first-run")
        Start-Process -FilePath $chromePath -ArgumentList $startArgs -NoNewWindow
        Start-Sleep -Seconds 1

        # Check whether port 9222 is listening
        $listening = $false
        try {
            $conn = Get-NetTCPConnection -LocalPort 9222 -ErrorAction Stop
            if ($conn) { $listening = $true }
        } catch {
            $listening = $false
        }

        if (-not $listening -and $forceKillChrome) {
            Write-Host "Port 9222 not available. Forcing existing Chrome processes to stop..."
            Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            Start-Process -FilePath $chromePath -ArgumentList $startArgs -NoNewWindow
            Start-Sleep -Seconds 1
            try { $conn = Get-NetTCPConnection -LocalPort 9222 -ErrorAction Stop; if ($conn) { $listening = $true } } catch {}
        }

        if ($listening) {
            Write-Host "Chrome started and listening on 9222 (user-data: $userData)"
        } else {
            Write-Host "Chrome started but 9222 not listening. Close other Chrome instances and retry, or re-run with --force-kill-chrome to force stop." -ForegroundColor Yellow
        }
    }
}

$pyArgs = @('-u','main.py') + $argsList

Write-Host "Running: $venvPython $($pyArgs -join ' ')"

# Run interactively so user can press Enter/q as main.py expects
$proc = Start-Process -FilePath $venvPython -ArgumentList $pyArgs -NoNewWindow -Wait -PassThru

exit $proc.ExitCode

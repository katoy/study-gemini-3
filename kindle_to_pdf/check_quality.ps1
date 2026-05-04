# Quality Check Script for Windows (PowerShell)
# Checks ruff, mypy, and test coverage (100%)

$ErrorActionPreference = "Stop"

Write-Host "🔍 Starting quality checks..." -ForegroundColor Cyan
Write-Host ""

# ruff check
Write-Host "📋 Running ruff..." -ForegroundColor Yellow
uv run ruff check .
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ ruff failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ ruff passed!" -ForegroundColor Green
Write-Host ""

# mypy check
Write-Host "📋 Running mypy..." -ForegroundColor Yellow
uv run mypy .
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ mypy failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ mypy passed!" -ForegroundColor Green
Write-Host ""

# pytest with coverage
Write-Host "📋 Running pytest with coverage..." -ForegroundColor Yellow
uv run pytest --cov=. --cov-report=term-missing --cov-fail-under=100
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Tests or coverage failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ All tests passed with 100% coverage!" -ForegroundColor Green
Write-Host ""

Write-Host "🎉 All quality checks passed!" -ForegroundColor Green

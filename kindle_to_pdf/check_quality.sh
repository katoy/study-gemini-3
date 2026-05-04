#!/bin/bash

# Quality Check Script for macOS/Linux
# Checks ruff, mypy, and test coverage (100%)

set -e

echo "🔍 Starting quality checks..."
echo ""

# ruff check
echo "📋 Running ruff..."
uv run ruff check .
echo "✅ ruff passed!"
echo ""

# mypy check
echo "📋 Running mypy..."
uv run mypy .
echo "✅ mypy passed!"
echo ""

# pytest with coverage
echo "📋 Running pytest with coverage..."
uv run pytest --cov=. --cov-report=term-missing --cov-fail-under=100
echo "✅ All tests passed with 100% coverage!"
echo ""

echo "🎉 All quality checks passed!"

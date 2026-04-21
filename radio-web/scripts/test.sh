#!/usr/bin/env bash
# テスト実行・カバレッジ計測スクリプト
# 使い方:
#   bash scripts/test.sh           # 通常実行
#   bash scripts/test.sh --html    # HTML レポートも生成
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

HTML_FLAG=""
for arg in "$@"; do
  if [[ "$arg" == "--html" ]]; then
    HTML_FLAG="--cov-report=html:htmlcov"
  fi
done

echo "=== テスト実行 ==="
uv run pytest --no-header $HTML_FLAG

if [[ -n "$HTML_FLAG" ]]; then
  echo ""
  echo "HTMLレポート: htmlcov/index.html"
fi

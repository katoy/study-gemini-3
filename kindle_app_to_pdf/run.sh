#!/bin/bash

# Kindle App to PDF - Run script (macOS/Linux)
# uv を使用して実行します

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# uv の確認
if ! command -v uv &> /dev/null; then
    echo "[ERROR] uv がインストールされていません。"
    echo "        brew install uv でインストールしてください。"
    echo "        または https://github.com/astral-sh/uv を参照してください。"
    exit 1
fi

echo "=== Kindle App to PDF (macOS/Linux) ==="
echo ""

# 仮想環境がない場合は作成
if [ ! -d ".venv" ]; then
    echo "仮想環境を作成中..."
    uv venv
    echo ""
fi

# 実行
echo "Kindle アプリで本を開き、最初のページを表示した状態で Enter を押してください。"
echo ""

uv run python main.py "$@"

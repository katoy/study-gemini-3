#!/bin/bash

# Kindle App to PDF セットアップスクリプト (macOS)

set -e

echo "=== Kindle App to PDF セットアップを開始します ==="
echo ""

# Python バージョン確認
python_version=$(python3 --version 2>&1)
echo "✓ $python_version"

# uv の確認
if command -v uv &> /dev/null; then
    uv_version=$(uv --version)
    echo "✓ $uv_version"
    echo ""
    echo "[推奨] uv を使用してセットアップします（高速です）"
    echo "仮想環境を作成中..."
    uv venv

    echo "仮想環境を有効化中..."
    source .venv/bin/activate

    echo "依存パッケージをインストール中..."
    uv pip install -r requirements.txt
else
    echo "ℹ uv がインストールされていません。"
    echo "  (高速なセットアップをしたい場合は brew install uv でインストールしてください)"
    echo ""
    echo "pip を使用してセットアップします..."

    echo "仮想環境を作成中..."
    python3 -m venv .venv

    echo "仮想環境を有効化中..."
    source .venv/bin/activate

    echo "依存パッケージをインストール中..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt
fi

echo ""
echo "=== セットアップが完了しました！ ==="
echo ""
echo "[使い方]"
echo "  1. Kindle アプリで本を開き、最初のページを表示してください。"
echo "  2. 以下を実行してください:"
echo ""
echo "     python main.py"
echo ""
echo "     または uv で実行:"
echo "     uv run python main.py"
echo ""
echo "[オプション]"
echo "  --direction {right|left|space}  : ページめくり方向（デフォルト: space）"
echo "  --page-delay SECONDS            : ページ送り後の待機時間（デフォルト: 1.5）"
echo ""
echo "[注意事項]"
echo "  - 実行中は Kindle アプリを操作しないでください。"
echo "  - アクセシビリティの権限が必要です（初回実行時にポップアップが出ます）。"

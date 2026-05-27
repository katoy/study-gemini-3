#!/bin/bash

# NHK ラジオダウンローダーを起動するスクリプト

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 依存関係をインストール（初回実行時など）
if [ "$1" = "--install" ] || [ "$1" = "-i" ]; then
    echo "依存関係をインストール中..."
    uv sync
    shift
fi

# 依存関係がインストールされているか確認
if [ ! -d ".venv" ]; then
    echo "依存関係をインストール中..."
    uv sync
fi

# 仮想環境を有効化
source .venv/bin/activate

# GUI モードで起動（デフォルト）
# URL を指定した場合はダウンロードモード、省略時は GUI
if [ $# -eq 0 ]; then
    echo "GUI モードで起動..."
    nhk-radio
else
    nhk-radio "$@"
fi

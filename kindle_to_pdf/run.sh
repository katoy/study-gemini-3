#!/bin/bash

# Kindle to PDF 起動スクリプト (macOS)

# スクリプトのディレクトリに移動
cd "$(dirname "$0")"

# uv がインストールされているか確認
if ! command -v uv &> /dev/null; then
    echo "エラー: 'uv' が見つかりません。先に setup.sh を実行するか、uv をインストールしてください。"
    echo "インストール方法: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 仮想環境が構築されているか確認 (簡易チェック)
if [ ! -d ".venv" ]; then
    echo "警告: .venv が見つかりません。セットアップを開始します..."
    ./setup.sh
fi

echo "=== Kindle to PDF を起動します ==="

# 引数がない場合はデフォルトで --launch-chrome を付けて実行
if [ $# -eq 0 ]; then
    echo "実行コマンド: uv run python main.py --launch-chrome"
    uv run python main.py --launch-chrome
else
    echo "実行コマンド: uv run python main.py $@"
    uv run python main.py "$@"
fi

#!/bin/bash

# Kindle to PDF セットアップスクリプト (macOS)

set -e

echo "=== Kindle to PDF セットアップを開始します ==="

# 1. Python 依存関係のインストール
echo "--- Python ライブラリをインストール中 ---"
uv sync

# 2. Playwright のブラウザをインストール
echo "--- Playwright (Chromium) をインストール中 ---"
uv run playwright install chromium

echo "=== セットアップが完了しました！ ==="
echo "使い方: uv run python main.py --launch-chrome"

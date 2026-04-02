#!/bin/bash

# Kindle to PDF セットアップスクリプト (macOS)

set -e

echo "=== Kindle to PDF セットアップを開始します ==="

# 1. Python 依存関係のインストール
echo "--- Python ライブラリをインストール中 ---"
pip install -r requirements.txt

# 2. Playwright のブラウザをインストール
echo "--- Playwright (Chromium) をインストール中 ---"
playwright install chromium

echo "=== セットアップが完了しました！ ==="
echo "使い方: python main.py --launch-chrome"

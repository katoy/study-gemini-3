#!/bin/bash

# Kindle App to PDF セットアップスクリプト (macOS)

set -e

echo "=== Kindle App to PDF セットアップを開始します ==="

# 1. Python 依存関係のインストール
echo "--- Python ライブラリをインストール中 ---"
pip install -r requirements.txt

echo "=== セットアップが完了しました！ ==="
echo "使い方: python main.py"

#!/bin/bash

# PDF Splitter & OCR Chapter Pipeline 実行スクリプト
# uv を使用して依存関係を自動解決して実行します

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# uv の確認
if ! command -v uv &> /dev/null; then
    echo "エラー: 'uv' が見つかりません。"
    echo "インストール方法: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 引数がない場合は使い方を表示
if [ $# -eq 0 ]; then
    echo "=== PDF Splitter & OCR Chapter Pipeline ==="
    echo ""
    echo "使い方:"
    echo "  ./run.sh <対象PDFファイルのパス> [オプション]"
    echo ""
    echo "主なオプション:"
    echo "  --chapters-json <パス>          手動指定の章情報JSONファイルを指定"
    echo "  --ocr-engine {ndlocr,tesseract} OCRエンジンを指定 (既定: ndlocr)"
    echo "  --max-size-mb <数値>            最大ファイルサイズ (MB) (既定: 20)"
    echo "  --force-ocr                     既存のOCR済みファイルを無視して再実行"
    echo ""
    if [ -f "data/Kindle_14.pdf" ]; then
        echo "例 (サンプルデータで実行):"
        echo "  ./run.sh data/Kindle_14.pdf"
        if [ -f "data/chapters.json" ]; then
            echo "  ./run.sh data/Kindle_14.pdf --chapters-json data/chapters.json"
        fi
        echo ""
    fi
    echo "詳細ヘルプ表示:"
    echo "  ./run.sh -h"
    exit 0
fi

# -h または --help の場合は直接ヘルプを表示
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    uv run scripts/pdf_chapter_pipeline.py -h
    exit 0
fi

echo "実行コマンド: uv run scripts/pdf_chapter_pipeline.py $@"
uv run scripts/pdf_chapter_pipeline.py "$@"

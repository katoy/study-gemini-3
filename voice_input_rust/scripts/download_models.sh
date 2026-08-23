#!/usr/bin/env bash
# Script to download ggml Whisper models for voice_input_rust

# スクリプトのディレクトリからプロジェクトルートに移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="${PROJECT_ROOT}/models"
mkdir -p "$MODELS_DIR"

BASE_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

echo "=== Whisper ggml モデルダウンロードスクリプト ==="
echo "ダウンロードしたいモデルを選択してください:"
echo "1) tiny     (~75 MB)   - 最速・低精度"
echo "2) base     (~142 MB)  - 軽量・標準"
echo "3) small    (~466 MB)  - 推奨・高精度"
echo "4) medium   (~1.5 GB)  - 超高精度"
echo "5) large-v3 (~3.1 GB)  - 最高精度"
echo "6) すべてダウンロード"
read -p "選択 (1-6): " choice

download_model() {
    local name=$1
    local file="ggml-${name}.bin"
    echo "Downloading ${file}..."
    curl -L "${BASE_URL}/${file}" -o "${MODELS_DIR}/${file}"
    echo "完了: ${MODELS_DIR}/${file}"
}

case $choice in
    1) download_model "tiny" ;;
    2) download_model "base" ;;
    3) download_model "small" ;;
    4) download_model "medium" ;;
    5) download_model "large-v3" ;;
    6)
        download_model "tiny"
        download_model "base"
        download_model "small"
        download_model "medium"
        download_model "large-v3"
        ;;
    *)
        echo "無効な選択肢です。"
        exit 1
        ;;
esac


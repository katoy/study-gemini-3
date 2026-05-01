#!/bin/sh
# run.sh - Docker コンテナをビルドして実行するスクリプト

set -e

# イメージ名
IMAGE_NAME="hello-world"

# イメージのビルド
echo "==> Building Docker image: $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

# コンテナの実行（引数をそのまま渡す）
echo "==> Running container..."
docker run --rm "$IMAGE_NAME" "$@"

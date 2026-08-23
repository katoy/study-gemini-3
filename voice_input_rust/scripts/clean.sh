#!/bin/bash
set -e

# スクリプトのディレクトリからプロジェクトルートに移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🧹 ビルド中間生成物・キャッシュのクリーンアップを開始します..."

cd "$PROJECT_ROOT"

# cargo clean の実行 (Rust ビルド生成物の削除)
if command -v cargo >/dev/null 2>&1; then
    echo "  - cargo clean を実行中..."
    cargo clean 2>/dev/null || true
fi

# swift package clean の実行 (存在する場合)
if command -v swift >/dev/null 2>&1; then
    echo "  - swift package clean を実行中..."
    swift package clean 2>/dev/null || true
fi

# Swift Package Manager のビルドディレクトリ削除
if [ -d ".build" ]; then
    echo "  - .build/ を削除中..."
    rm -rf .build
fi

if [ -d ".swiftpm" ]; then
    echo "  - .swiftpm/ を削除中..."
    rm -rf .swiftpm
fi

# システム一時ファイル・ログ・プロファイル/カバレッジデータの削除
echo "  - 一時ファイル・プロファイルデータのクリーンアップ中..."
find . -type f \( -name ".DS_Store" -o -name "*~" -o -name "*.swp" -o -name "*.log" -o -name "*.profraw" -o -name "*.profdata" \) -delete 2>/dev/null || true

echo "✨ クリーンアップが完了しました。"


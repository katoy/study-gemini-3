#!/bin/bash

# Sketch アプリ全体のサーバー管理スクリプト
# backend（Express）と frontend（Vite）を同時に管理します
# 使用法: ./scripts/dev-all.sh {start|stop|restart|status}

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKEND_SCRIPT="$SCRIPT_DIR/server-control.sh"
FRONTEND_SCRIPT="$SCRIPT_DIR/frontend-control.sh"

for script in "$BACKEND_SCRIPT" "$FRONTEND_SCRIPT"; do
  if [ ! -x "$script" ]; then
    chmod +x "$script"
    echo "✅ $script を実行可能にしました"
  fi
done

start_all() {
  echo "🚀 全サーバーを起動します..."
  echo ""

  echo "📌 ステップ1: バックエンドサーバーを起動"
  "$BACKEND_SCRIPT" start || {
    echo "❌ バックエンドサーバーの起動に失敗しました"
    return 1
  }
  echo ""

  sleep 2

  echo "📌 ステップ2: フロントエンドサーバーを起動"
  "$FRONTEND_SCRIPT" start || {
    echo "❌ フロントエンドサーバーの起動に失敗しました"
    "$BACKEND_SCRIPT" stop || true
    return 1
  }
  echo ""

  echo "✅ 全サーバーが起動しました"
  echo ""
  echo "📊 アクセス情報:"
  echo "  • フロントエンド: http://localhost:3010"
  echo "  • バックエンド API: http://localhost:3011"
  echo "  • WebSocket: ws://localhost:3011/api/ws"
  echo "  • Sketch MCP Status: http://localhost:3011/api/sketch-mcp/status"
  echo ""
  echo "📝 ログファイル:"
  echo "  • バックエンド: $PROJECT_ROOT/logs/backend.log"
  echo "  • フロントエンド: $PROJECT_ROOT/logs/frontend.log"
}

stop_all() {
  echo "🛑 全サーバーを停止します..."
  echo ""

  echo "📌 ステップ1: フロントエンドサーバーを停止"
  "$FRONTEND_SCRIPT" stop || true
  echo ""

  sleep 1

  echo "📌 ステップ2: バックエンドサーバーを停止"
  "$BACKEND_SCRIPT" stop || true
  echo ""

  echo "✅ 全サーバーを停止しました"
}

restart_all() {
  echo "🔄 全サーバーを再起動します..."
  stop_all
  sleep 2
  start_all
}

status_all() {
  echo "📊 サーバー状態："
  echo ""

  echo "📌 バックエンドサーバー:"
  "$BACKEND_SCRIPT" status || true
  echo ""

  echo "📌 フロントエンドサーバー:"
  "$FRONTEND_SCRIPT" status || true
}

case "${1:-status}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    restart_all
    ;;
  status)
    status_all
    ;;
  *)
    echo "使用法: $0 {start|stop|restart|status}"
    echo ""
    echo "コマンド:"
    echo "  start   - 全サーバー（バックエンド + フロントエンド）をバックグラウンドで起動"
    echo "  stop    - 全サーバーを停止"
    echo "  restart - 全サーバーを再起動"
    echo "  status  - 全サーバーの状態を確認"
    echo ""
    echo "個別管理:"
    echo "  ./scripts/server-control.sh {start|stop|restart|status}   # バックエンドのみ"
    echo "  ./scripts/frontend-control.sh {start|stop|restart|status} # フロントエンドのみ"
    exit 1
    ;;
esac

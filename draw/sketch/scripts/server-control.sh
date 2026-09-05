#!/bin/bash

# Sketch アプリのバックエンド（Express/WebSocket）サーバー管理スクリプト
# 使用法: ./scripts/server-control.sh {start|stop|restart|status}

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$PROJECT_ROOT/.backend.pid"
LOG_FILE="$PROJECT_ROOT/logs/backend.log"

# ログディレクトリを確認
mkdir -p "$PROJECT_ROOT/logs"

# 環境変数を設定
export GEMINI_API_KEY="${GEMINI_API_KEY:-}"
export NODE_ENV="${NODE_ENV:-development}"
export PORT="${PORT:-3011}"

start_server() {
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "❌ バックエンドサーバーは既に起動しています (PID: $pid)"
      return 1
    fi
  fi

  echo "🚀 バックエンドサーバーを起動します（ポート $PORT）..."

  if [ -z "$GEMINI_API_KEY" ]; then
    echo "⚠️  警告: GEMINI_API_KEY が設定されていません"
  fi

  cd "$PROJECT_ROOT"
  nohup npm run dev:server > "$LOG_FILE" 2>&1 &
  local pid=$!

  echo "$pid" > "$PID_FILE"
  echo "✅ バックエンドサーバーが起動しました (PID: $pid)"
  echo "📝 ログ: $LOG_FILE"

  # 起動確認
  sleep 2
  if kill -0 "$pid" 2>/dev/null; then
    echo "✅ プロセスは正常に実行中です"
  else
    echo "❌ プロセスが起動に失敗しました。ログを確認してください:"
    tail -20 "$LOG_FILE"
    return 1
  fi
}

stop_server() {
  if [ ! -f "$PID_FILE" ]; then
    echo "❌ バックエンドサーバーは起動していません"
    return 1
  fi

  local pid=$(cat "$PID_FILE")

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "❌ プロセス $pid は実行中ではありません"
    rm -f "$PID_FILE"
    return 1
  fi

  echo "🛑 バックエンドサーバーを停止します (PID: $pid)..."
  kill "$pid" 2>/dev/null || true

  for i in {1..30}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "⚠️  強制終了します..."
    kill -9 "$pid" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  echo "✅ バックエンドサーバーを停止しました"
}

restart_server() {
  echo "🔄 バックエンドサーバーを再起動します..."
  stop_server || true
  sleep 1
  start_server
}

status_server() {
  if [ ! -f "$PID_FILE" ]; then
    echo "❌ バックエンドサーバーは起動していません"
    return 1
  fi

  local pid=$(cat "$PID_FILE")

  if kill -0 "$pid" 2>/dev/null; then
    echo "✅ バックエンドサーバーは起動中です (PID: $pid, ポート: $PORT)"
    echo "📝 ログファイル: $LOG_FILE"
    return 0
  else
    echo "❌ プロセス $pid は実行中ではありません"
    rm -f "$PID_FILE"
    return 1
  fi
}

case "${1:-status}" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  restart)
    restart_server
    ;;
  status)
    status_server
    ;;
  *)
    echo "使用法: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac

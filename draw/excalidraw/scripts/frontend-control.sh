#!/bin/bash

# Draw アプリのフロントエンド（Vite）サーバー管理スクリプト
# 使用法: ./scripts/frontend-control.sh {start|stop|restart|status}

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$PROJECT_ROOT/.frontend.pid"
LOG_FILE="$PROJECT_ROOT/logs/frontend.log"

# ログディレクトリを確認
mkdir -p "$PROJECT_ROOT/logs"

# 環境変数を設定
export NODE_ENV="${NODE_ENV:-development}"
export VITE_PORT="${VITE_PORT:-3000}"

start_frontend() {
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "❌ フロントエンドサーバーは既に起動しています (PID: $pid)"
      return 1
    fi
  fi

  echo "🚀 フロントエンドサーバーを起動します（ポート $VITE_PORT）..."

  cd "$PROJECT_ROOT"
  nohup npm run dev:vite > "$LOG_FILE" 2>&1 &
  local pid=$!

  echo "$pid" > "$PID_FILE"
  echo "✅ フロントエンドサーバーが起動しました (PID: $pid)"
  echo "📝 ログ: $LOG_FILE"

  # 起動確認
  sleep 3
  if kill -0 "$pid" 2>/dev/null; then
    echo "✅ プロセスは正常に実行中です"
  else
    echo "❌ プロセスが起動に失敗しました。ログを確認してください:"
    tail -20 "$LOG_FILE"
    return 1
  fi
}

stop_frontend() {
  if [ ! -f "$PID_FILE" ]; then
    echo "❌ フロントエンドサーバーは起動していません"
    return 1
  fi

  local pid=$(cat "$PID_FILE")

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "❌ プロセス $pid は実行中ではありません"
    rm -f "$PID_FILE"
    return 1
  fi

  echo "🛑 フロントエンドサーバーを停止します (PID: $pid)..."
  kill "$pid" 2>/dev/null || true

  # 終了を待つ
  for i in {1..30}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done

  # まだ実行中なら強制終了
  if kill -0 "$pid" 2>/dev/null; then
    echo "⚠️  強制終了します..."
    kill -9 "$pid" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  echo "✅ フロントエンドサーバーを停止しました"
}

restart_frontend() {
  echo "🔄 フロントエンドサーバーを再起動します..."
  stop_frontend || true
  sleep 1
  start_frontend
}

status_frontend() {
  if [ ! -f "$PID_FILE" ]; then
    echo "❌ フロントエンドサーバーは起動していません"
    return 1
  fi

  local pid=$(cat "$PID_FILE")

  if kill -0 "$pid" 2>/dev/null; then
    echo "✅ フロントエンドサーバーは起動中です (PID: $pid, ポート: $VITE_PORT)"
    echo "📝 ログファイル: $LOG_FILE"
    return 0
  else
    echo "❌ プロセス $pid は実行中ではありません"
    rm -f "$PID_FILE"
    return 1
  fi
}

# 使用法
case "${1:-status}" in
  start)
    start_frontend
    ;;
  stop)
    stop_frontend
    ;;
  restart)
    restart_frontend
    ;;
  status)
    status_frontend
    ;;
  *)
    echo "使用法: $0 {start|stop|restart|status}"
    echo ""
    echo "コマンド:"
    echo "  start   - フロントエンドサーバーをバックグラウンドで起動"
    echo "  stop    - フロントエンドサーバーを停止"
    echo "  restart - フロントエンドサーバーを再起動"
    echo "  status  - フロントエンドサーバーの状態を確認"
    exit 1
    ;;
esac

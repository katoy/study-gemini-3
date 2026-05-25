#!/bin/bash
# NHK ラジオ Web アプリケーション起動スクリプト

# 既存プロセスの停止
echo "既存プロセスを確認中..."
existing_pids=$(lsof -t -i :8000 2>/dev/null)
if [ -n "$existing_pids" ]; then
    echo "ポート 8000 を使用中のプロセスを停止します..."
    echo "$existing_pids" | while read pid; do
        if [ -n "$pid" ]; then
            echo "  PID $pid を kill 中..."
            kill -9 "$pid" 2>/dev/null
        fi
    done
    sleep 1
    echo "プロセス停止完了"
else
    echo "ポート 8000 は利用可能です"
fi

# サーバー起動
echo ""
echo "サーバーを起動中..."
uv run uvicorn app.main:app --reload

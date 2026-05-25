#!/bin/bash
# NHK ラジオ Web アプリケーション起動スクリプト

# 既存プロセスの停止
echo "既存プロセスを確認中..."
existing_pid=$(lsof -t -i :8000 2>/dev/null)
if [ -n "$existing_pid" ]; then
    echo "ポート 8000 を使用中のプロセス ($existing_pid) を停止します..."
    kill "$existing_pid" 2>/dev/null
    sleep 1
    echo "プロセス停止完了"
else
    echo "ポート 8000 は利用可能です"
fi

# サーバー起動
echo ""
echo "サーバーを起動中..."
uv run uvicorn app.main:app --reload

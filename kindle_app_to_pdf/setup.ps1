# PowerShell setup script for Windows - Kindle App to PDF
Write-Host "=== Kindle App to PDF - Windows セットアップ ===" -ForegroundColor Cyan
Write-Host ""

# Python バージョン確認
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python が見つかりません。https://www.python.org/ からインストールしてください。" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python: $pythonVersion"

# uv の確認
$uvAvailable = $false
$uvVersion = uv --version 2>$null
if ($LASTEXITCODE -eq 0) {
    $uvAvailable = $true
    Write-Host "✓ uv: $uvVersion"
    Write-Host ""
    Write-Host "[推奨] uv を使用してセットアップします（高速です）" -ForegroundColor Yellow

    # uv で仮想環境作成とインストール
    Write-Host "仮想環境を作成中..."
    uv venv

    Write-Host "仮想環境を有効化中..."
    & ".venv\Scripts\Activate.ps1"

    Write-Host "依存パッケージをインストール中..."
    uv pip install -r requirements.txt
} else {
    Write-Host "ℹ uv がインストールされていません。" -ForegroundColor Yellow
    Write-Host "  (高速なセットアップをしたい場合は https://github.com/astral-sh/uv をインストールしてください)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "pip を使用してセットアップします..." -ForegroundColor Yellow

    # pip で仮想環境作成とインストール
    if (-not (Test-Path ".venv")) {
        Write-Host "仮想環境を作成中..."
        python -m venv .venv
    }

    Write-Host "仮想環境を有効化中..."
    & ".venv\Scripts\Activate.ps1"

    Write-Host "依存パッケージをインストール中..."
    python -m pip install --upgrade pip --quiet
    pip install -r requirements.txt
}

Write-Host ""
Write-Host "=== セットアップ完了 ===" -ForegroundColor Green
Write-Host ""
Write-Host "[使い方]"
Write-Host "  1. Kindle for PC を起動し、読みたい本の最初のページを表示してください。"
Write-Host "  2. Kindle ウィンドウを最前面に表示した状態で、以下を実行してください:"
Write-Host ""
Write-Host "     python main.py"
Write-Host ""
Write-Host "     または uv で実行:"
Write-Host "     uv run python main.py"
Write-Host ""
Write-Host "[オプション]"
Write-Host "  --direction {right|left|space}  : ページめくり方向（デフォルト: space）"
Write-Host "  --page-delay SECONDS            : ページ送り後の待機時間（デフォルト: 1.5）"
Write-Host ""
Write-Host "[注意事項]"
Write-Host "  - 実行中は Kindle ウィンドウを操作しないでください。"
Write-Host "  - 高 DPI (スケーリング) 環境では、Windows の表示スケールを 100% に設定してください。"
Write-Host "  - 再実行時は '.venv\Scripts\Activate.ps1' で仮想環境を有効化してください。"

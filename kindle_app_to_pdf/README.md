# Kindle App to PDF

Kindle デスクトップアプリの書籍を、高品質な PNG 画像としてキャプチャし、劣化のない PDF を自動生成するツールです。

**対応 OS**: macOS（AppleScript 使用）、Windows（pygetwindow + PIL 使用）

## ⚠️ 重要：注意事項 (Disclaimer)

- **著作権について**: 本ツールは、個人での利用、または著作権法で認められている範囲内（私的使用のための複製など）での使用を目的としています。生成された PDF を他人に配布したり、インターネット上にアップロードしたりすることは、著作権法に抵触する恐れがあります。利用者は自己責任において使用してください。
- **OS別注意事項**: 
  - **macOS**: `osascript` (AppleScript) と `screencapture` に依存します。アクセシビリティ許可が必要です。
  - **Windows**: `pygetwindow` と `PIL.ImageGrab` を使用します。高 DPI 環境では表示スケール 100% を推奨します。
- **ハードウェア要件**: Retina ディスプレイなど高解像度環境では、生成される PDF ファイルが巨大になる場合があります。必要に応じて `split_pdf.py` で分割してください。

## 特徴

- **高画質・ロスレス**: `img2pdf` を使用し、再エンコードなしで PNG の品質を維持したまま PDF 化します。
- **マルチプラットフォーム**: macOS と Windows に対応しています。
- **UI干渉の最小化**: ウィンドウ領域を自動検出し、Kindle アプリのみをキャプチャします。
- **高度な終端検知**: 画像の重複を検知し、本の終わりに達すると自動停止します。
- **柔軟なページ送り**: デフォルトでスペースキーによるページ送りに対応しているほか、矢印キーも利用可能です。

## 動作環境

### macOS
- **OS**: macOS 12 (Monterey) 以降推奨 (Intel / Apple Silicon 両対応)
- **Python**: 3.11 以上
- **必須アプリ**: Kindle デスクトップアプリ (App Store 版または Amazon 公式サイト版)
- **依存コマンド**: `osascript`, `screencapture` (macOS 標準搭載)

### Windows
- **OS**: Windows 10 / 11
- **Python**: 3.11 以上
- **必須アプリ**: Kindle for PC（Microsoft Store または Amazon 公式サイト版）
- **表示設定**: 推奨スケール 100%（高 DPI 環境では調整が必要な場合があります）

## セットアップ

### 1. リポジトリの準備
本リポジトリをダウンロードまたはクローンします。

### 2. Python 依存ライブラリのインストール

#### **macOS**

**最も簡単: セットアップスクリプトを使う（推奨）**
```bash
bash setup.sh
```

**uv を使う場合 (高速です)**
```bash
# uv がインストールされていない場合は先にインストール
# brew install uv

uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

**pip を使う場合**
```bash
pip install -r requirements.txt
```

#### **Windows**

**最も簡単: セットアップスクリプトを使う（推奨）**
```powershell
setup.bat
```

**uv を使う場合 (高速です)**
```powershell
# uv がインストールされていない場合は先にインストール
# winget install astral-sh.uv  または https://github.com/astral-sh/uv から

uv venv
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

**PowerShell スクリプトを使う場合**
```powershell
.\setup.ps1
```

**pip を使う場合**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. OS別の権限設定

#### macOS
1. システム設定 > プライバシーとセキュリティ > **アクセシビリティ** を開きます。
2. 使用しているターミナルアプリ（「ターミナル」、「iTerm2」、「Visual Studio Code」など）のスイッチを **オン** にします。
3. 同様に、**「画面収録」** の権限も確認してください。

#### Windows
- 特別な権限設定は不要ですが、Windows の表示スケールが 100% であることを確認してください。
- 高 DPI 環境では、設定 > ディスプレイ > スケール から調整してください。

## 使い方

Kindle アプリで本を開き、**最初のページ（またはキャプチャを開始したいページ）** を表示した状態で実行してください。

### 最も簡単な方法

**macOS/Linux:**
```bash
./run.sh
```

**Windows:**
```powershell
run.bat
```

### コマンドラインでの実行

```bash
# 標準的な実行（デフォルトでスペースキーによる送り）
python main.py

# または uv で実行
uv run python main.py

# 矢印キーを使いたい場合
python main.py --direction right
python main.py --direction left

# ページ送りが遅い書籍の場合
python main.py --page-delay 2.0

# 出力先を指定する場合
python main.py --output /path/to/output
```

### オプション

- `--direction {right,left,space}`: ページめくりの方向（デフォルト: `space`）
- `--page-delay SECONDS`: ページ送り後の待機秒数（デフォルト: `1.5`）
- `--output DIR`: PDF の保存先ディレクトリ（デフォルト: `output`）

## トラブルシューティング

### macOS

**1. ページ送りがされない / 権限エラー**
- ターミナル、VSCode、iTerm 等に **「アクセシビリティ」の権限** が付与されているか確認してください。

**2. PDF の最後に評価画面やシークバーが入る**
- `--page-delay` を少し長めに設定してください。例：`python main.py --page-delay 2.0`

### Windows

**1. キャプチャ座標がずれている**
- Windows の表示スケールを確認してください。**設定 > ディスプレイ > スケール と レイアウト** で 100% に設定してください。
- 必要に応じて、Kindle for PC のウィンドウサイズを調整してください。

**2. スキャンが終了しない**
- Kindle ウィンドウが最前面にあり、フォーカスされていることを確認してください。
- 最後のページに到達してからしばらく待つと、自動的に終了します。

### 共通

**3. PDF が生成されない**
- `output` ディレクトリの権限を確認してください。
- ディスク容量が十分にあるか確認してください。

## ファイル構成

```text
kindle_app_to_pdf/
├── main.py              # メイン・エントリポイント（Mac/Windows 両対応）
├── kindle_capture.py    # Kindle 操作・キャプチャロジック（OS別に自動分岐）
├── pdf_maker.py         # img2pdf を使用した PNG からロスレス PDF への変換処理
├── split_pdf.py         # (ツール) 巨大な PDF を分割するスクリプト
│
├── # セットアップスクリプト
├── setup.sh             # (macOS/Linux) セットアップスクリプト
├── setup.bat            # (Windows) セットアップスクリプト (batch版)
├── setup.ps1            # (Windows) セットアップスクリプト (PowerShell版)
│
├── # 実行スクリプト
├── run.sh               # (macOS/Linux) uv で実行するスクリプト
├── run.bat              # (Windows) uv で実行するスクリプト
│
├── # 設定ファイル
├── requirements.txt     # 依存 Python ライブラリの一覧（pip/uv用）
├── pyproject.toml       # Python プロジェクト設定（uv/pip-tools用）
├── README.md            # 本ドキュメント
│
└── output/              # デフォルトの保存先（書籍ごとの PNG 群と PDF）
```

### 各ファイルの役割

- **main.py**: ユーザーインターフェースとしての CLI を提供し、`kindle_capture` と `pdf_maker` を連携させます。
- **kindle_capture.py**: OS に応じて最適な方法で Kindle をキャプチャします。
  - **macOS**: `osascript` (AppleScript) を使用
  - **Windows**: `pygetwindow` と `PIL.ImageGrab` を使用
- **pdf_maker.py**: キャプチャされた PNG を `img2pdf` に渡し、品質を落とさずに PDF を生成します。
- **split_pdf.py**: 大きな PDF を扱いやすいサイズに分割するツールです。

## ライセンス

MIT

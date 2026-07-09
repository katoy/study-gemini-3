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
- **インタラクティブな連続処理**: 1 冊の処理が終わると、そのまま次の本を処理するか確認するため、複数の書籍を効率的に PDF 化できます。
- **柔軟なページ送り**: デフォルトで右矢印キーによるページ送りに対応しているほか、スペースキーや左矢印キーも利用可能です。

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
エクスプローラー上で `setup.bat` をダブルクリックするか、コマンドプロンプトで以下を実行します。
```cmd
setup.bat
```
※ PowerShell から実行する場合は、実行ポリシーによるブロックを回避するため以下を実行してください。
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

**uv を使う場合 (高速です)**
```cmd
# uv がインストールされていない場合は先にインストール
# winget install astral-sh.uv  または https://github.com/astral-sh/uv から

uv venv
# コマンドプロンプトの場合:
.venv\Scripts\activate.bat
# PowerShell の場合:
.venv\Scripts\Activate.ps1

uv pip install -r requirements.txt
```

**pip を使う場合**
```cmd
python -m venv .venv
# コマンドプロンプトの場合:
.venv\Scripts\activate.bat
# PowerShell の場合:
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
本プログラムはインタラクティブに動作し、1 冊終わるごとに次の本を処理するか確認します。

### 最も簡単な方法

**macOS/Linux:**
```bash
./run.sh
```

**Windows:**
エクスプローラー上で `run.bat` をダブルクリックして起動するか、コマンドラインで以下を実行します。
* コマンドプロンプトの場合:
  ```cmd
  run.bat
  ```
* PowerShell の場合:
  ```powershell
  .\run.bat
  ```
※ コマンドライン引数（オプション）を渡したい場合は、以下のように実行できます。
  ```cmd
  run.bat --direction space
  ```

### コマンドラインでの実行

```bash
# 標準的な実行（デフォルトで右矢印キーによる送り）
python main.py

# または uv で実行
uv run python main.py

# 矢印キーを使いたい場合
python main.py --direction right
python main.py --direction left

# ページ送りが遅い書籍の場合
python main.py --page-delay 2.0

# 既存の画像ディレクトリから PDF のみを再生成する場合
python main.py --images-dir ./output/MyBook_PNGs

# キャプチャした PNG 画像を削除せずに残す場合
python main.py --screenshots keep
```

### オプション

- `--direction {right,left,space}`: ページめくりの方向（デフォルト: `right`）
- `--page-delay SECONDS`: ページ送り後の待機秒数（デフォルト: `1.5`）
- `--output-dir DIR`: PDF の保存先ディレクトリ（デフォルト: `output`）
- `--images-dir DIR`: 既存の PNG 画像ディレクトリを入力として使用し、キャプチャをスキップします。
- `--screenshots {delete,keep}`: キャプチャした PNG の後処理。`delete` は PDF 生成後に削除（デフォルト）、`keep` は保持します。

## トラブルシューティング

### 共通

**1. スキャンが終了しない / 同じページが何度も撮影される**
- 本ツールは、撮影した画像のハッシュ値（MD5）を比較することで終端を検知します。
- アニメーションやページ送りの遅延により、同じページが連続して撮影されると、3回連続で同じハッシュ値になった時点で「終端」とみなして停止します。
- ページ送りが遅い場合は、`--page-delay 2.0` のように待機時間を長めに設定してください。

**2. PDF が生成されない**
- `output` ディレクトリの権限を確認してください。
- `img2pdf` が正しくインストールされているか確認してください（`uv pip install img2pdf`）。

### Windows

**1. ページ送りがされない / 1ページのみで終了する**
- Kindle アプリのアクティブ化のために一時的にタイトルバーをクリックする関係上、フォーカスが一時的に外れることがあります（自動で Esc キーを送信して復帰を試みます）。
- 改善しない場合は、実行直後の開始猶予時間（Enter キーを押した直後）の間に、**手動で Kindle アプリの書籍本文エリアを一度クリック** してフォーカスを与えてください。
- 使用する書籍や Kindle アプリのバージョンによってページめくりキーが異なるため、改善しない場合は `--direction space` と `--direction right`（デフォルト）の双方をお試しください。
- コマンドプロンプトや PowerShell を「管理者として実行」している場合、セキュリティ制限（UAC）により一般ユーザーとして実行されている Kindle アプリにキー入力を送信できないことがあります。ターミナルと Kindle アプリを同じ権限レベルで実行してください。

### macOS

**1. ページ送りがされない / 権限エラー**
- ターミナル、VSCode、iTerm 等に **「アクセシビリティ」の権限** が付与されているか確認してください。

**2. PDF の最後に評価画面やシークバーが入る**
- macOS 版では、ウィンドウタイトルの変化や UI 要素の「評価」「完了」などのキーワードを検知して自動停止を試みます。
- それでも入り込む場合は、`--page-delay` を少し長めに設定するか、生成後に PDF 編集ソフトで最後のページを削除してください。

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

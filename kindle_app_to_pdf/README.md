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
- **検索可能 PDF への拡張**: 生成された高画質 PDF に OCR 処理（NDLOCR-Lite や ocrmypdf）を適用することで、文字選択や全文検索が可能な PDF へ変換できます（詳細は [OCR による検索可能 PDF の作成方法](#ocr-による検索可能-pdf-の作成方法) を参照）。

## 動作環境

### macOS
- **OS**: macOS 12 (Monterey) 以降推奨 (Intel / Apple Silicon 両対応)
- **Python**: 3.13 推奨 (3.11 以上対応、`.python-version` により uv で自動管理)
- **必須アプリ**: Kindle デスクトップアプリ (App Store 版または Amazon 公式サイト版)
- **依存コマンド**: `osascript`, `screencapture` (macOS 標準搭載)

### Windows
- **OS**: Windows 10 / 11
- **Python**: 3.13 推奨 (3.11 以上対応)
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

**uv を使う場合 (推奨・高速)**
```bash
# uv がインストールされていない場合は先にインストール
# brew install uv

# 自動セットアップ (推奨): .python-version (Python 3.13) と uv.lock に基づいて仮想環境と依存関係を同期
uv sync --all-extras --dev

# または従来方式の手動セットアップ
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

**uv を使う場合 (推奨・高速)**

`uv` は、Python のパッケージ管理や仮想環境構築、スクリプト実行を高速に行える Rust 製のツールです。Python 本体の自動管理機能も備えています。

1. **`uv` のインストール**:
   お好みの方法で `uv` をインストールします。インストール完了後は、必ず**ターミナルを再起動**してください。
   * **PowerShell (推奨)**: 以下のコマンドを実行します。
     ```powershell
     powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   * **winget (Windows パッケージ マネージャー)**: 以下を実行します。
     ```cmd
     winget install astral-sh.uv
     ```

2. **セットアップ**:
   本ツールのディレクトリへ移動し、以下のいずれかの方法でセットアップします。
   * **方法 A: 自動セットアップ (推奨)**
     `pyproject.toml` に基づいて自動で仮想環境の作成から依存パッケージのインストールまでを完了します：
     ```cmd
     uv sync
     ```
   * **方法 B: 手動セットアップ (従来方式)**
     ```cmd
     # 仮想環境の作成 (Pythonが未インストールなら自動取得)
     uv venv
     
     # 仮想環境のアクティベート
     # コマンドプロンプトの場合:
     .venv\Scripts\activate.bat
     # PowerShell の場合:
     .venv\Scripts\Activate.ps1
     
     # パッケージのインストール
     uv pip install -r requirements.txt
     ```

3. **実行 (`uv run`)**:
   仮想環境をアクティベートすることなく、直接ツールを実行することができます：
   ```cmd
   uv run python main.py
   ```
   オプションを指定する場合も同様です：
   ```cmd
   uv run python main.py --page-delay 2.0
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
  run.bat --page-delay 2.0
  ```

### コマンドラインでの実行

```bash
# 標準的な実行（デフォルトでスペースキーによる送り。縦書き・横書きを問わず動作します）
python main.py

# または uv で実行
uv run python main.py

# 矢印キーで明示的に送りたい場合
python main.py --direction right  # 横書き（左開き）書籍
python main.py --direction left   # 縦書き（右開き）書籍

# ページ送りが遅い書籍の場合
python main.py --page-delay 2.0

# 既存の画像ディレクトリから PDF のみを再生成する場合
python main.py --images-dir ./output/MyBook_PNGs

# キャプチャした PNG 画像を削除せずに残す場合
python main.py --screenshots keep
```

### オプション

- `--direction {right,left,space}`: ページめくりの方向（デフォルト: `space`。縦書き・横書きを意識せずに済みます）
- `--title TITLE`: 書籍のタイトル（macOS などウィンドウタイトルから書籍名が取得できない場合に指定。PDF ファイル名に使用されます）
- `--page-delay SECONDS`: ページ送り後の待機秒数（デフォルト: `1.5`）
- `--output-dir DIR`: PDF の保存先ディレクトリ（デフォルト: `output`）
- `--images-dir DIR`: 既存の PNG 画像ディレクトリを入力として使用し、キャプチャをスキップします。
- `--screenshots {delete,keep}`: キャプチャした PNG の後処理。`delete` は PDF 生成後に削除（デフォルト）、`keep` は保持します。

## OCR による検索可能 PDF の作成方法

本ツールで出力される PDF は、キャプチャした高品質な PNG 画像を再エンコードなしで束ねた「画像ベースの PDF」です。
見た目は非常に鮮明ですが、そのままではテキストの選択やコピー、全文検索（Ctrl+F / Cmd+F）ができません。

生成された PDF に OCR（光学文字認識）処理を施し、画像の上に不可視の文字層（透明テキスト）を重ねることで、**オリジナルの高画質な見た目を保ったまま、全文検索やテキストコピーができる検索可能 PDF（Searchable PDF）** を作成できます。

以下に、実用的な作成手順を推奨順に詳しく解説します。

---

### OCR 手法の比較と選び方

日本語の書籍（特に Kindle 本）は、縦書き・横書き、ルビ、見開きなど特有のレイアウトを持ちます。用途や書籍の形式に合わせて適切なエンジンを選択してください。

| 方法 / ツール | 縦書き | 横書き | 特徴・向いている用途 | おすすめ度 |
|---|:---:|:---:|---|:---:|
| **1. NDLOCR-Lite** | **◎** | **◎** | 国立国会図書館開発の日本語特化 OCR。縦書き（右→左の読み順）やルビの除外に対応し、句読点も高精度に維持。画像劣化なしで透明テキスト層付き PDF を直接生成可能。 | **【一番推奨】** |
| **2. pdf-splitter パイプライン** | **◎** | **◎** | 姉妹ツールの自動化パイプライン。NDLOCR-Lite による OCR に加え、目次解析、章ごとの自動分割、20MB 超の均等分割まで一括処理。 | **【自動化・NotebookLM 連携向け】** |
| **3. ocrmypdf (Tesseract)** | **△** | **◯** | オープンソースの定番 CLI ツール。英語書籍や、Homebrew 等でサクッと手軽に処理したい場合に便利（和文縦書きは誤認識や空白混入が増える傾向あり）。 | 手軽さ重視 |
| **4. OS / PDF リーダー機能** | **◯** | **◯** | macOS の「テキスト認識表示（Live Text）」や Adobe Acrobat Pro の OCR 機能。 | GUI 操作 |

---

### 方法 1: 【推奨】NDLOCR-Lite で直接 OCR PDF を生成する

国立国会図書館が開発・公開している軽量版 OCR ツール「**[NDLOCR-Lite](https://github.com/ndl-lab/ndlocr-lite)**」（v1.3.1）を使用する方法です。

日本語の書籍（小説・新書などの縦書き、技術書・ビジネス書などの横書き）に対して非常に高い認識精度を持ち、元の PDF 画像の画質を維持したまま文字層を埋め込んだ `<名前>_ocr.pdf` を直接出力できます。

#### 1. セットアップ（初回のみ）

リポジトリをクローンし、環境変数を設定します（モデルデータ約 150MB を含みます）。

```bash
# 任意の場所に clone (例: ~/tools/ndlocr-lite)
git clone --depth 1 --branch 1.3.1 https://github.com/ndl-lab/ndlocr-lite ~/tools/ndlocr-lite

# 環境変数にパスを設定
export NDLOCR_LITE_DIR=~/tools/ndlocr-lite
```

> [!TIP]
> ターミナルを再起動しても使えるよう、お使いのシェルの設定ファイル（macOS の場合は `~/.zshrc`、Linux の場合は `~/.bashrc`）に `export NDLOCR_LITE_DIR="$HOME/tools/ndlocr-lite"` を追記しておくことを推奨します。

#### 2. OCR の実行

`uv` を利用して実行します。NDLOCR-Lite 側の必要な依存関係が一時環境に自動解決されます。

```bash
# NDLOCR-Lite の CLI コマンド（ndlocr-lite）で実行する場合
uv run --project "$NDLOCR_LITE_DIR" ndlocr-lite \
  --sourcepdf "/path/to/output/MyBook.pdf" \
  --pdf-output "/path/to/output/MyBook_ocr.pdf" \
  --output "/path/to/output"
```

または、スクリプトパスを直接指定して実行する場合：

```bash
uv run --project "$NDLOCR_LITE_DIR" python "$NDLOCR_LITE_DIR/src/ocr.py" \
  --sourcepdf "/path/to/output/MyBook.pdf" \
  --pdf-output "/path/to/output/MyBook_ocr.pdf" \
  --output "/path/to/output"
```

#### 特徴と処理時間の目安
- **処理速度**: Apple Silicon (M1/M2/M3) CPU 環境で **約 1〜3 秒 / ページ**。200 ページ前後の書籍でおよそ 8〜10 分程度で完了します。
- **画質と容量**: 元の画像解像度（PNG ロスレス）はそのまま保持され、不可視のテキスト情報のみが追加されるため、ファイルサイズはほぼ変わりません。
- **ルビと読み順**: 本文とルビを適切に分離し、縦書き書籍でも右列から左列へと正しい順番でテキスト化されます。

---

### 方法 2: 【全自動】pdf-splitter パイプラインで OCR ＆ 章分割を一括実行する

本リポジトリの姉妹ツールである `../pdf-splitter`（PDF Splitter & OCR Chapter Pipeline）と連携する方法です。

単に OCR 処理を行うだけでなく、OCR 結果から目次や見出しキーワード（「第1章」「はじめに」など）を自動解析して**章ごとに PDF を分割**し、さらに NotebookLM 等のインポート上限（20MB）を超える章は自動で均等分割してくれます。

#### 1. 実行手順

`pdf-splitter` ディレクトリへ移動し、本ツールで生成した PDF パスを渡して実行します。

```bash
# 1. pdf-splitter ディレクトリに移動
cd ../pdf-splitter

# 2. パイプラインを実行（NDLOCR_LITE_DIR が設定されている必要があります）
uv run scripts/pdf_chapter_pipeline.py "../kindle_app_to_pdf/output/MyBook.pdf"
```

※ Tesseract (`ocrmypdf`) を使いたい場合は、`--ocr-engine tesseract --lang jpn+eng` を付与します。

#### 2. 生成されるファイル

処理が完了すると、`<入力元ディレクトリ>/output/<書籍名>/` 配下に以下のファイルが自動生成されます：

- `MyBook_ocr.pdf` : 書籍全体の OCR 済み検索可能 PDF
- `MyBook_ch01_はじめに.pdf` : 章ごとに分割された PDF（各 20MB 以下に調整済み）
- `MyBook_ch02_第1章_xxx.pdf` : 〃

#### 3. AI エージェント連携（Antigravity / Claude Code）
AI コーディングアシスタント上で `pdf-ocr-chapter-splitter` サブエージェントが有効になっている環境では、チャット上で以下のように指示するだけで一連の OCR・章分割処理が全自動で実行されます：

> 「output/MyBook.pdf を OCR して章ごとに分割して」

---

### 方法 3: ocrmypdf を使う（手軽・英語書籍向け）

オープンソースの標準的 OCR ツール「`ocrmypdf`（Tesseract OCR ベース）」を使用する方法です。
Mac の Homebrew で手軽にインストールでき、英語主体の書籍や、手早く OCR を試したい場合に適しています。

#### 1. インストール

- **macOS (Homebrew)**:
  ```bash
  brew install ocrmypdf tesseract-lang
  ```
- **Windows**:
  - [Chocolatey](https://chocolatey.org/) や Docker、WSL (Windows Subsystem for Linux) を利用してインストールします。

#### 2. 実行コマンド

- **横書き書籍（日本語 + 英語）**:
  ```bash
  ocrmypdf -l jpn+eng --skip-text "output/MyBook.pdf" "output/MyBook_ocr.pdf"
  ```

- **縦書き書籍（日本語縦書き）**:
  ```bash
  ocrmypdf -l jpn_vert+jpn --skip-text "output/MyBook.pdf" "output/MyBook_ocr.pdf"
  ```

> [!NOTE]
> `--skip-text` オプションを付けることで、すでにテキスト層が存在するページがある場合でも二重処理を防ぎ安全に変換できます。
> なお、Tesseract は和文文字の間に余計な空白が挿入されやすい傾向があるため、日本語の小説や縦書き書籍を本格的にテキスト化する場合は「方法 1 (NDLOCR-Lite)」を強く推奨します。

---

### 方法 4: PDF ビューア・OS 標準機能の活用

コマンドラインを使わずに確認・利用したい場合、以下の方法もあります。

- **macOS「プレビュー」アプリのテキスト認識表示（Live Text）**:
  macOS 12 (Monterey) 以降では、本ツールで生成した画像 PDF を「プレビュー」で開くだけで、OS 組み込みの機械学習により画面上の文字を直接ドラッグ選択・コピー・検索（Cmd+F）できます（ファイル自体を OCR 変換する必要すらありません）。
- **Adobe Acrobat Pro**:
  ツール >「スキャンと OCR」>「テキストを認識」を実行することで、高精度な透明テキスト層付き PDF に変換・保存できます。

---

### OCR 実行時の注意点と Tips

1. **キャプチャ画像の静止を確保する**:
   Kindle アプリのページ送りアニメーション中にキャプチャされると、文字がブレて OCR の認識精度が大幅に低下します。キャプチャ実行時は `--page-delay 1.5`（ページ送りが重い本は `2.0`）を指定し、完全に表示が落ち着いた状態でキャプチャしてください。
2. **処理時間とタイムアウト**:
   数十ページ〜数百ページの本を OCR する場合、PC の CPU スペックに応じて 5〜20 分程度の時間がかかります。ターミナルを閉じずにバックグラウンドで処理を待機してください。
3. **著作権法への配慮**:
   OCR によって生成されたテキストや検索可能 PDF についても、著作権法の認める私的使用の範囲内（個人での閲覧、学習、検索等）で適切にご利用ください。

## テストと品質保証（変換の自動テスト）

本ツールでは、キャプチャロジックや PDF 変換処理の信頼性を担保するため、ユニットテスト（カバレッジ 100% 維持）に加えて、**縦書き書籍・横書き書籍を対象とした 2 種類の変換自動テスト**を用意しています。

### 1. CI・ローカル用モック自動テスト（Kindle アプリ不要・推奨）

Kindle アプリを起動できない環境（GitHub Actions 等の CI パイプラインや、Kindle を開かずに素早くロジックを検証したい場合）向けの自動テストです。
Pillow を用いて縦書き・横書きの書籍画像を動的に生成し、キャプチャループ、重複検知による停止判定、PDF 生成、および生成された PDF の構造（ページ数やアスペクト比）が正しいかをミリ秒単位で網羅的にテストします。

- **対象書籍サンプル**:
  - **縦書き書籍（右開き）**: 『走れメロス』（縦長画像、ページ送り後のハッシュ変化と終端停止を検証）
  - **横書き書籍（左開き）**: 『Alice's Adventures in Wonderland』（横長・見開き画像、ページ送り後のハッシュ変化と終端停止を検証）
- **テストファイル**: [`tests/test_sample_books_conversion.py`](tests/test_sample_books_conversion.py)
- **実行コマンド**:
  ```bash
  # 走れメロス（縦書き）の変換テストのみ実行
  uv run pytest tests/test_sample_books_conversion.py -k merosu -v

  # Alice's Adventures in Wonderland（横書き）の変換テストのみ実行
  uv run pytest tests/test_sample_books_conversion.py -k alice -v

  # サンプル書籍テストをすべて実行
  uv run pytest tests/test_sample_books_conversion.py -v
  ```

### 2. 実機 E2E 自動テスト（Kindle アプリ実機連携）

実際に起動しているデスクトップ版 Kindle アプリと連携し、ウィンドウの検知、前面化、ページ送りキー（Space）の送信、画面キャプチャ、および実際の PDF 生成までの一連のフローをエンドツーエンドで自動検証します。

- **事前準備**:
  1. デスクトップ版 Kindle アプリを起動し、対象書籍（『走れメロス』または『Alice's Adventures in Wonderland』）を開いておきます。
  2. macOS の場合、「システム設定 > プライバシーとセキュリティ」にて、実行するターミナルに「アクセシビリティ」および「画面収録」の権限が付与されていることを確認します。
- **テストファイル**: [`tests/test_e2e_kindle.py`](tests/test_e2e_kindle.py)
- **検証項目**:
  - Kindle ウィンドウのアクティブ化
  - ページ送りキー送信によるページ遷移
  - キャプチャ画像の取得と `output/{書籍名}.pdf` への保存
  - `pypdf.PdfReader` を用いて、生成された PDF に実際に複数ページが含まれ、期待されるアスペクト比（縦長 / 横長）になっているかのアサーション
- **実行コマンド**:
  ```bash
  # 走れメロス（縦書き実機）の E2E テスト
  uv run pytest tests/test_e2e_kindle.py -k merosu -s

  # Alice's Adventures in Wonderland（横書き実機）の E2E テスト
  uv run pytest tests/test_e2e_kindle.py -k alice -s
  ```

### 3. OCR・章分割連携自動テスト（縦書き・横書き日本語）

NDLOCR-Lite (`ocr.py`)、`ocrmypdf` (Tesseract)、および `pdf_chapter_pipeline.py` の OCR 認識と章分割処理を、Pillow で生成した**縦書き日本語（右開き小説調）**および**横書き日本語（技術書調）**の書籍サンプルを用いてエンドツーエンドで自動検証します。

- **テストファイル**: [`tests/test_ocr_and_pipeline.py`](tests/test_ocr_and_pipeline.py)
- **検証項目**:
  - `TestNDLOCR`:
    - `test_ndlocr_horizontal_japanese`: 横書き日本語サンプルの OCR（文字層埋め込みとキーワード「第1章」「はじめに」等の認識）
    - `test_ndlocr_vertical_japanese`: 縦書き日本語サンプルの OCR（右列→左列、上→下の読み順認識と「第1章」「メロス」等の認識）
  - `TestOCRMyPDF`:
    - `test_ocrmypdf_horizontal_japanese`: 横書き日本語サンプルの ocrmypdf 実行とテキスト層付与
    - `test_ocrmypdf_vertical_japanese`: 縦書き日本語サンプルの ocrmypdf 実行とテキスト層付与
  - `TestPdfChapterPipeline`:
    - `test_pipeline_horizontal_japanese_chapters`: 横書き日本語書籍の OCR 実行、章キーワード検出、および章ごとの PDF 分割
    - `test_pipeline_vertical_japanese_chapters`: 縦書き日本語書籍の OCR 実行、縦書き章見出し検出、および章ごとの PDF 分割
- **実行コマンド**:
  ```bash
  # OCR・パイプライン連携テストのみ実行
  uv run pytest tests/test_ocr_and_pipeline.py -v -s
  ```

### 4. 全体テストスイート・品質チェック・カバレッジ 100% 保証

全 86 件のテスト（ユニットテスト・統合テスト・OCR連携テスト）および静的解析（Linter / 型チェック）、テストカバレッジ 100% の検証を一括実行できます。
本プロジェクトでは `pyproject.toml` の `[tool.coverage.report]` に `fail_under = 100` を設定しており、**全ステートメントのカバレッジ 100%（Missing: 0）** を厳格に保証しています。

```bash
# 全テスト実行（全 86 件・全件パス）
uv run pytest

# カバレッジ測定（カバレッジ 100% を検証・未カバー行なし）
uv run pytest --cov --cov-report=term-missing

# Ruff によるコードフォーマット・Lint チェック
uv run ruff check .

# Mypy による型チェック
uv run mypy .
```

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
- 使用する書籍や Kindle アプリのバージョンによってキー入力への反応が異なる場合があるため、改善しない場合は書籍の開き方向に応じて `--direction right`（横書き）や `--direction left`（縦書き）もお試しください。
- コマンドプロンプトや PowerShell を「管理者として実行」している場合、セキュリティ制限（UAC）により一般ユーザーとして実行されている Kindle アプリにキー入力を送信できないことがあります。ターミナルと Kindle アプリを同じ権限レベルで実行してください。

**2. 画面のクリック位置がずれて、フォーカスが当たらない（高 DPI 環境）**
- Windows のディスプレイ設定で画面のスケーリングが 100% 以外（例: 125% や 150%）に設定されている場合、PyAutoGUI のクリック座標系がズレる問題が発生することがあります。
- 本ツールでは自動的に DPI スケールを補正する処理（`_focus_window` 内）を導入していますが、それでもクリックがずれる場合は、一時的に Windows のディスプレイ設定にて画面スケールを「100%」に変更してからお試しください。

### macOS

**1. ページ送りがされない / 権限エラー**
- ターミナル、VSCode、iTerm 等に **「アクセシビリティ」の権限** が付与されているか確認してください。
- 権限が不足している場合、以下のようなエラーが発生します：
  ```
  RuntimeError: AppleScript エラー: 33:78: execution error: System Events でエラーが発生しました: アシスタティブ・デバイスの制御は許可されていません。 (-1719)
  ```
- システム設定の「プライバシーとセキュリティ」＞「アクセシビリティ」から、実行中のターミナルアプリ（Terminal, VSCode 等）を明示的にオンにしてください。

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
├── .python-version      # uv / pyenv 向け Python バージョン指定 (3.13)
├── .tool-versions       # asdf / mise 向け Python バージョン指定 (3.13.5)
├── requirements.txt     # 依存 Python ライブラリの一覧（pip/uv用）
├── pyproject.toml       # Python プロジェクト設定（uv/ruff/mypy/coverage用）
├── uv.lock              # パッケージバージョン固定用ロックファイル (Pillow 12.x, pypdf 6.x 等)
├── README.md            # 本ドキュメント
│
├── tests/               # 自動テストスイート（ユニットテスト / 結合テスト / E2Eテスト）
│   ├── test_ocr_and_pipeline.py        # OCR（NDLOCR/ocrmypdf）と章分割パイプラインの縦書き・横書きテスト
│   ├── test_sample_books_conversion.py # 縦書き（メロス）・横書き（Alice）のサンプル書籍自動テスト
│   ├── test_e2e_kindle.py              # 実機 Kindle 連携 E2E テスト
│   ├── test_kindle_capture.py          # キャプチャ・ウィンドウ制御テスト
│   ├── test_main.py                    # CLI インターフェーステスト
│   ├── test_pdf_maker.py               # PDF 作成ロジックテスト
│   └── test_split_pdf.py               # PDF 分割テスト
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
- **tests/**: 100% カバレッジを維持する自動テストスイート。Kindle アプリ不要のモック変換テストや実機 E2E テストを含みます。

## ライセンス

MIT

# PDF Splitter & OCR Chapter Pipeline Plugin

カレントディレクトリ内のスキャンPDFをOCR処理して検索可能にし、目次（TOC）情報を解析して章ごとに自動分割するエージェントとスクリプトのプラグインです。

---

## 目次 (Table of Contents)

1. [概要](#概要)
2. [プロジェクト構成](#プロジェクト構成)
3. [依存関係とセットアップ](#依存関係とセットアップ)
4. [OCR について](#ocr-について)
5. [実行方法とオプション](#実行方法とオプション)
6. [グローバルな設定・更新方法](#グローバルな設定・更新方法)
   - [初期設定（シンボリックリンクの作成）](#初期設定シンボリックリンクの作成)
   - [更新方法（Gitによる一元管理）](#更新方法gitによる一元管理)
7. [クライアント別の利用方法](#クライアント別の利用方法)
   - [Antigravity CLI (agy) & Desktop App](#1-antigravity-cli-agy--desktop-app)
   - [Codex (Antigravity IDE)](#2-codex-antigravity-ide)
   - [Claude Code](#3-claude-code)

---

## 概要

このプラグインは、以下の2つの主要な処理機能を提供します。

- **`pdf-ocr-chapter-splitter`**: 電子書籍などのスキャンPDFをOCR処理（既定は NDLOCR-Lite、`--ocr-engine tesseract` で `ocrmypdf`）し、出力されたテキストから目次情報を解析して章ごとにPDFを分割します。また、分割後のファイルが20MBを超える場合は、自動的にさらに細かく分割します。
- **`pdf-splitter`**: 指定フォルダ内のすべてのPDFファイルをスキャンし、単純に20MB以下の均等なページ数になるように自動分割します。

---

## プロジェクト構成

本リポジトリ（`/Users/katoy/github/study-gemini-3/pdf-splitter`）のディレクトリ構成は以下の通りです。

```text
pdf-splitter/
├── plugin.json                           # プラグインのメタデータ定義
├── .gitignore                            # キャッシュやPDF成果物の無視設定
├── agents/
│   ├── pdf-ocr-chapter-splitter/
│   │   └── agent.md                      # 章分割エージェントの指示書
│   └── pdf-splitter/
│       └── agent.md                      # 均等分割エージェントの指示書
├── skills/
│   └── pdf-splitter/
│       └── SKILL.md                      # スキル説明ドキュメント
├── scripts/
│   ├── pdf_chapter_pipeline.py           # OCR & 目次解析・章分割スクリプト (Python)
│   ├── pdf_utils.py                      # OCR 実行 (NDLOCR-Lite / ocrmypdf) などの共通処理
│   └── split_pdf.py                      # 均等分割スクリプト (Python)
├── tests/                                # pytest による単体テスト
├── bench/                                # OCR エンジン比較ベンチ (engines/ 各エンジンのラッパー、compare.py 集計)
├── docs/
│   └── myocr_evaluation.md               # OCR エンジンの評価レポート
└── README.md                             # 本ファイル
```

---

## 依存関係とセットアップ

実行環境に以下のツールがインストールされている必要があります。

1. **Python / uv** (スクリプトの依存関係マネージャ)
   ```bash
   # uv がインストールされていない場合はインストールしてください
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. **NDLOCR-Lite** (既定の OCR エンジン。縦書き・横書きの日本語に対応し、句読点も保持する)
   ```bash
   # 任意の場所に clone し、その場所を環境変数 NDLOCR_LITE_DIR で指定する（モデル約 150MB を含む）
   git clone --depth 1 --branch 1.3.1 https://github.com/ndl-lab/ndlocr-lite ~/tools/ndlocr-lite
   export NDLOCR_LITE_DIR=~/tools/ndlocr-lite
   ```
   - 毎回設定しなくて済むよう、`export NDLOCR_LITE_DIR="$HOME/tools/ndlocr-lite"` を `~/.zshrc` に追記しておくことを推奨します。
   - 実行時に `uv` が NDLOCR-Lite 固定版の依存（`requirements.txt`）を一時環境に入れて起動します。
   - v1.3.1 は `uv tool install` だと `pdf_output_utils` が欠けて起動できないため、clone して使います。
   - ライセンス: CC BY 4.0（同梱モデルには DINOv3 License も適用）。出典「国立国会図書館 NDLOCR-Lite」。再配布時は LICENCE と LICENCE_DEPENDENCEIES を同梱してください。
   - ocrmypdf の `--skip-text` と違い、既存の文字層があるページも OCR し直します（画像のみの Kindle 由来 PDF では問題ありません）。
3. **ocrmypdf** (`--ocr-engine tesseract` を指定する場合のみ)
   ```bash
   # macOS の場合 (Tesseract OCR 等の依存パッケージも自動でインストールされます)
   brew install ocrmypdf
   ```

> [!IMPORTANT]
> `uv`・NDLOCR-Lite・`ocrmypdf` はスクリプトやエージェントによって**自動インストールされません**。
> インストールされていない場合はエラー終了するため、事前に上記のコマンドで手動インストールを完了させておいてください。

---

## OCR について

### エンジンの選択

| エンジン | 指定方法 | 向いている用途 |
|---|---|---|
| **NDLOCR-Lite**（既定） | `--ocr-engine ndlocr` | 日本語の本全般（縦書き・横書きの両方） |
| Tesseract (ocrmypdf) | `--ocr-engine tesseract --lang jpn+eng` | NDLOCR-Lite を用意できない環境、英語中心の PDF |

Kindle 本のページ画像で比較した結果（文字誤り率 CER、詳細は [docs/myocr_evaluation.md](docs/myocr_evaluation.md)）:

| | NDLOCR-Lite | Tesseract |
|---|---:|---:|
| 横書き CER | 2.4% | 9.1% |
| 縦書き CER | 4.8% | 21.5%（`jpn_vert`） |
| 和文の文字間に入る余計な空白 | ほぼなし | 多数（目次・章検出を壊す） |

- NDLOCR-Lite は縦書きの読み順（右→左）とルビの除外を自動で処理し、句読点もほぼ保持します。
- 他に RapidOCR・YomiToku・MyOCR も検証しました。縦書きで句読点が消える（RapidOCR）、遅く非商用ライセンス（YomiToku）などの理由で不採用です。

### 処理の流れ（NDLOCR-Lite）

1. `pdf_utils.run_ocr` が `uv run` で NDLOCR-Lite の `ocr.py` を `--sourcepdf <入力> --pdf-output <出力>` 付きで起動します。
2. NDLOCR-Lite が各ページを 150dpi で画像化して OCR し、元のページ画像に透明な文字層を重ねた PDF を書き出します。ページ画像の解像度は変わらず、ファイルサイズもほぼ同じです。
3. 出力 PDF は `<入力PDFのフォルダ>/output/<名前>/<名前>_ocr.pdf` に保存され、2 回目以降は再利用されます（やり直す場合は `--force-ocr`）。

### 処理時間の目安

- 約 3 秒/ページ（CPU、Apple M1 で計測）。164 ページの本で約 8 分です。
- タイムアウトは 30 分です。約 600 ページを超える本では打ち切られる可能性があります。
- 初回はモデルと依存ライブラリの準備に余分な時間がかかります。

### OCR 結果からの章検出

目次ページに印字されたページ番号があれば、それを使って章の開始ページを決めます。Kindle 本の目次はリンクのみでページ番号を持たないことが多いため、その場合は各ページ先頭の見出し（「第1章」「CHAPTER 1」「はじめに」など）を探すキーワード検出に切り替わります。

キーワード検出では、OCR 結果の揺れを次のように吸収します。

- テキストを NFKC 正規化してから照合します（全角の「第１章」も検出）。
- 「第1章Obsidian」のように「章」の直後に空白がない見出しも検出します。
- 「第5章では、…」のように、後ろに助詞や句読点が続くものは本文中の言及とみなして無視します。
- 「CHAPTER 1」と「第1章」は同じ章として扱い、ページ上端の柱（章タイトル）が続くページでは新しい章を始めません。

### 注意点

- NDLOCR-Lite は既存の文字層があるページも OCR し直します（ocrmypdf の `--skip-text` に相当する機能はありません）。
- 縦中横（縦書き中の横向き数字）の検出は無効のままです。
- 「……」（三点リーダー）は取りこぼしやすい傾向があります。

---

## 実行方法とオプション

### 基本的な実行方法
`uv run` を使用して、依存ライブラリを自動解決しながらスクリプトを実行します。

```bash
uv run scripts/pdf_chapter_pipeline.py "<対象PDFの絶対パス>"
```

### 高度なオプションとトラブルシューティング

#### 1. 使用する Python バージョンの明示
システムの Python 環境によっては、`uv` が特定の古いバージョンを探索してエラー終了することがあります。その場合は `--python 3.12`（または3.12以上のバージョン）を明示して実行してください。

```bash
uv run --python 3.12 scripts/pdf_chapter_pipeline.py "<対象PDFの絶対パス>" --max-size-mb 20
```

Tesseract (ocrmypdf) で OCR する場合は `--ocr-engine tesseract --lang jpn+eng`（縦書きは `--lang jpn_vert`）を指定します。`scripts/split_pdf.py` も同じ `--ocr-engine` を受け付けます。

#### 2. 目次解析の失敗（フォールバック）と手動による章指定 (`--chapters-json`)
OCRのテキスト化精度やPDFのレイアウトによっては、自動的な目次ページの判定・解析に失敗し、キーワード検出や均等分割にフォールバックすることがあります。
正確な章分割を行いたい場合は、手動で章の開始「物理ページ番号」を記述した JSON ファイルを作成し、`--chapters-json` で指定して再実行します。

**JSON ファイルの作成例 (`chapters.json`)**:
```json
[
  {"title": "まえがき", "page": 4},
  {"title": "第 1 章 Agent Skills って何だろう", "page": 18},
  {"title": "第 2 章 Agent Skills の仕組み", "page": 49},
  {"title": "付録", "page": 291}
]
```

**実行コマンド**:
```bash
uv run --python 3.12 scripts/pdf_chapter_pipeline.py "<対象PDFの絶対パス>" --chapters-json "<作成したchapters.jsonの絶対パス>"
```

---

## グローバルな設定・更新方法

プラグインをグローバルに登録することで、どのプロジェクトで作業していても `pdf-ocr-chapter-splitter` などのエージェントを呼び出せるようになります。

### 初期設定（シンボリックリンクの作成）

現在のワークスペースフォルダから、Antigravityプラットフォームのグローバルプラグイン領域へのシンボリックリンクを作成します。

ターミナルで以下のコマンドを実行してください。

```bash
# 1. 既存のグローバルプラグイン設定を削除
rm -rf ~/.gemini/config/plugins/pdf-splitter

# 2. 本フォルダからグローバルプラグインへのシンボリックリンクを作成
ln -s /Users/katoy/github/study-gemini-3/pdf-splitter ~/.gemini/config/plugins/pdf-splitter

# 3. 必要に応じて、グローバルのスクリプト領域にもリンクを作成
rm -f ~/.gemini/antigravity-cli/scripts/pdf_chapter_pipeline.py
ln -s /Users/katoy/github/study-gemini-3/pdf-splitter/scripts/pdf_chapter_pipeline.py ~/.gemini/antigravity-cli/scripts/pdf_chapter_pipeline.py
```

### 更新方法（Gitによる一元管理）

ファイルの実体は本フォルダ（`/Users/katoy/github/study-gemini-3/pdf-splitter`）にのみ存在するため、更新作業はすべてこのフォルダ内で行います。

- **エージェント指示の調整やスクリプトの編集**:
  本フォルダ内のファイルを直接編集・保存するだけで、シンボリックリンクを通じてグローバル側にも**即座に自動反映**されます。
- **最新版への更新 / 変更の保存**:
  ```bash
  # 最新のコードを適用する場合
  git pull origin main

  # 変更を保存する場合
  git add .
  git commit -m "Update agent rules or scripts"
  git push origin main
  ```

---

## クライアント別の利用方法

### 1. Antigravity CLI (`agy`) & Desktop App

グローバルプラグインに登録されているため、起動時に自動的に読み込まれます。

- **エージェントの呼び出し**:
  対話中に以下のようにエージェントを直接呼び出すか、処理を委任します。
  ```text
  /invoke pdf-ocr-chapter-splitter
  ```
- **スキルの使用**:
  ```text
  現在のフォルダにある「sample.pdf」を章ごとに分割して。
  ```
  エージェントが自動的に `pdf-splitter` スキルや `pdf-ocr-chapter-splitter` サブエージェントを実行して処理します。

### 2. Codex (Antigravity IDE)

IDEを起動すると、左側または右側のサイドバーパネルにグローバルエージェントとして `pdf-ocr-chapter-splitter` および `pdf-splitter` が表示されます。

- **操作方法**:
  1. チャットパネルのエージェント選択ドロップダウンから `pdf-ocr-chapter-splitter` を選択します。
  2. チャットに `分割対象のPDFファイル` もしくは `対象フォルダ` を指定して指示を送信します。
  3. エージェントが裏で `uv run` を用いてスクリプトを呼び出し、進行状況と結果を視覚的にレポートします。

### 3. Claude Code

Claude Code はローカルでのシェルコマンド実行を自律的に行えるため、本プロジェクトのスクリプトをグローバルなコマンドとして登録しておくか、Claude Code に直接実行させることで利用できます。

#### 方法 A: パスを通して直接指示する（推奨）
スクリプトへのシンボリックリンクをユーザーの `bin` ディレクトリなどに配置します。

```bash
# 例: ~/.local/bin/ 配下にリンクを作成 (パスが通っている必要があります)
ln -s /Users/katoy/github/study-gemini-3/pdf-splitter/scripts/pdf_chapter_pipeline.py ~/.local/bin/pdf_chapter_pipeline
```
設定後、Claude Code のプロンプトで以下のように指示します：
> 「現在のディレクトリにある book.pdf を `pdf_chapter_pipeline` コマンドを使って章ごとに分割して。」

Claude Code は自律的に `pdf_chapter_pipeline book.pdf` などのコマンドを実行し、完了まで待機します。

#### 方法 B: Antigravity 委任コマンドの利用
Claude Code から `agy` プラグイン経由で処理を委任します。

```text
/antigravity:delegate "現在のディレクトリにある book.pdf を章ごとに分割して"
```
これにより、Claude Code からバックグラウンドの `agy` にタスクが投げられ、処理完了後にレポートが返ってきます。

# PDF Splitter & OCR Chapter Pipeline Plugin

カレントディレクトリ内のスキャンPDFをOCR処理して検索可能にし、目次（TOC）情報を解析して章ごとに自動分割するエージェントとスクリプトのプラグインです。

---

## 目次 (Table of Contents)

1. [概要](#概要)
2. [プロジェクト構成](#プロジェクト構成)
3. [依存関係とセットアップ](#依存関係とセットアップ)
4. [グローバルな設定・更新方法](#グローバルな設定・更新方法)
   - [初期設定（シンボリックリンクの作成）](#初期設定シンボリックリンクの作成)
   - [更新方法（Gitによる一元管理）](#更新方法gitによる一元管理)
5. [クライアント別の利用方法](#クライアント別の利用方法)
   - [Antigravity CLI (agy) & Desktop App](#1-antigravity-cli-agy--desktop-app)
   - [Codex (Antigravity IDE)](#2-codex-antigravity-ide)
   - [Claude Code](#3-claude-code)

---

## 概要

このプラグインは、以下の2つの主要な処理機能を提供します。

- **`pdf-ocr-chapter-splitter`**: 電子書籍などのスキャンPDFをOCR処理（`ocrmypdf`）し、出力されたテキストから目次情報を解析して章ごとにPDFを分割します。また、分割後のファイルが20MBを超える場合は、自動的にさらに細かく分割します。
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
│   └── split_pdf.py                      # 均等分割スクリプト (Python)
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
2. **ocrmypdf** (PDF OCRツール)
   ```bash
   # macOS の場合 (Tesseract OCR 等の依存パッケージも自動でインストールされます)
   brew install ocrmypdf
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

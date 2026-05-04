# Kindle to PDF - Project Setup & Build Guide

このドキュメントは、kindle_to_pdf プロジェクトを構築・実行するための包括的なガイドです。

## 📋 プロジェクト概要

**Kindle to PDF** は、Kindle Cloud Reader で開いている本を自動でキャプチャし、高品質な画像 PDF を生成するツールです。

### 主な特徴
- **無劣化・最高画質**: `img2pdf` で PNG を再エンコードせず結合。オリジナル品質を完全維持
- **macOS Live Text 最適化**: OCR 不要。macOS のテキスト認識機能と相性が良い
- **賢い終端検出**: MD5 ハッシュ比較で、書籍終了を自動判定
- **レンダリング安定待機**: ページ遷移後、完全レンダリングまで待機
- **自動 Chrome 起動**: `--launch-chrome` で専用セッションを自動化

---

## 🛠 環境要件

| 要件 | バージョン | 説明 |
|---|---|---|
| OS | macOS / Windows / Linux | macOS 推奨 |
| Python | 3.12+ | |
| パッケージマネージャー | uv | 推奨（pip でも可） |

---

## 🚀 セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/katoy/study-gemini-3.git
cd study-gemini-3/kindle_to_pdf
```

### 2. 環境構築（推奨方法：uv を使用）

#### macOS / Linux

```bash
# セットアップスクリプトを実行（最も簡単）
chmod +x setup.sh
./setup.sh

# または手動で以下を実行
uv sync
uv run playwright install chromium
```

#### Windows (PowerShell)

```powershell
# バッチファイルで自動セットアップ
.\setup_win.bat

# または手動で実行
uv sync
uv run playwright install chromium
```

### 3. 環境確認

```bash
# Python バージョン確認
python --version  # 3.12 以上であることを確認

# uv がインストール済みか確認
uv --version

# 仮想環境が正常か確認
uv run python -c "import playwright; print('Playwright OK')"
```

---

## 📖 実行方法

### 基本的な使用方法

#### macOS / Linux

```bash
# 最も推奨される方法：自動で Chrome を起動してキャプチャ
uv run python main.py --launch-chrome

# または付属スクリプトで実行
./run.sh
```

#### Windows

```powershell
# バッチファイルで実行（推奨）
.\run_win.bat

# または PowerShell スクリプトで実行
.\run_win.ps1

# または直接実行
uv run python main.py --launch-chrome
```

### よくある使用例

#### 例 1: 標準的なキャプチャ（Chrome 自動起動）

```bash
uv run python main.py --launch-chrome
```

**動作**:
1. 新しい Chrome セッションを起動
2. `read.amazon.co.jp` または `read.amazon.com` を自動検出
3. ArrowDown キーでページ遷移
4. 各ページをスクリーンショット
5. 画像が安定するまで待機（MD5 ハッシュ比較）
6. 同じ画面が 3 回続いたら終了
7. `./output/<書籍タイトル>/` に PNG を保存
8. PDF を生成してデフォルト出力先に保存

#### 例 2: 既存のキャプチャ画像から PDF のみ生成

```bash
uv run python main.py --images-dir ./output/書籍タイトル
```

#### 例 3: キャプチャ画像を保持する

```bash
uv run python main.py --launch-chrome --screenshots keep
```

#### 例 4: ページ遷移の待機時間を調整

```bash
uv run python main.py --launch-chrome --page-delay 2.0
```

#### 例 5: 出力先を指定

```bash
uv run python main.py --launch-chrome --output-dir /path/to/output
```

---

## ⚙️ コマンドラインオプション

| オプション | 省略形 | デフォルト | 説明 |
|---|---|---|---|
| `--output-dir` | `-o` | `./output` | 生成物の保存先ディレクトリ |
| `--launch-chrome` | - | なし（指定時のみ） | 専用の Chrome インスタンスを自動起動し CDP で接続 |
| `--screenshots` | - | `delete` | `delete`（終了後に削除）または `keep`（保持） |
| `--page-delay` | - | `0.8` | ページ遷移後の最低待機秒数 |
| `--images-dir` | - | なし | 指定した画像ディレクトリを入力として PDF を生成 |
| `--chrome-user-data-dir` | - | 一時フォルダ | Chrome プロファイル保存先（`--launch-chrome` 使用時） |

---

## 📂 ファイル構成

```
kindle_to_pdf/
├── main.py                  # エントリーポイント。CLI 引数処理と全体フロー管理
├── kindle_capture.py        # Playwright を使用したブラウザ操作・キャプチャ
├── pdf_maker.py             # img2pdf を使用した PDF 生成
├── tests/
│   ├── test_main.py         # main.py のテスト
│   ├── test_kindle_capture.py
│   ├── test_pdf_maker.py
│   └── __init__.py
├── run.sh                   # macOS / Linux 起動スクリプト
├── run_win.bat              # Windows バッチファイル
├── run_win.ps1              # Windows PowerShell スクリプト
├── setup.sh                 # macOS / Linux セットアップスクリプト
├── setup_win.bat            # Windows セットアップバッチ
├── check_quality.sh         # macOS / Linux 品質チェック
├── check_quality.bat        # Windows 品質チェック（Command Prompt）
├── check_quality.ps1        # Windows 品質チェック（PowerShell）
├── pyproject.toml           # uv プロジェクト定義
└── README.md                # 本ドキュメント
```

---

## 🧪 テストの実行

### すべてのテストを実行

```bash
uv run pytest
```

### 特定のテストファイルのみ実行

```bash
uv run pytest tests/test_kindle_capture.py
uv run pytest tests/test_pdf_maker.py
uv run pytest tests/test_main.py
```

### カバレッジを確認（詳細表示）

```bash
uv run pytest --cov=. --cov-report=term-missing
```

### HTML カバレッジレポート生成

```bash
uv run pytest --cov=. --cov-report=html
open htmlcov/index.html  # macOS
# Windows の場合は htmlcov\index.html をブラウザで開く
```

**品質基準**: テストカバレッジは **100%** が必須です。

---

## ✅ 品質チェック

コード品質を保証するため、以下の 3 つのチェックを実行できます：

1. **ruff**: Python コードのリント（スタイル違反、潜在的なバグ）
2. **mypy**: 型チェック（型安全性の検証）
3. **pytest**: テスト実行とカバレッジ確認（100% カバレッジが必須）

### macOS / Linux

```bash
chmod +x check_quality.sh
./check_quality.sh
```

### Windows (Command Prompt)

```cmd
check_quality.bat
```

### Windows (PowerShell)

```powershell
.\check_quality.ps1
```

### 各チェックを個別に実行

```bash
# ruff チェック
uv run ruff check .

# mypy で型チェック
uv run mypy main.py kindle_capture.py pdf_maker.py

# pytest でテスト実行
uv run pytest --cov=.
```

---

## 🏗 プロジェクトアーキテクチャ

3 つのモジュールで構成された直列パイプライン：

```
main.py
  ↓
kindle_capture.py
  ↓
pdf_maker.py
```

### モジュール詳細

#### `main.py`: エントリーポイント
- CLI 引数解析（`argparse`）
- 全体フロー管理
- `--launch-chrome` が指定されると、Chrome をサブプロセスで起動
- 複数冊の連続処理に対応（`while True` ループ）

#### `kindle_capture.py`: ブラウザ操作・キャプチャ
- Playwright の CDP（Chrome DevTools Protocol）接続
- `read.amazon.*` を含む URL のタブを自動検出
- ArrowDown キーでページ遷移
- MD5 ハッシュ比較で画面の安定化待機（`_wait_for_page_stable`）
- `MAX_SAME_PAGES=3` で書籍終端判定

**重要な定数**:

| 定数 | 値 | 説明 |
|---|---|---|
| `MAX_SAME_PAGES` | `3` | 同一画面連続検出で終端とみなす回数 |
| `NEXT_PAGE_KEY` | `'ArrowDown'` | ページ送りキー |
| `DEFAULT_CDP_URL` | `'http://localhost:9222'` | Chrome CDP エンドポイント |

#### `pdf_maker.py`: PDF 生成
- `img2pdf.convert()` で PNG を再エンコードせず結合
- これにより macOS Live Text が高精度に動作

---

## 🔍 トラブルシューティング

### Chrome の起動に失敗する

```
エラー: "Failed to launch Chrome"
```

**対処方法**:
1. ポート 9222 が他のプロセスで使用されていないか確認
2. Chrome / Chromium がインストール済みか確認
3. `--chrome-user-data-dir` で別のディレクトリを指定してみる

### Playwright のインストール失敗

```
エラー: "playwright install chromium failed"
```

**対処方法**:
1. `uv run playwright install chromium` を再実行
2. ネットワーク接続を確認
3. Playwright ダウンロードディレクトリのキャッシュをクリア:
   ```bash
   rm -rf ~/.cache/ms-playwright  # macOS/Linux
   # Windows: del %APPDATA%\Local\ms-playwright
   ```

### テストが失敗する

```bash
# 失敗の詳細を表示
uv run pytest -vv

# 特定のテストのみ実行
uv run pytest tests/test_kindle_capture.py::test_capture -vv
```

### 品質チェックが失敗する

```bash
# ruff の問題を自動修正
uv run ruff check . --fix

# mypy エラーの詳細確認
uv run mypy main.py kindle_capture.py pdf_maker.py --show-error-codes

# カバレッジの詳細を確認
uv run pytest --cov=. --cov-report=term-missing
```

---

## 📦 依存関係

### 本体依存

```
img2pdf >= 0.6.0    # 高品質 PNG → PDF 変換
playwright >= 1.50.0 # ブラウザ自動化
```

### 開発依存

```
mypy >= 1.20.2           # 静的型チェック
pytest >= 9.0.3          # テストフレームワーク
pytest-asyncio >= 1.3.0  # 非同期テスト対応
pytest-cov >= 7.1.0      # カバレッジ計測
ruff >= 0.15.12          # Python リント
```

---

## 🔐 セキュリティと注意事項

### 利用範囲

本ツールは **個人的な学習や資料管理** を目的としています。

### 利用規約

- Amazon Kindle の利用規約を確認のうえ、自己責任でご利用ください
- 生成した PDF の再配布等は厳禁です

### Live Text について

- テキストのコピー・検索は macOS の「プレビュー」アプリ等で行ってください
- OS の機能により文字認識が行われます

---

## 💡 ベストプラクティス

### 日常的な開発ワークフロー

```bash
# 1. コードを編集
# ... (編集作業)

# 2. テストを実行
uv run pytest

# 3. 品質チェック
./check_quality.sh  # または check_quality.bat / .ps1

# 4. 変更をコミット
git add .
git commit -m "description"
```

### パフォーマンス最適化

```bash
# ページ遷移の待機時間を短く
uv run python main.py --launch-chrome --page-delay 0.5

# または長めに（ネットワークが遅い場合）
uv run python main.py --launch-chrome --page-delay 2.0
```

### デバッグ時

```bash
# 詳細なログを出力させる場合は
# main.py のログレベルを DEBUG に変更してから実行

uv run python main.py --launch-chrome --screenshots keep
# （終了後、./output/<書籍タイトル>/ で画像を確認）
```

---

## 📝 よくある質問（FAQ）

### Q: 複数の書籍を連続処理できますか？

**A**: はい。`uv run python main.py --launch-chrome` を実行すると、プログラムが書籍ごとに一時停止し、次の処理を待ちます（`input()` で）。

### Q: PDF のファイル名をカスタマイズできますか？

**A**: 現在は自動生成（書籍のタイトルから）です。必要に応じて `pdf_maker.py` を修正してください。

### Q: どのぐらいの時間がかかりますか？

**A**: 本の厚さにもよりますが、数百ページの本で 5～15 分程度が目安です。

### Q: Windows でも動作しますか？

**A**: はい。ただし Chrome の起動方法が異なる場合があります。トラブルがあれば `run_win.bat` / `run_win.ps1` を参照してください。

---

## 📞 サポート

問題が発生した場合：

1. README.md の「トラブルシューティング」を確認
2. テストを実行して環境が正常か確認
3. 品質チェック（`check_quality.sh` など）を実行
4. GitHub Issues で報告

---

## 📚 参考リンク

- [uv - Astral](https://astral.sh/uv/)
- [Playwright Python](https://playwright.dev/python/)
- [img2pdf](https://github.com/josch/img2pdf)
- [Amazon Kindle Cloud Reader](https://read.amazon.com)

---

**最終更新**: 2026-05-03

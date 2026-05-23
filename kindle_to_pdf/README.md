# Kindle to PDF

Kindle Cloud Reader で開いている本を自動でキャプチャし、高品質な画像 PDF を生成するツールです。

## 🌟 主な特徴

- **無劣化・最高画質**: `img2pdf` を採用。キャプチャした PNG 画像を再エンコード（圧縮）することなく PDF に結合するため、オリジナルの画質を完全に維持します。
- **macOS Live Text 最適化**: OCR を内蔵せず、生成した PDF は macOS の「テキスト認識表示 (Live Text)」と相性が良く、高精度なテキスト選択・コピーが可能です。
- **賢い終端検出**: ページのハッシュ値（MD5）を比較し、同じ画面が続いた場合に「書籍の終わり」と自動判定して停止します。
- **レンダリング安定待機**: ページ遷移後、画像のロードが完了して表示が安定するまで待機してからキャプチャします。
- **自動ブラウザ起動**: `--launch-chrome` オプションで、専用のクリーンなブラウザセッション（Chrome または Edge）を自動で立ち上げ、CDP 経由で接続します。

---

## 🛠 動作環境

- **OS**: macOS, Windows, Linux（macOS を想定した使い勝手の最適化あり）
- **Python**: 3.12 以上
- **パッケージマネージャー**: [uv](https://astral.sh/uv/) 推奨

---

## 🚀 セットアップ

付属のセットアップスクリプトを使うか、`uv` を利用した環境構築を推奨します。OS ごとに手順を分けて記載します。

### macOS / Linux

```bash
# リポジトリ直下で（実行権限がなければ chmod +x setup.sh）
./setup.sh

# または uv を使用する場合
uv sync
uv run playwright install chromium
```

### Windows (PowerShell)

```powershell
# 管理者として開かないでください（不要な権限を避けるため）
# リポジトリ直下で
.\setup_win.bat

# PowerShell を使って playwright を手動で入れる場合
uv sync
uv run playwright install chromium
```

---

## 📖 実行方法

以下は macOS / Windows の両方での代表的な実行例です。環境に合わせて使ってください。

### macOS / Linux

- 自動でブラウザを起動してキャプチャ（推奨）:

```bash
# 付属スクリプトで簡単起動（デフォルトは Chrome）
./run.sh

# あるいは uv 経由で明示的に起動
uv run python main.py --launch-chrome

# Microsoft Edge を使用する場合
uv run python main.py --launch-chrome --browser edge
```

- 既存のキャプチャ画像から PDF を生成する場合:

```bash
uv run python main.py --images-dir ./output/書籍タイトル
```

- 追加例（画像を残す・遅延を長めに）:

```bash
uv run python main.py --launch-chrome --screenshots keep --page-delay 2.0
```

### Windows (コマンドプロンプト / PowerShell)

- バッチファイルで起動（推奨）:

```
run_win.bat
```

- 直接 Python を呼ぶ場合:

```powershell
# PowerShell の例
uv run python main.py --launch-chrome

# 既存画像から PDF を作る
uv run python main.py --images-dir .\output\書籍タイトル
```

---

## ⚙️ オプション一覧（更新）

| オプション | 省略形 | デフォルト | 説明 |
|---|---|---:|---|
| `--output-dir` | `-o` | `./output` | 生成物の保存先 |
| `--browser` | なし | `chrome` | 使用するブラウザ（`chrome` または `edge`） |
| `--launch-chrome` | なし | なし | 専用のブラウザインスタンスを自動起動し、CDP で接続する |
| `--screenshots` | なし | `delete` | `delete`（画像を削除）または `keep`（画像を保持） |
| `--page-delay` | なし | `0.8` | ページ遷移後の最低待機秒数（秒） |
| `--images-dir DIR` | なし | なし | 指定した画像ディレクトリを入力として PDF を生成 |
| `--chrome-user-data-dir DIR` | なし | 一時フォルダ | `--launch-chrome` 使用時のユーザーデータディレクトリ |


注意: Windows のパスはバックスラッシュ（\）または PowerShell の場合はエスケープ済みパスを使用してください。

---

## 📂 ファイル構成

```text
kindle-to-pdf/
├── main.py              # エントリーポイント。引数処理と全体のフロー管理。
├── kindle_capture.py    # Playwright を使用したブラウザ操作・キャプチャ・終端判定。
├── pdf_maker.py         # img2pdf を使用した高品質な PDF 生成。
├── run.sh               # macOS / Linux 用の起動スクリプト（環境により uv 経由で起動）。
├── run_win.bat          # Windows 用の起動バッチ。
├── run_win.ps1          # Windows PowerShell 用の実行スクリプト。
├── check_quality.sh     # macOS / Linux 用の品質チェック スクリプト（ruff, mypy, coverage）。
├── check_quality.bat    # Windows 用の品質チェック バッチ（Command Prompt）。
├── check_quality.ps1    # Windows 用の品質チェック スクリプト（PowerShell）。
├── setup.sh             # macOS / Linux の環境構築スクリプト。
├── setup_win.bat        # Windows の環境構築バッチ。
├── pyproject.toml       # uv 用のプロジェクト定義。
└── README.md            # 本ドキュメント。
```

---

## ✅ 品質チェック

コードの品質を保証するため、以下のチェック (ruff, mypy, テストカバレッジ 100%) を実行できます。

### macOS / Linux

```bash
# 実行権限を付与（初回のみ）
chmod +x check_quality.sh

# 品質チェック実行
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

各スクリプトは以下を実行します：
- **ruff**: Python コードのリント チェック（スタイル違反、潜在的なバグを検出）
- **mypy**: 型チェック（型安全性を検証）
- **pytest**: テスト実行とカバレッジ確認（100% カバレッジが必須）

すべてのチェックが合格すれば、品質基準を満たしています。

---

## 📝 注意事項

- **私的利用の範囲内で**: 本ツールは個人的な学習や資料管理を目的としています。生成した PDF の再配布等は厳禁です。
- **自己責任で**: Amazon Kindle の利用規約を確認のうえ、自己責任でご利用ください。
- **Live Text について**: テキストのコピー・検索は macOS の「プレビュー」アプリ等で行ってください。OS の機能により文字認識が行われます。

必要ならば、README にスクリーンショットやトラブルシューティング（Chrome 起動時のポート競合、Playwright のインストール失敗時の対処）を追加できます。どの程度詳しく追加するか指示ください。

# Kindle to PDF

Kindle Cloud Reader で開いている本を自動でキャプチャし、高品質な画像 PDF を生成するツールです。

## 🌟 主な特徴

- **無劣化・最高画質**: `img2pdf` を採用。キャプチャした PNG 画像を再エンコード（圧縮）することなく PDF に結合するため、オリジナルの画質を完全に維持します。
- **macOS Live Text 最適化**: OCR を内蔵せず、生成した PDF は macOS の「テキスト認識表示 (Live Text)」と相性が良く、高精度なテキスト選択・コピーが可能です。
- **賢い終端検出**: ページのハッシュ値（MD5）を比較し、同じ画面が続いた場合に「書籍の終わり」と自動判定して停止します。
- **レンダリング安定待機**: ページ遷移後、画像のロードが完了して表示が安定するまで待機してからキャプチャします。
- **自動 Chrome 起動**: `--launch-chrome` オプションで、専用のクリーンな Chrome セッションを自動で立ち上げ、CDP 経由で接続します。

---

## 🛠 動作環境

- **OS**: macOS, Windows, Linux（macOS を想定した使い勝手の最適化あり）
- **Python**: 3.12 以上
- **パッケージマネージャー**: [uv](https://astral.sh/uv/) 推奨

---

## 🚀 セットアップ

付属のセットアップスクリプトを使うか、`uv` を利用した環境構築を推奨します。

### 付属スクリプトを使う（macOS 等）

```bash
# リポジトリ直下で
./setup.sh
```

### uv を使う場合

```bash
uv sync
uv run playwright install chromium
```

---

## 📖 使い方

1. (オプション) `--launch-chrome` で専用の Chrome を起動するか、既存の Chrome をデバッグモードで起動して接続します。
2. Chrome で Kindle Cloud Reader を開き、ログインして本を表示します。
3. 最初のページを表示した状態でターミナルに戻り、Enter などの操作でキャプチャを開始します。

### 例: 自動起動（推奨）

```bash
# デフォルト起動（Chrome を自動で開く）
./run.sh

# uv を使う場合
uv run python main.py --launch-chrome
```

### 画像から PDF を作る

既にキャプチャ済みの PNG から PDF を作る場合:

```bash
uv run python main.py --images-dir ./output/書籍タイトル
```

---

## ⚙️ オプション一覧

| オプション | デフォルト | 説明 |
|---|---:|---|
| `--output-dir`, `-o` | `./output` | 生成物の保存先 |
| `--launch-chrome` | なし | 専用の Chrome インスタンスを自動起動する |
| `--screenshots {delete,keep}` | `delete` | PNG 画像の扱い。`keep` で画像を output に残す |
| `--page-delay` | `0.8` | ページ遷移後の最低待機秒数 |
| `--images-dir DIR` | なし | 指定した画像ディレクトリを入力として PDF を生成 |
| `--chrome-user-data-dir` | 一時フォルダ | `--launch-chrome` 使用時のプロファイル保存先 |

---

## 📂 ファイル構成

```text
kindle-to-pdf/
├── main.py            # エントリーポイント。引数処理と全体のフロー管理。
├── kindle_capture.py  # Playwright を使用したブラウザ操作・キャプチャ・終端判定。
├── pdf_maker.py       # img2pdf を使用した高品質な PDF 生成。
├── run.sh             # macOS 用の起動スクリプト (推奨)。
├── setup.sh           # 環境構築スクリプト。
├── pyproject.toml     # uv 用のプロジェクト定義。
└── README.md          # 本ドキュメント。
```

---

## 📝 注意事項

- **私的利用の範囲内で**: 本ツールは個人的な学習や資料管理を目的としています。生成した PDF の再配布等は厳禁です。
- **自己責任で**: Amazon Kindle の利用規約を確認のうえ、自己責任でご利用ください。
- **Live Text について**: テキストのコピー・検索は macOS の「プレビュー」アプリ等で行ってください。OS の機能により文字認識が行われます。

# Kindle to PDF

Kindle Cloud Reader で開いている本を自動でキャプチャし、高品質な画像 PDF を生成するツールです。

## 🌟 主な特徴

- **無劣化・最高画質**: `img2pdf` を採用。キャプチャした PNG 画像を再エンコード（圧縮）することなく PDF に結合するため、オリジナルの画質を完全に維持します。
- **macOS Live Text 最適化**: OCR 機能を内蔵しない代わりに、生成された PDF は macOS 標準の「テキスト認識表示 (Live Text)」に最適化されています。プレビュー等で開くだけで、極めて高精度なテキスト選択・コピーが可能です。
- **賢い終端検出**: ページのハッシュ値（MD5）を比較し、同じ画面が続いた場合に「書籍の終わり」と自動判定して停止します。
- **レンダリング安定待機**: ページ遷移後、画像のロードが完了して表示が安定するまで自動的に待機してからキャプチャします。
- **自動 Chrome 起動**: `--launch-chrome` オプションにより、専用のクリーンなブラウザセッションを自動で立ち上げ、リモートデバッグモードで接続します。

---

## 🛠 動作環境

- **OS**: macOS (M1/M2/M3 シリーズ推奨), Windows, Linux
- **Python**: 3.11 以上
- **ブラウザ**: Google Chrome

---

## 🚀 セットアップ

macOS の場合は、提供されている `setup.sh` を実行することで、Python ライブラリと Playwright のブラウザを一括でインストールできます。

```bash
cd kindle_to_notebooklm
bash setup.sh
```

**手動でインストールする場合:**
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 📖 使い方

### 方法 A: Chrome を自動起動する (推奨)

この方法では、既存の Chrome 設定に影響を与えない専用のウィンドウが起動します。

```bash
python main.py --launch-chrome
```

1. 起動した Chrome で [Kindle Cloud Reader](https://read.amazon.co.jp) にログインし、本を開きます。
2. 最初のページを表示した状態で、ターミナルに戻り **Enter キー** を押すとキャプチャが開始されます。

### 方法 B: 既存の画像から PDF を生成する

すでに画像（`page_0001.png` など）が揃っているディレクトリから PDF のみを作成する場合に使用します。

```bash
python main.py --images-dir ./output/書籍タイトル
```

---

## ⚙️ オプション一覧

| オプション | デフォルト | 説明 |
|---|---|---|
| `--output-dir`, `-o` | `./output` | 生成物の保存先 |
| `--launch-chrome` | なし | 専用の Chrome インスタンスを自動起動する |
| `--screenshots {delete,keep}` | `delete` | PNG 画像の扱い。 `keep` を指定すると `output/書籍名/` に画像を残します。 |
| `--page-delay` | `0.8` | ページ遷移後の最低待機秒数。通信が遅い場合は長めに設定します。 |
| `--images-dir DIR` | なし | 指定した画像ディレクトリを入力として PDF を生成します。 |
| `--chrome-user-data-dir` | 一時フォルダ | `--launch-chrome` 使用時のプロファイル保存先。 |

---

## 📂 ファイル構成

```text
kindle_to_notebooklm/
├── main.py            # エントリーポイント。引数処理と全体のフロー管理。
├── kindle_capture.py  # Playwright を使用したブラウザ操作・キャプチャ・終端判定。
├── pdf_maker.py       # img2pdf を使用した高品質な PDF 生成。
├── setup.sh           # macOS 用の環境構築スクリプト。
├── requirements.txt   # Python 依存ライブラリ一覧。
├── .tool-versions     # asdf 等のバージョン管理用ファイル。
└── README.md          # 本ドキュメント。
```

---

## 📝 注意事項

- **私的利用の範囲内で**: 本ツールは著作権法第30条（私的使用のための複製）に基づき、個人的な学習や資料管理を目的として作成されています。生成した PDF の再配布等は厳禁です。
- **自己責任で**: Amazon Kindle の利用規約を確認の上、自己責任でご利用ください。
- **Live Text について**: テキストのコピー・検索を行いたい場合は、生成された PDF を macOS の「プレビュー」アプリで開いてください。OS の機能により自動的に文字が認識されます。

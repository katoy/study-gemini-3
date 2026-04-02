# Kindle App to PDF

Mac の Kindle デスクトップアプリで開いている本を自動でキャプチャし、高品質な画像 PDF を生成するツールです。

## 主な特徴

- **無劣化・最高画質**: `img2pdf` を採用。キャプチャした PNG 画像を再エンコードなく PDF に結合します。
- **macOS Live Text 最適化**: 生成した PDF は macOS 標準の「テキスト認識表示 (Live Text)」に最適化されています。
- **賢い終端検出**: ページのハッシュ値（MD5）を比較し、同じ画面が続いた場合に「書籍の終わり」と自動判定して停止します。
- **ネイティブアプリ対応**: Playwright 不要。`osascript` + `screencapture` のみを使用します。

---

## 動作環境

- **OS**: macOS
- **Python**: 3.11 以上
- **アプリ**: Mac 用 Kindle アプリ（App Store から入手）

---

## セットアップ

```bash
cd kindle_app_to_pdf
bash setup.sh
```

**手動でインストールする場合:**
```bash
pip install -r requirements.txt
```

---

## 使い方

1. Kindle アプリを起動し、キャプチャしたい本を開く
2. **最初のページ**を表示した状態でターミナルに戻る
3. 以下のコマンドを実行:

```bash
python main.py
```

4. ターミナルのプロンプトで **Enter キー** を押すとキャプチャ開始
5. 完了すると `./output/` に PDF が生成される

---

## オプション一覧

| オプション | デフォルト | 説明 |
|---|---|---|
| `--output-dir`, `-o` | `./output` | 生成物の保存先 |
| `--screenshots {delete,keep}` | `delete` | PNG 画像の扱い。`keep` で画像を残す |
| `--page-delay` | `1.5` | ページ送り後の待機秒数。描画が遅い場合は長めに設定 |
| `--images-dir DIR` | なし | 指定した画像ディレクトリから PDF のみ生成 |

---

## PDF の分割

生成した PDF が大きすぎる場合（例: 200 MB 超）は `split_pdf.py` で分割できます。

```bash
python split_pdf.py output/Kindle.pdf --max-mb 200 --output-dir output
```

| オプション | デフォルト | 説明 |
|---|---|---|
| `--max-mb` | `200` | 分割後の最大ファイルサイズ（MB） |
| `--output-dir`, `-o` | `./output` | 分割ファイルの保存先 |

実行例:

```
入力: Kindle.pdf  (247.6 MB, 404 ページ)
  → Kindle_part01.pdf  (ページ 1〜322, 199.2 MB)
  → Kindle_part02.pdf  (ページ 323〜404, 48.4 MB)

合計 2 ファイルに分割しました。
```

---

## ファイル構成

```
kindle_app_to_pdf/
├── main.py            # エントリーポイント。引数処理と全体のフロー管理。
├── kindle_capture.py  # osascript + screencapture によるキャプチャ・終端判定。
├── pdf_maker.py       # img2pdf を使用した高品質な PDF 生成。
├── split_pdf.py       # 生成した PDF を指定サイズ以下に分割するスクリプト。
├── setup.sh           # macOS 用の環境構築スクリプト。
├── requirements.txt   # Python 依存ライブラリ一覧。
└── README.md          # 本ドキュメント。
```

---

## 注意事項

- **私的利用の範囲内で**: 本ツールは著作権法第30条（私的使用のための複製）に基づき、個人的な学習や資料管理を目的として作成されています。生成した PDF の再配布等は厳禁です。
- **自己責任で**: Amazon Kindle の利用規約を確認の上、自己責任でご利用ください。
- **アクセシビリティ権限**: `osascript` で他アプリを操作するため、システム環境設定の「プライバシーとセキュリティ」→「アクセシビリティ」でターミナル（または使用するターミナルアプリ）に権限を付与してください。

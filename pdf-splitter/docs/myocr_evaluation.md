# MyOCR 利用検討レポート（2026-10-11）

## 結論（縦書き検証を含めた最終判断）

**OCR エンジンには NDLOCR-Lite（ndl-lab/ndlocr-lite v1.3.1）を推奨する。** 詳細は「縦書き対応エンジンの追加検証」を参照。

- 縦書き・横書きの両方に 1 つのエンジンで対応でき、句読点も残る（縦書き CER 4.8%、横書き 2.4%）。CPU で 1 ページ約 1 秒と最速。
- PDF を直接入力でき、元の画像を保ったまま文字層を埋め込んだ検索可能 PDF を出力できる（ocrmypdf の置き換えになる）。
- ライセンスは CC BY 4.0（同梱モデルは DINOv3 License も適用。商用利用可、再配布時はライセンス同梱が必要）。

以下は最初の比較（横書きのみ）時点の結論。

**MyOCR（robbyzhaox/myocr）は採用しない。** 横書きでは RapidOCR（PP-OCRv6、`lang_type=japan`）が最も正確だったが、縦書きでは句読点がほぼ消えるため不採用とした。

- 標準の MyOCR は日本語の CER が 56.9% で、実用にならない。
- 認識モデルを PP-OCRv6 に差し替えると CER 1.5% まで改善する。ただし、同じ認識モデルを使う RapidOCR（CER 0.3%）より精度も速度も劣る。
- MyOCR に同梱されているモデルは、3 つとも PaddleOCR のモデルを paddle2onnx で ONNX 化したもの（入出力名が `p2o.*`）。MyOCR を経由する利点はない。

## 調査結果（MyOCR の構造）

| 項目 | 内容 |
|---|---|
| 構成 | 検出 `dbnet++.onnx` → 向き判定 `cls.onnx`（0°/180°）→ 認識 `rec.onnx`（CRNN-CTC） |
| 認識モデル | 出力 6625 クラス = 中国語版 PP-OCR の辞書。`alphabetChinese` は簡体字中心でひらがなを含まない |
| 前処理・デコード | 高さ 48、`(x/255-0.5)/0.5`、blank=0、末尾に空白文字。PP-OCR と同じ |
| 縦書き | 非対応 |
| 検索可能 PDF 出力 | なし（テキストと矩形のみ） |
| 保守状況 | v0.1.1（2025-05）以降は依存ライブラリの更新のみ。モデルは Google Drive から手作業で入手 |
| 依存 | `numpy==2.2.6`、`onnxruntime==1.21.0` などバージョン固定が多い。Python 3.11–3.12 |

## ベンチマーク

- サンプル: Kindle_13（横書き、Mac 版 Kindle のスクリーンショット）から 10 ページ。うち 5 ページは手作業で正解テキストを作成。
- 環境: macOS、CPU のみ。
- 実行方法: 下記「再現手順」。

| エンジン | CER | 和文間空白 | 章検出 | 章検出 (NFKC 後) | 誤検出 | 秒/ページ |
|---|---:|---:|---:|---:|---:|---:|
| Tesseract（現行、`jpn+eng`） | 9.1% | 18 | 2/5 | 2/5 | 0 | 0.97 |
| MyOCR 標準 | 56.9% | 8 | 3/5 | 3/5 | 0 | 2.39 |
| MyOCR + PP-OCRv6 認識モデル | 1.5% | 0 | 4/5 | 5/5 | 0 | 2.32 |
| **RapidOCR（PP-OCRv6）** | **0.3%** | 1 | **5/5** | 5/5 | 0 | 1.65 |

- **CER**: NFKC 正規化と空白除去の後の文字誤り率。タイトルバーの「Kindle」行は除く。
- **和文間空白**: 和文文字にはさまれた空白の数。現行パイプラインで目次の正規表現が一致しない原因になっている。
- **章検出**: `scripts/pdf_chapter_pipeline.py` の `detect_chapters_by_keywords` で、章見出しのある 5 ページのうち何ページを検出できたか。

### 各エンジンの傾向

- **Tesseract**: 本文の CER は 9.1% だが、和文の間に空白が入る。装飾された見出し（章の扉ページ）はほぼ読めない（例: 「第 1 章」→「ノェノマ =z」）。
- **MyOCR 標準**: 和文の大半が欠落する（例: 「Obsidian って、結局なんやの？」→「Obsidian、局の？」）。
- **MyOCR + PP-OCRv6**: 本文はほぼ正確。一方で、次の誤りが出る。
  - 「1」「2」のような短い行の取りこぼし（信頼度 0.5 未満を捨てる `OCRResult.build` の仕様と、旧世代の検出モデルが原因）
  - 1 行がまるごと崩れる（「ひとつずつ、見ていきます。」→「上半12首CよC？口」。旧世代の向き判定モデルが 180° 回転と誤判定したと見られる）
- **RapidOCR**: 最も正確で最も速い。誤りは装飾文字の分割（「PROLOGUE」→「P / ROLOG U」）程度。

## パイプラインへの示唆（エンジン選定とは別に）

- `detect_chapters_by_keywords` の `第\s*[0-9…]+\s*章` は半角数字にしか一致しない。PP-OCR 系は「第１章」のように全角数字を出すことがあり、NFKC 正規化をしないと章を取りこぼす（MyOCR + PP-OCRv6 の 4/5 → 5/5）。テキスト抽出の直後に `unicodedata.normalize("NFKC", ...)` を入れるべき。
- RapidOCR は文字列と座標しか返さない。検索可能 PDF を作るには文字層の合成（hOCR を経由して ocrmypdf に渡すか、pikepdf で直接書き込む）が必要。これは別計画で扱う。

## 縦書きでの RapidOCR 検証（2026-10-11 追記）

- サンプル: Kindle_4（『走れメロス』、ルビあり）5 ページ、Kindle_16（縦書きの実用書。太字・縦中の英単語あり）5 ページ。うち 3 ページ（k4_p008、k4_p015、k16_p040）は正解テキストを手作業で作成。正解テキストにルビは含めない。
- `rapidocr_engine.py --vertical`: 縦長の検出枠を本文の列とみなし、右から左へ並べる。列幅の 0.75 倍未満の細い枠はルビとして除外する。

| エンジン | CER | CER（句読点・括弧を除く） | 和文間空白 | 秒/ページ |
|---|---:|---:|---:|---:|
| Tesseract `jpn+eng` | 95.9% | 107.6% | 4 | 1.90 |
| Tesseract `jpn_vert+jpn+eng` | 21.5% | 20.8% | 1986 | 2.98 |
| RapidOCR（並べ替えなし） | 85.0% | 87.6% | 1 | 1.76 |
| **RapidOCR `--vertical`** | **11.6%** | **2.9%** | 1 | 2.02 |

- RapidOCR は縦長の列を 90° 回転して認識するため、**縦書きの本文の文字自体はほぼ正確に読める**（句読点を除いた CER は 2.9%）。ただし読み順は上から下に並ぶので、`--vertical` のような右→左の並べ替えが必須（しないと CER は 85.0%）。
- 誤りの大半は**句読点・括弧・小書き文字の欠落**（欠落・置換 186 文字中、「、」61・「。」47・「「」22・「」」15・「っ」17）。縦組みでは句読点や小書き文字がマスの右上に寄るため、回転した行画像の中で位置がずれて落ちると見られる。全文検索や章見出しの検出への影響は小さいが、テキストとして書き出す用途では句読点がほぼ消える。
- 縦中の英単語（Obsidian、YouTube）は正しく読める（「O」が「〇」になる誤りはある）。
- Tesseract `jpn_vert` は和文の間に空白が大量に入り（1,986 個）、Kindle_16 のような小さい文字や太字の混在したページでは崩れる。
- 試して不採用にした方式: 列を 1 文字ずつのマスに切って横一列に並べ直し、正立のまま認識する方式。句読点や「っ」は読めるようになるが、文字送りの推定が 1〜2 文字ずれると列全体が崩れ、総合的には回転方式より悪かった。

### 縦書き対応の示唆

- パイプラインに組み込むときは、ページが縦書きかどうかを判定して読み順を切り替える必要がある。判定は検出枠の縦長・横長の比率で十分できる見込み（本文の枠の大半が縦長なら縦書き）。
- 句読点の欠落を許容できない用途なら、縦書きページだけ別エンジン（YomiToku・NDLOCR-Lite など縦書きに特化したもの）を併用する検討が必要。

## 縦書き対応エンジンの追加検証（2026-10-11 追記）

RapidOCR の句読点欠落は許容できないため、縦書きに対応した YomiToku（v0.15.0）と NDLOCR-Lite（v1.3.1）を同じサンプルで比較した。

### 縦書き（正解 3 ページ）

| エンジン | CER | 句読点の欠落 | 秒/ページ |
|---|---:|---:|---:|
| RapidOCR `--vertical` | 11.6% | 149 | 2.02 |
| **NDLOCR-Lite** | 4.8% | **5** | **1.07** |
| YomiToku（通常） | **1.7%** | 0 | 7.30 |
| YomiToku `--lite` | 4.8% | 0 | 4.39 |

- NDLOCR-Lite の誤りの多くは「……」の取りこぼし（NFKC 後の「.」21 個）。『走れメロス』の 2 ページでは CER 0.2〜0.5% とほぼ完全で、ルビの除外と右→左の読み順も自前で処理する。
- YomiToku は最も正確だが、CPU では 1 ページ 7 秒以上かかる（500 ページの本で約 1 時間）。

### 横書き（Kindle_13、正解 5 ページ）

| エンジン | CER | 章検出 | 秒/ページ |
|---|---:|---:|---:|
| RapidOCR | 0.3% | 5/5 | 1.65 |
| NDLOCR-Lite | 2.4% | 4/5 | 1.00 |
| YomiToku（通常） | 1.0% | 2/5 | 5.91 |
| YomiToku `--lite` | 2.1% | 2/5 | 5.28 |

- YomiToku は「CHAPTER 1」のような装飾された章扉ページを図として扱い、本文テキストから落とす。章分割が目的のこのパイプラインには不向き。
- NDLOCR-Lite の取りこぼし 1 件（p019）は OCR ではなくパイプラインの正規表現の問題。「第1章Obsidian…」のように「章」の直後に空白がないと `第\s*[0-9…]+\s*章(?:\s+|$)` に一致しない。

### NDLOCR-Lite の PDF 入出力

- `ocr.py --sourcepdf <入力.pdf> --pdf-output <出力.pdf> --output <dir>` で、PDF からページ画像を取り出して OCR し、文字層付きの PDF を書き出せる。
- Kindle_4（縦書き 25 ページ、14.4MB）で確認した結果:
  - 処理時間は約 29 秒（約 1.2 秒/ページ）。
  - 出力は 14.5MB。ページ画像は元と同じ 1860×1540 で保持される。
  - pypdf の `extract_text()` で、縦書きの読み順どおりのテキストが取れる。
- ページごとの txt・json・xml も同時に出力される。

### 選定理由

| 観点 | NDLOCR-Lite | YomiToku | RapidOCR |
|---|---|---|---|
| 縦書きの句読点 | ○ | ◎ | ×（ほぼ消える） |
| 横書きの精度 | ○ | ◎ | ◎ |
| 章扉ページ | ○ | ×（図として除外） | ◎ |
| 速度（CPU） | ◎ 約 1 秒 | △ 5〜7 秒 | ○ 約 2 秒 |
| 検索可能 PDF | ◎ 標準機能 | ○ `-f pdf` | × 自作が必要 |
| ライセンス | CC BY 4.0（＋DINOv3） | CC BY-NC-SA 4.0（商用は別契約） | Apache-2.0 |
| 導入 | git clone ＋ 固定版の requirements（`uv tool install` 可） | PyPI（torch 依存で重い） | PyPI |

## 制約・未検証事項

- 横書きのサンプルは 1 冊のみ。
- 目次ページを含む本ではないため、`parse_toc_entries` による目次解析は未評価。
- 正解テキストは横書き 5 ページ（約 2,000 文字）、縦書き 3 ページ（約 1,600 文字）のみ。

## 再現手順

```bash
cd pdf-splitter/bench
# MyOCR のモデルを ~/.MyOCR/models/ に配置する（Google Drive: 1RXppgx4XA_pBX9Ll4HFgWyhECh5JtHnY）
uvx gdown --folder https://drive.google.com/drive/folders/1RXppgx4XA_pBX9Ll4HFgWyhECh5JtHnY -O ~/.MyOCR/models
# 差し替え用の PP-OCRv6 認識モデル（RapidOCR の初回実行で自動ダウンロードされたものをコピー）
#   → ~/.MyOCR/models/PP-OCRv6_rec_small.onnx

uv run --python 3.12 --script engines/tesseract_engine.py samples/*.png --out results/tesseract
uv run --python 3.12 --script engines/myocr_engine.py samples/*.png --out results/myocr_stock
uv run --python 3.12 --script engines/myocr_engine.py samples/*.png --out results/myocr_ppocrv6 \
  --rec-model ~/.MyOCR/models/PP-OCRv6_rec_small.onnx
uv run --python 3.12 --script engines/rapidocr_engine.py samples/*.png --out results/rapidocr_ppocrv6
uv run --python 3.12 --script compare.py

# 縦書き
uv run --python 3.12 --script engines/tesseract_engine.py samples_vert/*.png --out results_vert/tesseract_jpn_vert \
  --lang jpn_vert+jpn+eng
uv run --python 3.12 --script engines/rapidocr_engine.py samples_vert/*.png --out results_vert/rapidocr_vertical --vertical
uv run --python 3.12 --script compare.py --samples samples_vert --results results_vert

# NDLOCR-Lite（事前に git clone --depth 1 --branch 1.3.1 https://github.com/ndl-lab/ndlocr-lite <DIR>）
uv run --python 3.12 --script engines/ndlocr_engine.py samples_vert --out results_vert/ndlocr_lite --ndlocr-dir <DIR>
# YomiToku（標準入力を閉じないと停止することがある）
uv run --python 3.12 --script engines/yomitoku_engine.py samples_vert/*.png --out results_vert/yomitoku < /dev/null
uv run --python 3.12 --script engines/yomitoku_engine.py samples_vert/*.png --out results_vert/yomitoku_lite --lite < /dev/null
```

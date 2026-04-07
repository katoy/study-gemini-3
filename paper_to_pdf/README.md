# paper_to_pdf

スマホで撮影した書籍の見開きページを AI 補正してクリーンな PDF に変換する CLI ツール。

---

## 目次

1. [主な機能](#主な機能)
2. [アーキテクチャ](#アーキテクチャ)
3. [セットアップ](#セットアップ)
4. [使い方](#使い方)
5. [オプション一覧](#オプション一覧)
6. [AI 補正バックエンド](#ai-補正バックエンド)
7. [パフォーマンス目安](#パフォーマンス目安)
8. [補正アルゴリズム](#補正アルゴリズム)
9. [デバッグ・評価ツール](#デバッグ評価ツール)
10. [撮影のヒント](#撮影のヒント)
11. [対応画像フォーマット](#対応画像フォーマット)

---

## 主な機能

- **高精度ページ境界検出:** 白比率プロファイル + Canny エッジ密度急落で籐・机などの背景テクスチャを確実に除去。台形に傾いた書籍も正確に検出。
- **Portrait 見開き対応:** カメラを 90° 回転して撮影した見開き（上下配置）を自動検出して水平分割。
- **ページ順序自動判定:** 縦書き/横書きの形態解析とページ番号比較の 2 シグナルを統合して右開き/左開きを自動推定。
- **湾曲補正 (DewarpNet / Polynomial / DocTR):**
  - `dewarpnet`: 深層学習による 3D 湾曲補正。
  - `polynomial`: 3 次多項式で非対称な膨らみを平坦化。
  - `doctr`: AI Transformer ベースの文書補正。
- **AI 超解像 & 復元補正:** Real-ESRGAN / Swin2SR による鮮明化、DocRes による AI 影・裏写り除去。
- **ドキュメント・クリーニング:** 適応型白色化で紙面を純白に。裏写り・影を除去。
- **傾き補正 (Deskew):** テキスト行を 0.1° 単位で検出して水平補正。
- **メモリ効率:** ストリーミング方式で数百枚でも安定した PDF 生成。

---

## アーキテクチャ

処理はパイプライン形式で実行されます。

```
入力画像
  └─ DetectionStep    ページ境界検出・見開き分割・透視変換
  └─ DewarpStep       湾曲補正（AI / 多項式 / DocTR）
  └─ EnhancementStep  AI 超解像・復元補正
  └─ PostProcessStep  影除去・傾き補正・サイズ正規化
  └─ QualityCheckStep 品質評価（文字見切れ / 余分領域 / 歪み）
       └─ PDF 出力
```

### ディレクトリ構成

| パス | 役割 |
|------|------|
| `core/config.py` | 設定データクラス (`ProcessingConfig`) |
| `core/pipeline.py` | パイプライン制御 |
| `page_detector.py` | ページ境界検出・透視変換・見開き分割のコアロジック |
| `steps/detection.py` | DetectionStep — 検出・分割 |
| `steps/dewarp.py` | DewarpStep — 湾曲補正 |
| `steps/enhancement.py` | EnhancementStep — AI 超解像 |
| `steps/postprocess.py` | PostProcessStep — 後処理 |
| `steps/quality_check.py` | QualityCheckStep — 品質評価 |
| `utils/` | デバイス選択・画像 I/O・モデルパス管理 |

---

## セットアップ

```bash
cd paper_to_pdf
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **M1 Mac:** PyTorch は MPS（Metal）で GPU 加速されます。  
> **AI 補正を使用する場合:** 各バックエンドの追加パッケージが必要です（[AI 補正バックエンド](#ai-補正バックエンド)参照）。

---

## 使い方

```bash
python main.py <入力フォルダ> <出力PDF> [オプション]
```

### 実行例

```bash
# 基本（見開き自動検出 + 分割 + DewarpNet 補正）
python main.py ./samples out.pdf

# AI 超解像を追加（Real-ESRGAN x2）
python main.py ./samples out.pdf --ai-enhance --ai-backend realesrgan --ai-scale 2

# 漫画（右開き・グレースケール）
python main.py ./manga out.pdf --book-type manga

# 検出・分割結果のみを PDF に出力（品質確認用）
python main.py ./samples out.pdf --detect-only

# ページ境界検出のみ確認（分割なし）
python main.py ./samples out.pdf --detect-only --no-split

# 詳細ログ出力
python main.py ./samples out.pdf --verbose
```

---

## オプション一覧

| オプション | 説明 | デフォルト |
|------------|------|------------|
| `--book-type` | `auto` / `jp_vert` / `jp_horiz` / `en` / `manga` | `auto` |
| `--dewarp-mode` | `dewarpnet` / `polynomial` / `doctr` / `none` | `dewarpnet` |
| `--sensitivity` | 境界検出感度 `low` / `medium` / `high` / `ai` | `medium` |
| `--ai-enhance` | AI 超解像・復元補正を有効化 | 無効 |
| `--ai-backend` | `realesrgan` / `swin2sr` / `docres` | `realesrgan` |
| `--ai-scale` | 超解像倍率 `1`（復元のみ）/ `2` / `4` | `2` |
| `--output-size` | `A4` / `A5` / `B5` / `Letter` | `A4` |
| `--grayscale` | グレースケール出力 | 無効 |
| `--shadow-strength` | 影・裏写り除去強度 `0.0`〜`1.0` | `1.0` |
| `--no-split` | 見開き分割を行わない | — |
| `--no-orient` | 向き自動補正を行わない | — |
| `--no-border` | 黒縁除去を行わない | — |
| `--detect-only` | 検出・分割のみ行い後処理なしで PDF 出力（確認用） | — |
| `--show-clip-area` | `--detect-only` と併用。分割線と各ページ領域ラベル（RIGHT/LEFT）を元画像上に描画して確認用 PDF を出力 | — |
| `--verbose`, `-v` | 詳細ログ出力 | — |

### 推奨設定

| 目的 | 推奨オプション |
|------|----------------|
| 速度重視（プレビュー） | `--dewarp-mode polynomial` |
| 品質重視（最終出力） | `--dewarp-mode dewarpnet --ai-enhance --ai-backend realesrgan --ai-scale 2` |
| 影・裏写りが強い | `--ai-enhance --ai-backend docres --ai-scale 1` |
| 検出品質の確認 | `--detect-only` または `--detect-only --no-split` |

---

## AI 補正バックエンド

### Real-ESRGAN（推奨）
ノイズ除去 + 超解像。書籍スキャンに最適化。

```bash
pip install realesrgan basicsr
```

モデルは初回実行時に自動ダウンロード（`~/.cache/paper_to_pdf/`）。

### Swin2SR（HuggingFace）
Swin Transformer V2 ベースの超解像。

```bash
pip install transformers accelerate
```

HuggingFace Hub から自動ダウンロード。認証トークン未設定時は速度制限を受ける場合があります。

```bash
huggingface-cli login   # 一度だけ実行（推奨）
# または
export HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxx"
```

### DocRes（AI 影・裏写り除去）
AI による高精度な影・裏写り除去。`--ai-scale 1` で超解像なし復元専用として動作。

```bash
pip install transformers
```

### DewarpNet（`--dewarp-mode dewarpnet` 使用時）
湾曲補正 AI モデル。PyTorch 必須。未ダウンロード時は polynomial に自動フォールバック。

---

## パフォーマンス目安

> A4 @ 300 DPI の見開き 1 枚あたりの目安（環境により大きく異なります）。

### 湾曲補正モード

| モード | CPU | M1 Mac (MPS) |
|--------|-----|--------------|
| `none` | < 0.1 s | < 0.1 s |
| `polynomial` | 0.1〜0.5 s | 0.1〜0.5 s |
| `dewarpnet` | 1〜3 s | 0.5〜1.5 s |

### AI 超解像・復元

| バックエンド | スケール | CPU | M1 Mac (MPS) | NVIDIA (CUDA) |
|--------------|----------|-----|--------------|----------------|
| `realesrgan` | ×2 | 15〜40 s | 3〜8 s | 1〜3 s |
| `realesrgan` | ×4 | 40〜120 s | 8〜25 s | 2〜8 s |
| `swin2sr` | ×2 | 数分 | 30〜90 s | 10〜30 s |
| `docres` | ×1 | 8〜20 s | 2〜5 s | 1〜2 s |

---

## 補正アルゴリズム

### ページ境界検出

複数の検出手法を優先順位付きで試行し、最初に有効な結果を採用します。

1. **edge_and_profile** — 白比率プロファイル（ページ内部領域の特定）+ Canny エッジ密度の急落（背景→ページの物理境界）を組み合わせ、左右端 10% バンドで下辺を独立検出して台形に対応。
2. **white_profile** — 行/列の白ピクセル比率から矩形境界を推定。
3. **book_region** — 局所標準偏差でテクスチャ量を計算し、低テクスチャ OR 高輝度領域をモルフォロジー処理で書籍領域として検出。
4. **adaptive_thresh** — 適応的二値化による輪郭検出（暗い背景向け）。
5. **brightness** — 大津法による輝度ベース検出。
6. **canny** — Canny エッジ + 輪郭検出（低コントラスト向け）。
7. **saturation** — HSV 彩度ベース検出（テクスチャ背景向け）。

透視変換後は `trim_page_border` で外縁を 2 段階除去（黒縁 → 白比率 < 25% の背景テクスチャ）。

### 綴じ目検出（`find_center_seam`）

見開き画像から左右ページの分割位置を求めます。

縦方向のブラー後、列ごとの平均輝度プロファイルに対して**横方向の重い Gaussian スムージング**（sigma ≈ 画像幅 / 80）を適用することで、テキスト列間の細い隙間（高周波成分）を除去し、製本部の広い影（低周波成分）だけを抽出します。これにより、テキスト列の間隔を誤って綴じ目と判定するケースを防ぎます。中心から離れるほど小さなペナルティを加え、極端に端に寄った位置を抑制します。

### Portrait 見開き検出

カメラを 90° 回転して撮影した見開き（Portrait フレームに上下配置）を `center_seam_confidence` スコアで検出し、水平分割 + 90°CW 回転で 2 ページに変換します。

### 湾曲補正

DewarpNet（深層学習）または 3 次多項式メッシュフィッティングでページの膨らみを平坦化。BM 出力が縮退した場合は polynomial に自動フォールバック。

### ドキュメント・クリーニング

エリアごとの紙面輝度を推定する適応型白色化で文字を鮮明に残しつつ裏写り・影・照明ムラを除去。

---

## デバッグ・評価ツール

### `check_book_detection.py` — 書籍境界検出の評価

```bash
python check_book_detection.py <入力フォルダ> [--out-dir 可視化出力先]
```

全検出手法を個別に試行し、面積比・矩形度・白比率を定量評価して可視化画像を出力します。

### `check_seam_detection.py` — 綴じ目検出の評価

```bash
python check_seam_detection.py <入力フォルダ> [--out-dir 可視化出力先]
```

見開き画像の水平/垂直綴じ目検出結果を可視化します。

### `compare_pages.py` — ページ比較

```bash
python compare_pages.py <画像A> <画像B>
```

2 枚のページ画像を並べて比較表示します。

---

## 撮影のヒント

1. **背景を工夫する:** 黒い布を敷くとページ境界をより正確に検出できます。
2. **照明を均一に:** 柔らかな間接照明の方が影除去が効果的です。
3. **フラットに置く:** 可能な限り本を平らに開いて撮影すると湾曲補正精度が向上します。

---

## 対応画像フォーマット

JPEG, PNG, HEIC, BMP, TIFF, TIF

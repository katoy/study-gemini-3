# paper_to_pdf (Advanced CLI Edition)

スマホで撮影した書籍の見開きページを、AI 級の高精度な補正を施してクリーンな PDF に変換するコマンドライン・ツールです。
最新のリファクタリングにより、処理工程がパイプライン化され、拡張性と保守性が大幅に向上しました。

---

## 目次

1. [主な機能](#主な機能)
2. [アーキテクチャ](#アーキテクチャ)
3. [セットアップ](#セットアップ)
4. [使い方](#使い方)
    - [実行例](#実行例)
    - [オプション一覧](#オプション一覧)
5. [補正アルゴリズムについて](#補正アルゴリズムについて)
6. [より綺麗にスキャンするためのヒント](#より綺麗にスキャンするためのヒント)
7. [対応画像フォーマット](#対応画像フォーマット)

---

## 主な機能

- **インテリジェント自動判定:** スマホを縦に持って撮った「横向きの見開き」も自動で回転・分割。
- **高度な湾曲補正 (DewarpNet / Polynomial):** 
    - `dewarpnet`: 深層学習を用いた強力な 3D 湾曲補正。
    - `polynomial`: 3次多項式を用いてページの非対称な膨らみを精密に平坦化。
- **AI 超解像補正 (Upscaling):** Real-ESRGAN や Swin2SR を用いた、文字や図版の鮮明化。
- **強力なドキュメント・クリーン:** 背景（紙の色）を純白にし、裏写り（ブリードスルー）や影を完全に排除。
- **精密な傾き補正 (Deskew):** テキスト行を 0.1度単位で検出し、完全に水平な状態に回転補正。
- **メモリ効率重視:** ストリーミング方式により、数百枚の画像でも安定して PDF を生成。

## アーキテクチャ

処理工程が独立したステップとして分離されており、パイプライン形式で実行されます。

- **`core/`**: 設定管理 (`config.py`) とパイプライン制御 (`pipeline.py`)。
- **`steps/`**: 各処理フェーズの独立した実装。
    - `DetectionStep`: ページ境界検出と見開き分割。
    - `DewarpStep`: 湾曲補正（AI または多項式）。
    - `EnhancementStep`: AI による超解像補正。
    - `PostProcessStep`: 影除去、傾き・向き補正、サイズ正規化。
- **`utils/`**: デバイス選択 (`device.py`) や画像 I/O (`image.py`) の共通ユーティリティ。

## セットアップ

### 1. Python 仮想環境を作成

```bash
cd paper_to_pdf
python3 -m venv .venv
source .venv/bin/activate
```

### 2. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

> **M1 Mac の場合:** PyTorch は MPS（Metal）で GPU 加速されます。
> **AI 補正を使用する場合:** `pip install realesrgan basicsr` (Real-ESRGAN) または `pip install transformers accelerate` (Swin2SR) が必要です。

## 使い方

```bash
python main.py [入力フォルダ] [出力PDF] [オプション]
```

### 実行例

```bash
# 漫画の自炊（右開き、グレースケール、強力な湾曲補正）
python main.py ./samples out.pdf --book-type manga --dewarp-mode dewarpnet

# 小説・実用書（縦書き、A4サイズ、影・裏写り除去）
python main.py ./novel/ novel.pdf --book-type jp_vert --shadow-strength 1.0

# AI 超解像を適用（Real-ESRGAN x2）
python main.py ./input out.pdf --ai-enhance --ai-backend realesrgan --ai-scale 2
```

### オプション一覧

| オプション | 説明 | デフォルト |
|------------|------|------------|
| `--book-type` | `jp_vert` (縦書き), `jp_horiz` (横書き), `en` (英語), `manga` (漫画) | `jp_vert` |
| `--dewarp-mode` | `dewarpnet` (AI 高精度), `polynomial` (幾何補正), `none` (なし) | `dewarpnet` |
| `--ai-enhance` | AI モデルで超解像補正を行う | (行わない) |
| `--ai-backend` | `realesrgan` または `swin2sr` | `realesrgan` |
| `--ai-scale` | 超解像の拡大倍率 (`2` または `4`) | `2` |
| `--output-size` | `A4`, `A5`, `B5`, `Letter` | `A4` |
| `--sensitivity` | `low`, `medium`, `high` (境界検出感度) | `medium` |
| `--grayscale` | 強制的にグレースケールで出力 | (書籍タイプに依存) |
| `--shadow-strength`| 影・裏写り除去の強度 (0.0 - 1.0) | `1.0` |
| `--no-split` | 見開き分割を行わない | (分割する) |
| `--no-orient` | 向きの自動補正を行わない | (補正する) |
| `--no-border` | 黒縁除去を行わない | (除去する) |

## 補正アルゴリズムについて

### 1. 湾曲補正 (Dewarping)
AI（DewarpNet）または 3次多項式メッシュフィッティングを採用。ページの綴じ目付近の急激な曲がりと、画像端の歪みの両方を考慮して平坦化します。

### 2. 背景白色化 (Document Cleaning)
単なる二値化ではなく、エリアごとの紙の明るさを推定する「適応型白色化」を行います。これにより、文字を鮮明に残したまま、裏側の透けや照明のムラを消し去ります。

### 3. 傾き補正 (Deskewing)
ハフ変換によりテキストの行（ベースライン）を検出し、画像全体を微細回転させます。

## より綺麗にスキャンするためのヒント

1. **背景を工夫する:** 本の背景に黒い布などを敷くと、ページの境界（エッジ）をより正確に検出できます。
2. **照明を均一にする:** 強い直射日光よりも、柔らかな間接照明の方が影除去が綺麗にかかります。
3. **フラットに置く:** 可能な限り本を平らに開いて撮影することで、湾曲補正の精度が最大化されます。

## 対応画像フォーマット

- JPEG, PNG, HEIC, BMP, TIFF, TIF

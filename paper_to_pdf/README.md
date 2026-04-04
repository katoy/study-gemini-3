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
5. [AI 補正バックエンド](#ai-補正バックエンド)
6. [パフォーマンス](#パフォーマンス)
7. [補正アルゴリズムについて](#補正アルゴリズムについて)
8. [より綺麗にスキャンするためのヒント](#より綺麗にスキャンするためのヒント)
9. [対応画像フォーマット](#対応画像フォーマット)

---

## 主な機能

- **インテリジェント自動判定:** スマホを縦に持って撮った「横向きの見開き」も自動で回転・分割。
- **高度な湾曲補正 (DewarpNet / Polynomial / DocTR):**
    - `dewarpnet`: 深層学習を用いた強力な 3D 湾曲補正。
    - `polynomial`: 3次多項式を用いてページの非対称な膨らみを精密に平坦化。
    - `doctr`: AI Transformer ベースの文書補正。
- **AI 超解像 & 復元補正:** Real-ESRGAN / Swin2SR による鮮明化、DocRes による AI 影・裏写り除去。
- **強力なドキュメント・クリーン:** 背景（紙の色）を純白にし、裏写り（ブリードスルー）や影を完全に排除。
- **精密な傾き補正 (Deskew):** テキスト行を 0.1度単位で検出し、完全に水平な状態に回転補正。
- **AI コーナー検出:** `--sensitivity ai` でコーナーを AI により精密に検出。
- **メモリ効率重視:** ストリーミング方式により、数百枚の画像でも安定して PDF を生成。

## アーキテクチャ

処理工程が独立したステップとして分離されており、パイプライン形式で実行されます。

- **`core/`**: 設定管理 (`config.py`) とパイプライン制御 (`pipeline.py`)。
- **`steps/`**: 各処理フェーズの独立した実装。
    - `DetectionStep` (`detection.py`): ページ境界検出と見開き分割。
    - `DewarpStep` (`dewarp.py`): 湾曲補正（AI / 多項式 / DocTR）。
    - `EnhancementStep` (`enhancement.py`): AI による超解像・復元補正。
    - `PostProcessStep` (`postprocess.py`): 影除去、傾き・向き補正、サイズ正規化。
- **`utils/`**: 共通ユーティリティ。
    - `device.py`: デバイス（CPU / MPS / CUDA）選択。
    - `image.py`: 画像 I/O ヘルパー。
    - `paths.py`: モデルキャッシュパス管理。
    - `dewarpnet_arch.py`: DewarpNet モデル定義。

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

# AI による影・裏写り除去（超解像なし）
python main.py ./input out.pdf --ai-enhance --ai-backend docres --ai-scale 1

# AI コーナー検出 + 詳細ログ
python main.py ./input out.pdf --sensitivity ai --verbose
```

### オプション一覧

| オプション | 説明 | デフォルト |
|------------|------|------------|
| `--book-type` | `jp_vert` (縦書き), `jp_horiz` (横書き), `en` (英語), `manga` (漫画) | `jp_vert` |
| `--dewarp-mode` | `dewarpnet` (AI 高精度), `polynomial` (幾何補正), `doctr` (AI Transformer), `none` (なし) | `dewarpnet` |
| `--ai-enhance` | AI モデルで超解像・復元補正を行う | (行わない) |
| `--ai-backend` | `realesrgan` (超解像), `swin2sr` (超解像), `docres` (AI 影・裏写り除去) | `realesrgan` |
| `--ai-scale` | 超解像の拡大倍率 (`1`: 復元のみ, `2`, `4`) | `2` |
| `--output-size` | `A4`, `A5`, `B5`, `Letter` | `A4` |
| `--sensitivity` | `low`, `medium`, `high`, `ai` (AI によるコーナー検出) | `medium` |
| `--grayscale` | 強制的にグレースケールで出力 | (書籍タイプに依存) |
| `--shadow-strength`| 影・裏写り除去の強度 (0.0 - 1.0) | `1.0` |
| `--no-split` | 見開き分割を行わない | (分割する) |
| `--no-orient` | 向きの自動補正を行わない | (補正する) |
| `--no-border` | 黒縁除去を行わない | (除去する) |
| `--verbose`, `-v` | 詳細ログを出力 | (なし) |

## AI 補正バックエンド

### Real-ESRGAN（推奨）
- ノイズ除去 + 超解像。書籍スキャンに最適化。
- インストール: `pip install realesrgan basicsr`
- モデルは初回実行時に自動ダウンロード (`~/.cache/paper_to_pdf/`)

### Swin2SR（HuggingFace）
- Swin Transformer V2 ベースの超解像。
- インストール: `pip install transformers accelerate`
- モデルは HuggingFace Hub から自動ダウンロード。

> **Warning: You are sending unauthenticated requests to the HF Hub...** が表示される場合  
> HuggingFace の認証トークンが未設定です。[https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) でトークンを取得し、以下のいずれかで設定してください。
>
> ```bash
> # 方法 A: CLI でログイン（推奨・一度だけ実行）
> huggingface-cli login
>
> # 方法 B: 環境変数で設定
> export HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxx"
> ```
>
> 未認証でも動作しますが、ダウンロード速度が制限される場合があります。

### DocRes（AI 影・裏写り除去）
- AI による高精度な影・裏写り（ブリードスルー）除去。`--ai-scale 1` と組み合わせて復元のみの用途にも利用可能。
- インストール: `pip install transformers`
- `--ai-backend docres --ai-scale 1` で超解像なしの復元処理として動作。

### DewarpNet（`--dewarp-mode dewarpnet` 使用時）
- 湾曲補正に AI モデルを使用。PyTorch 必須。
- モデルが未ダウンロードまたは PyTorch 未インストール時は polynomial に自動フォールバック。

> **M1 Mac の場合:** PyTorch は MPS（Metal）で GPU 加速されます。

---

## パフォーマンス

> 以下の数値は **A4 @ 300 DPI（約 2480×3508 px）の見開き 1 枚** を処理した場合のおおよその目安です。  
> 実測値は画像サイズ・内容・ハードウェア環境によって大きく変わります。

### 湾曲補正モードの速度比較

| モード | CPU | M1 Mac (MPS) | 備考 |
|--------|-----|--------------|------|
| `none` | < 0.1 s | < 0.1 s | 補正なし |
| `polynomial` | 0.1〜0.5 s | 0.1〜0.5 s | GPU 不要。軽量で安定 |
| `dewarpnet` | 1〜3 s | 0.5〜1.5 s | AI による高精度補正。初回はモデルロードに数秒 |
| `doctr` | *(placeholder)* | *(placeholder)* | 実装予定 |

### AI 超解像・復元モデルの速度比較

タイル推論（512 px または 128 px 単位）のため、処理時間は画像サイズに概ね比例します。

| バックエンド | スケール | CPU | M1 Mac (MPS) | NVIDIA GPU (CUDA) | 特徴 |
|--------------|----------|-----|--------------|-------------------|------|
| `realesrgan` | ×2 | 15〜40 s | 3〜8 s | 1〜3 s | **推奨。** 品質・速度のバランスが最良 |
| `realesrgan` | ×4 | 40〜120 s | 8〜25 s | 2〜8 s | 高解像度が必要な場合 |
| `swin2sr` | ×2 | 数分 | 30〜90 s | 10〜30 s | タイル 128 px のため非常に遅い |
| `swin2sr` | ×4 | 数分〜 | 60〜180 s | 20〜60 s | CPU での利用は非推奨 |
| `docres` | ×1 | 8〜20 s | 2〜5 s | 1〜2 s | 復元のみ（超解像なし）。高速 |

### 処理全体の目安（`--ai-enhance` なし）

見開き 1 枚あたり、湾曲補正を含む全処理（AI 超解像除く）のおおよその合計時間：

| 構成 | CPU |
|------|-----|
| `--dewarp-mode none` | < 1 s |
| `--dewarp-mode polynomial` | 0.5〜2 s |
| `--dewarp-mode dewarpnet` | 2〜5 s |

### 推奨設定

| 目的 | 推奨オプション |
|------|---------------|
| **速度重視**（プレビュー確認など） | `--dewarp-mode polynomial` |
| **品質重視**（最終出力） | `--dewarp-mode dewarpnet --ai-enhance --ai-backend realesrgan --ai-scale 2` |
| **影・裏写りが強い場合** | `--ai-enhance --ai-backend docres --ai-scale 1` |
| **GPU なしで AI 超解像** | `--ai-enhance --ai-backend realesrgan --ai-scale 2`（CPU でも動作するが遅い） |

---

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

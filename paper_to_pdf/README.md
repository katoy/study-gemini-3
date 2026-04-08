# paper_to_pdf

スマホで撮影した書籍の見開きページを AI 補正してクリーンな PDF に変換する高度な CLI ツール。

---

## 目次

1. [主な機能](#主な機能)
2. [ディレクトリ構成](#ディレクトリ構成)
3. [補正アルゴリズムの詳細](#補正アルゴリズムの詳細)
4. [セットアップ](#セットアップ)
5. [使い方](#使い方)
6. [オプション一覧](#オプション一覧)
7. [AI 補正バックエンド](#ai-補正バックエンド)
8. [パフォーマンス目安](#パフォーマンス目安)
9. [ライセンス・引用](#ライセンス引用)

---

## 主な機能

- **高精度ページ境界検出:** 白比率プロファイル + Canny エッジ密度急落で、背景テクスチャを確実に除去。台形に傾いた書籍も正確に検出。
- **Portrait 見開き対応:** カメラを 90° 回転して撮影した見開き（上下配置）を自動検出し、水平分割。
- **ページ順序自動判定:** 縦書き/横書きの形態解析により、右開き/左開きを自動推定。
- **高度な湾曲補正 (Dewarping):**
  - **反復的高精度補正:** 3段階のパスにより、文字列をほぼ完璧な水平に整列。
  - **WLS フィッティング:** 重み付き最小二乗法により、長い本文行を優先的に平坦化。
  - **AI 幾何補正 (DewarpNet):** 深層学習による 3D 湾曲補正（見開き全体に対応）。
- **AI 超解像 & 復元補正:** Real-ESRGAN / Swin2SR による鮮明化、DocRes による AI 影・裏写り除去。
- **ドキュメント・クリーニング:** 適応型白色化で紙面を純白に。照明ムラを解消。
- **品質診断 (Quality Check):** 本文エリア（中央 70%）に特化した歪み検出。文字の見切れ、余分な背景を自動検出し、レポート。

---

## ディレクトリ構成

| パス | 役割 |
|------|------|
| `main.py` | CLI エントリポイント・引数処理 |
| `processor.py` | 全体プロセスのオーケストレーション |
| `core/pipeline.py` | 処理ステップの実行管理 |
| `core/config.py` | 処理設定データクラス (`ProcessingConfig`) |
| `page_detector.py` | ページ境界検出・綴じ目検出・分割のコアロジック |
| `dewarper.py` | 湾曲補正 (AI / 多項式) のエントリポイント |
| `steps/` | パイプラインの各処理ステップ |
| `utils/` | デバイス選択、画像 I/O、共通行プロファイル抽出 |
| `pdf_builder.py` | ストリーミング方式による PDF 生成 |
 
---
 
## 処理パイプラインの流れ
 
```mermaid
graph TD
    A[入力画像] --> B[DetectionStep]
    subgraph "1. Detection & Split (page_detector.py)"
        B --> B1[書籍領域の境界検出]
        B1 --> B2[透視変換による正投影]
        B2 --> B3[AI 幾何補正: DewarpNet/DocTr ※任意]
        B3 --> B4[向き・天地の自動補正]
        B4 --> B5[綴じ目検出 & 左右ページ分割]
    end
    B5 --> C[DewarpStep]
    subgraph "2. Refined Dewarp (dewarper.py)"
        C --> C1[共通行プロファイルの抽出]
        C1 --> C2[WLS重み付き 3次多項式フィッティング]
        C2 --> C3[3段階の反復的平坦化 (Straightening)]
        C3 --> C4[安全ガード: 補正量制限 & 破綻検知]
    end
    C4 --> D[EnhancementStep]
    subgraph "3. Enhancement (ai_enhancer.py)"
        D --> D1[AI 超解像: Real-ESRGAN / Swin2SR]
        D1 --> D2[AI 影・裏写り除去: DocRes]
    end
    D2 --> E[PostProcessStep]
    subgraph "4. Finalizing (image_processor.py)"
        E --> E1[適応型白色化 & コントラスト調整]
        E1 --> E2[出力サイズ正規化: A4/B5 等]
    end
    E2 --> F[QualityCheckStep]
    subgraph "5. Quality Evaluation"
        F --> F1[本文エリア特化の湾曲・傾き評価]
        F1 --> F2[文字見切れ & 背景残留の判定]
        F2 --> F3[品質診断レポート生成]
    end
    F3 --> G[PDF Builder]
    G --> H((出力 PDF))
```
 
---
 
## 補正アルゴリズムの詳細

### 1. ページ境界検出 (Detection)
複数のアルゴリズムを多層防御的に組み合わせ、最もスコアの高い結果を採用します。
- **Edge & Profile:** ページの内部領域（白比率）と、背景との物理境界（エッジ密度）を統合評価。
- **Safety Inset:** 検出された境界を 0.2% 内側に追い込むことで、背景の写り込みを完全に除去。

### 2. 反復的湾曲補正 (Polynomial Dewarping)
従来の 1 パス補正とは異なり、以下の高度なプロセスを踏みます。
1. **共通プロファイル抽出:** `utils/image.py` の共通ロジックにより、画像全体のテキスト行のうねりを正確に抽出。
2. **重み付き最小二乗法 (WLS):** 行の長さに応じた重み付けを行い、3次多項式で高精度にフィッティング。
3. **3段階反復:** 補正を 3 回繰り返すことで、残存する微細な歪みを段階的に排除し、文字列を真っ直ぐにします。
4. **安全装置:** 補正量リミッター (高さの 35% 以内) と白紙化検知により、画像の完全性を保護。

---

## セットアップ

```bash
cd paper_to_pdf
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **M1 Mac:** PyTorch は MPS (Metal Performance Shaders) で GPU 加速されます。

---

## 使い方

```bash
python main.py <入力フォルダ> <出力PDF> [オプション]
```

### 実行例

- **基本（AI + 高精度補正）:**
  ```bash
  python main.py ./samples out.pdf --dewarp-mode dewarpnet
  ```
- **最高画質（超解像 x2）:**
  ```bash
  python main.py ./samples out.pdf --ai-enhance --ai-backend realesrgan --ai-scale 2
  ```
- **診断モード（品質レポートを表示）:**
  ```bash
  python main.py ./samples out.pdf --diagnose
  ```

---

## オプション一覧

| オプション | 説明 | デフォルト |
|------------|------|------------|
| `--book-type` | 書籍タイプ (`auto`, `jp_vert`, `jp_horiz`, `manga`) | `auto` |
| `--dewarp-mode` | 湾曲補正 (`dewarpnet`, `polynomial`, `none`) | `dewarpnet` |
| `--writing-mode` | 書字方向 (`horizontal`, `vertical`, `auto`) | `auto` |
| `--ai-enhance` | AI 超解像・復元補正を有効化 | 無効 |
| `--diagnose` | 処理後に品質診断サマリーを表示 | 無効 |
| `--show-page-area` | 分割・抽出範囲を赤枠描画した確認用 PDF を出力 | 無効 |

---

## パフォーマンス目安 (A4 @ 300 DPI 見開き)

| モード | 環境 | 速度 |
|--------|------|------|
| Polynomial (3-iter) | CPU | ~0.8s |
| DewarpNet | M1 Mac (MPS) | ~1.2s |
| Real-ESRGAN x2 | M1 Mac (MPS) | ~5.0s |

---

## ライセンス・引用
- **DewarpNet:** Stony Brook University (MIT License)
- **Real-ESRGAN:** Tencent ARC (BSD 3-Clause)

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
- **湾曲補正 (DewarpNet / Polynomial / DocTR):**
  - `dewarpnet`: 深層学習による 3D 湾曲補正。
  - `polynomial`: 3 次多項式で非対称な膨らみを平坦化。
  - `doctr`: Transformer ベースの文書補正。
- **AI 超解像 & 復元補正:** Real-ESRGAN / Swin2SR による鮮明化、DocRes による AI 影・裏写り除去。
- **ドキュメント・クリーニング:** 適応型白色化で紙面を純白に。照明ムラを解消。
- **品質診断 (Quality Check):** 文字の見切れ、余分な背景、歪みを自動検出し、処理後にレポート。

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
| `steps/` | パイプラインの各処理ステップ (Detection, Dewarp, Enhancement, etc.) |
| `utils/` | デバイス選択、画像 I/O、モデルパス管理、座標変換 |
| `pdf_builder.py` | ストリーミング方式による PDF 生成 |

---

## 補正アルゴリズムの詳細

### 1. ページ境界検出 (Detection)
複数のアルゴリズムを多層防御的に組み合わせ、最もスコアの高い結果を採用します。
- **Edge & Profile:** ページの内部領域（白比率）と、背景との物理境界（エッジ密度）を統合評価。
- **Safety Inset:** 検出された境界を 0.2% 内側に追い込むことで、微細な背景の写り込みを物理的に除去。

### 2. 綴じ目検出 (Center Seam)
見開きの「谷」を特定するための 3 段階戦略：
1. **戦略 0 (片側空白):** 片方のページが白紙（扉ページ等）の場合を検出し、中央 50% を境界とする。
2. **戦略 1 (明るいギャップ):** 製本時のスパインや白いマージンによる垂直な「隙間」を優先。
3. **戦略 2 (輝度最小値):** 物理的な「谷」による影を探索。中心引力ペナルティにより、端の影への誤検出を防止。

### 3. 湾曲補正 (Dewarping)
- **Cubic Polynomial Fitting:**
  $$y = ax^3 + bx^2 + cx + d$$
  3 次式を用いることで、見開き特有の複雑な曲線をモデル化。フィッティングの決定係数 $R^2$ が低い場合は、誤補正を防ぐため自動的にスキップされます。
- **Gradient-based Stretching:** 曲線の傾きに基づいて垂直方向に画像を補間し、歪んで圧縮された文字を元の比率に復元します。

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

- **基本（AI 補正あり）:**
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
| `--dewarp-mode` | 湾曲補正 (`dewarpnet`, `polynomial`, `doctr`, `none`) | `dewarpnet` |
| `--ai-enhance` | AI 超解像・復元補正を有効化 | 無効 |
| `--ai-backend` | 補正エンジン (`realesrgan`, `swin2sr`, `docres`) | `realesrgan` |
| `--diagnose` | 処理後に品質診断サマリーを表示 | 無効 |
| `--show-book-area` | 検出した書籍領域を赤枠で可視化して出力 | 無効 |

---

## AI 補正バックエンド

### Real-ESRGAN
ノイズ除去と超解像を同時に行います。書籍の小さな文字をクッキリさせるのに最適です。

### DocRes
AI による高精度な影・裏写り除去。`--ai-scale 1` で超解像なしの復元のみとしても動作します。

---

## パフォーマンス目安 (A4 @ 300 DPI 見開き)

| モード | 環境 | 速度 |
|--------|------|------|
| Polynomial | CPU | ~0.5s |
| DewarpNet | M1 Mac (MPS) | ~1.0s |
| Real-ESRGAN x2 | M1 Mac (MPS) | ~5.0s |

---

## ライセンス・引用
- **DewarpNet:** Stony Brook University (MIT License)
- **Real-ESRGAN:** Tencent ARC (BSD 3-Clause)
- **DocTr:** Document Transformer (Apache 2.0)

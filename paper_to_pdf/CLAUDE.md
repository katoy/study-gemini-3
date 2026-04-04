# CLAUDE.md - paper_to_pdf

日本語で対話すること

## プロジェクト概要

スマホで撮影した書籍の見開きページを、AI 級の高精度な補正を施してクリーンな PDF に変換するコマンドライン・ツール。

## ファイル構成

| ファイル | 役割 |
|----------|------|
| `main.py` | CLI エントリポイント。引数パースと `BookProcessor` の起動 |
| `processor.py` | `BookProcessor` / `ProcessingConfig` — 処理全体のオーケストレーション |
| `page_detector.py` | ページ境界・向き検出 |
| `dewarper.py` | 湾曲補正 (DewarpNet AI / polynomial フォールバック) |
| `image_processor.py` | 背景白色化・影除去・傾き補正 |
| `pdf_builder.py` | PDF 組み立て (ストリーミング方式) |
| `ai_enhancer.py` | オープンソース AI モデルによる超解像補正 |

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 実行方法

```bash
python main.py <入力フォルダ> <出力PDF> [オプション]

# 例: 漫画
python main.py ./samples out.pdf --book-type manga --dewarp-mode dewarpnet

# 例: 縦書き小説
python main.py ./novel/ novel.pdf --book-type jp_vert --shadow-strength 1.0
```

## 主要オプション

| オプション | 説明 | デフォルト |
|------------|------|------------|
| `--book-type` | `jp_vert` / `jp_horiz` / `en` / `manga` | `jp_vert` |
| `--dewarp-mode` | `dewarpnet` / `polynomial` / `none` | `dewarpnet` |
| `--output-size` | `A4` / `A5` / `B5` / `Letter` | `A4` |
| `--sensitivity` | `low` / `medium` / `high` | `medium` |
| `--shadow-strength` | 影・裏写り除去強度 (0.0–1.0) | `1.0` |
| `--grayscale` | グレースケール出力 | manga タイプは自動 ON |
| `--ai-enhance` | AI 超解像補正を有効化 | OFF |
| `--ai-backend` | `realesrgan` / `swin2sr` | `realesrgan` |
| `--ai-scale` | 超解像倍率 `2` / `4` | `2` |

## AI 補正バックエンド

### Real-ESRGAN (推奨)
- ノイズ除去 + 超解像。書籍スキャンに最適化。
- インストール: `pip install realesrgan basicsr`
- モデルは初回実行時に自動ダウンロード (`~/.cache/paper_to_pdf/`)

### Swin2SR (HuggingFace)
- Swin Transformer V2 ベースの超解像。
- インストール: `pip install transformers accelerate`
- モデルは HuggingFace Hub から自動ダウンロード

### DewarpNet (dewarpnet モード時)
- 湾曲補正に AI モデルを使用。PyTorch 必須。
- モデルが未ダウンロードまたは PyTorch 未インストール時は polynomial に自動フォールバック。

## 依存ライブラリ

- `opencv-python` — 画像処理全般
- `Pillow` — 画像 I/O・PDF 組み立て
- `numpy` — 数値演算
- `torch` / `torchvision` — DewarpNet (M1 Mac: MPS 加速)
- `requests` — モデルの自動ダウンロード

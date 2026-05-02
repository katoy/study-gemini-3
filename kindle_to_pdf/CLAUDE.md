# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## セットアップ

```bash
bash setup.sh
# または手動で:
uv sync
uv run playwright install chromium
```

## 実行コマンド

```bash
# Chrome を自動起動してキャプチャ（推奨）
uv run python main.py --launch-chrome

# 既存の PNG 画像から PDF のみ生成
uv run python main.py --images-dir ./output/<書籍タイトル>

# PNG を保持したままキャプチャ
uv run python main.py --launch-chrome --screenshots keep

## テストの実行

```bash
# 全てのテストを実行
uv run pytest

# 特定のファイルのみ実行
uv run pytest tests/test_kindle_capture.py

# カバレッジを確認
uv run pytest --cov=.
```

## アーキテクチャ

3 モジュールの直列パイプライン:

```
main.py → kindle_capture.py → pdf_maker.py
```

**`main.py`**: CLI 引数解析 (`argparse`) と全体フロー管理。`--launch-chrome` が指定されると `kindle_capture.launch_chrome()` でサブプロセスとして Chrome を起動し、空きポートを自動割り当てする。処理は `while True` ループで複数冊の連続処理に対応。

**`kindle_capture.py`**: Playwright の CDP 接続 (`connect_over_cdp`) で既存 Chrome セッションに接続し、`read.amazon` を含む URL を持つタブを自動検出する。ページ送りは `ArrowDown` キーで行い、各ページ遷移後にスクリーンショットの MD5 を比較してレンダリング安定を待つ (`_wait_for_page_stable`)。同一ハッシュが `MAX_SAME_PAGES=3` 回続いたら書籍終端と判定して停止する。

**`pdf_maker.py`**: `img2pdf.convert()` で PNG を再エンコードせず結合する。これにより macOS Live Text によるテキスト認識が高精度になる。

## 重要な定数 (kindle_capture.py)

| 定数 | 値 | 説明 |
|---|---|---|
| `MAX_SAME_PAGES` | `3` | 同一画面連続検出で終端とみなす回数 |
| `NEXT_PAGE_KEY` | `'ArrowDown'` | ページ送りキー |
| `DEFAULT_CDP_URL` | `'http://localhost:9222'` | Chrome CDP エンドポイント |

# NHK ラジオ聞き逃し Web (FastAPI + htmx)

`radio` (Tkinter GUI) を FastAPI + htmx で書き直した Web アプリです。

## 目次

- [必要条件](#必要条件)
- [セットアップ](#セットアップ)
- [起動](#起動)
- [機能](#機能)
- [テスト・カバレッジ](#テストカバレッジ)
  - [実行方法](#実行方法)
  - [計測結果](#計測結果)
- [環境変数](#環境変数)
- [プロジェクト構成](#プロジェクト構成)

---

## 必要条件

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- ffmpeg (ダウンロード時)

## セットアップ

```bash
cd radio-web
uv sync
```

## 起動

```bash
uv run uvicorn app.main:app --reload
```

ブラウザで http://localhost:8000 を開く。

## 機能

| 操作 | 説明 |
|---|---|
| ジャンル選択 | プルダウンで絞り込み (htmx で部分更新) |
| 番組カードをクリック | エピソード一覧を展開 (htmx で遅延ロード) |
| DL ボタン | yt-dlp でバックグラウンドダウンロード開始 |
| `/downloads` | 全ジョブの状態確認 |

## テスト・カバレッジ

### 実行方法

```bash
# 通常実行 (term-missing 表示)
bash scripts/test.sh

# HTML レポートも生成
bash scripts/test.sh --html
# → htmlcov/index.html をブラウザで開く
```

目標カバレッジ: **80% 以上** (`--cov-fail-under=80` で強制)

### 計測結果

> 実行日: 2026-04-21 / Python 3.13.13 / pytest 9.0.3

```
123 passed, 2 skipped in 3.11s
```

| ファイル | Stmts | Miss | カバレッジ | 未カバー行 |
|---|---:|---:|---:|---|
| `nhk_radio_web/__init__.py` | 0 | 0 | **100%** | — |
| `nhk_radio_web/cache.py` | 93 | 0 | **100%** | — |
| `nhk_radio_web/config.py` | 34 | 0 | **100%** | — |
| `nhk_radio_web/constants.py` | 10 | 0 | **100%** | — |
| `nhk_radio_web/core.py` | 214 | 0 | **100%** | — |
| `nhk_radio_web/downloads.py` | 272 | 0 | **100%** | — |
| `nhk_radio_web/text.py` | 134 | 0 | **100%** | — |
| `nhk_radio_web/types.py` | 36 | 0 | **100%** | — |
| **TOTAL** | **793** | **0** | **100%** | — |

**注記:**

- Windows 向けパス分岐 (`os.name == "nt"`) は macOS で実行不可のため `# pragma: no cover` でスキップ
- 到達不能な防御的コードも同様に `# pragma: no cover` でスキップ

## 環境変数

| 変数 | 説明 | デフォルト |
|---|---|---|
| `NHK_RADIO_CACHE_DIR` | キャッシュ保存先 | `<project>/.cache` |
| `NHK_RADIO_DOWNLOAD_DIR` | ダウンロード先 | `<project>/downloads` |

## プロジェクト構成

```
radio-web/
├── app/
│   ├── main.py          # FastAPI インスタンス・lifespan
│   └── routes.py        # 全エンドポイント・ダウンロードジョブ管理
├── src/nhk_radio_web/
│   ├── types.py         # Program / Episode dataclass
│   ├── constants.py     # NHK API URL・ジャンル定数
│   ├── core.py          # 番組・エピソード取得ロジック
│   ├── cache.py         # JSON キャッシュ (TTL 付き)
│   ├── downloads.py     # ダウンロード追跡・yt-dlp コマンド生成
│   ├── text.py          # テキスト整形ユーティリティ
│   └── config.py        # パス解決・環境変数
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── downloads.html
│   └── partials/
│       ├── program_list.html
│       ├── episode_list.html
│       └── download_status.html
├── tests/               # pytest テスト (75 件)
└── scripts/test.sh      # テスト実行スクリプト
```

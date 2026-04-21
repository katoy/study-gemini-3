# CLAUDE.md — radio-web

日本語で対話すること。

## プロジェクト概要

NHK ラジオ「らじる★らじる」聞き逃し番組の検索・ダウンロード Web アプリ。
`../radio` (Tkinter GUI) を FastAPI + htmx で書き直したもの。個人学習目的専用。

## 起動

```bash
uv run uvicorn app.main:app --reload
# → http://localhost:8000
```

## テスト

```bash
bash scripts/test.sh           # カバレッジ付き実行
bash scripts/test.sh --html    # HTML レポートも生成
```

目標カバレッジ: **100%**

## アーキテクチャ

```
radio-web/
├── app/
│   ├── main.py       # FastAPI インスタンス・lifespan
│   └── routes.py     # 全エンドポイント・ダウンロードジョブ管理 (_jobs dict)
├── src/nhk_radio_web/
│   ├── types.py      # Program / Episode dataclass
│   ├── constants.py  # NHK API URL・ジャンル定数
│   ├── core.py       # 番組・エピソード取得ロジック (asyncio + httpx + yt-dlp)
│   ├── cache.py      # JSON キャッシュ (TTL=3600s、スキーマバージョン管理)
│   ├── downloads.py  # ダウンロード追跡・yt-dlp コマンド生成・マニフェスト管理
│   ├── text.py       # テキスト整形ユーティリティ
│   └── config.py     # パス解決・環境変数
├── templates/
│   ├── base.html             # レイアウト・startDL() JS 関数
│   ├── index.html            # ジャンルフィルタ + 番組グリッド
│   ├── downloads.html        # ジョブ一覧ページ
│   └── partials/
│       ├── program_list.html  # 番組カードグリッド・トグル JS
│       ├── episode_list.html  # エピソード一覧・DL ボタン
│       └── download_status.html # ステータス表示・htmx ポーリング
└── tests/
```

## 重要な設計上の決定

### htmx + ダウンロード
- DL ボタンは `hx-vals` + json-enc 拡張を **使わない**。
  → `data-program` / `data-episode` 属性に JSON を持たせ、`startDL()` で `fetch()` する。
- `POST /download` はステータス HTML フラグメントを返す（JSONResponse ではない）。
  → htmx が `outerHTML` スワップ後、`htmx.process()` でポーリングを起動。

### 番組カードのトグル
- `data-open` 属性で開閉状態を管理。CSS で `.program-card[data-open] .episode-area { display: block }` を制御。
- 初回クリック: htmx がエピソードを取得し、`after-request` でカードに `data-loaded` と `data-open` を付与。
- 2回目以降: JS イベントデリゲーション (`document.addEventListener('click', ...)`) でトグル。
- `button` クリックはトグルしない (`if (e.target.closest('button')) return`)。

### キャッシュ
- 番組一覧: `.cache/programs/{genre|all}.json`（TTL 1時間）
- エピソード一覧: `.cache/episodes/{site_id}_{corner_id}.json`（TTL 1時間）
- 取得失敗時は stale キャッシュ（TTL=10^12）でフォールバック。

### Starlette 1.0.0 の TemplateResponse API
```python
# 正しい書き方（request を第1引数に）
templates.TemplateResponse(request, "template.html", {"key": "value"})
# NG: TemplateResponse("template.html", {"request": req, ...})
```

### pragma: no cover
- Windows NT パス分岐 (`os.name == "nt"`) は macOS で実行不可。
- 到達不能な防御的コード（ファイルシステムが重複パスを返さない等）。

## 環境変数

| 変数 | デフォルト |
|---|---|
| `NHK_RADIO_CACHE_DIR` | `<project>/.cache` |
| `NHK_RADIO_DOWNLOAD_DIR` | `<project>/downloads` |

## 依存関係の追加

```bash
uv add <package>
uv add --dev <package>
```

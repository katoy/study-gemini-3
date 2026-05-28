# radio-web コード全体レビュー（2026-05-29）

## 概要

radio-web は **100% テストカバレッジ** を達成した完成度の高い FastAPI + htmx Web アプリケーション。REST API、WebSocket、キャッシング、バッチダウンロード、ジャンルフィルタなど、機能は十分に揃っている。ただし、いくつかの拡張性や保守性の改善ポイントが存在する。

---

## ✅ 強み

### 1. **テストと品質**

- ✅ テストカバレッジ **100%** (248 件)
- ✅ 全モジュール厳密にテスト
- ✅ エラー経路・エッジケース対応済み
- ✅ `pytest` + `mypy` + `ruff` で完全検証

### 2. **API 設計**

- ✅ **14 エンドポイント** で Web アプリに必要な機能をカバー
- ✅ 型安全な Pydantic モデル (`ProgramData`, `EpisodeData`, `DownloadJobData`)
- ✅ 一貫性のある JSON API (`/api/v1/...`)
- ✅ HTML + JSON の 2 つのレスポンス形式に対応
- ✅ メタデータ (`meta`) による構造化レスポンス

### 3. **リアルタイム機能**

- ✅ WebSocket (`/ws/jobs`) でダウンロード進捗をリアルタイム配信
- ✅ 観測可能性（進捗 %, ETA, 速度を可視化）
- ✅ htmx ポーリング + WebSocket のハイブリッド対応

### 4. **キャッシング戦略**

- ✅ TTL ベース (1 時間) でパフォーマンス最適化
- ✅ Stale キャッシュ (TTL=10^12) で障害耐性
- ✅ スキーマバージョン管理でマイグレーション対応

### 5. **ダウンロード管理**

- ✅ 並行制御 (デフォルト 2 並行)
- ✅ 自動リトライ (3 回、指数バックオフ)
- ✅ キャンセル機能
- ✅ ファイル追跡 + RFC 5987 Content-Disposition

### 6. **ドメイン設計**

- ✅ 関心の分離 (routes vs core vs downloads vs job_manager)
- ✅ Dataclass 型 (`Program`, `Episode`) で構造化
- ✅ 検索・フィルタ・ソート機能完備

---

## 🚨 改善ポイント

### 1. **REST API 過不足**

#### 不足している機能
- ❌ **ダウンロードジョブのバッチ操作**
  - 複数ジョブの一括キャンセル API がない
  - 提案: `DELETE /api/v1/download-jobs?status=...` (フィルタ付き削除)

- ❌ **進捗情報の JSON API**
  - WebSocket でしか進捗が取得できない
  - REST クライアント向けに `GET /api/v1/download-jobs/{job_id}/progress` が欲しい

- ❌ **ダウンロード履歴・統計**
  - 完了したジョブの検索・フィルタがない
  - 提案: `GET /api/v1/download-jobs?status=completed&limit=50&offset=0`

- ❌ **キャッシュ状態の問い合わせ**
  - `POST /api/cache/clear` はあるが、キャッシュ容量や更新時刻が取得できない
  - 提案: `GET /api/v1/cache/status` (キャッシュサイズ、最終更新時刻など)

- ❌ **番組検索の高度なフィルタ**
  - `genre` と `q` しかない
  - 提案: `broadcast` フィルタ (AM/FM), `onair_date` 範囲検索

#### 既存エンドポイントの視点

| 機能 | GET | POST | PUT | DELETE | WebSocket |
|------|-----|------|-----|--------|-----------|
| 番組管理 | ✅ | - | - | - | - |
| エピソード取得 | ✅ | - | - | - | - |
| ダウンロードジョブ作成 | - | ✅ | - | - | - |
| ジョブ一覧・詳細 | ✅ | - | - | ✅ | ✅ |
| ファイルダウンロード | ✅ | - | - | - | - |
| 設定管理 | ✅ | ✅ | ✅ | - | - |
| キャッシュ管理 | - | ✅ | - | - | - |

→ **結論**: 基本機能は揃っている。だが **バッチ操作**、**進捗情報 API**、**履歴検索** などの拡張に向けた整備が必要。

---

### 2. **エラーハンドリングの一貫性**

#### 問題
- HTTP ステータスコードがまちまち
  - 404 (見つからない), 422 (バリデーション), 204 (成功, 無コンテンツ)
  - エラーレスポンス形式が HTML と JSON でばらばら

#### 現況
```python
# routes.py での error 返却
raise HTTPException(status_code=422, detail="...")  # 一部は JSON
return HTMLResponse(status_code=204)  # 一部は HTML
```

#### 改善案
- ✅ `/api/v1/...` は必ず JSON + `ErrorResponse` 構造化
- ✅ HTML routes (`/`, `/programs`, ...) は HTML 返却（OK）
- ✅ エラーメッセージは国際化対応を考慮

#### 提案モデル
```python
class ErrorResponse(BaseModel):
    error: dict[str, str]  # {"code": "...", "message": "..."}

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
```

---

### 3. **MCP (Model Context Protocol) 対応**

#### 現況
- MCP サーバーは未実装
- クライアント向け API のみ

#### 提案

**MCP サーバーとして radio-web を公開すれば:**

1. **他の Claude エージェント/ツール** が番組検索できる
2. **バッチダウンロード** を自動化できる
3. **LLM が NHK コンテンツを検索・分析** できる

#### 実装例
```python
# mcp/server.py
from mcp.server import Server, Tool

server = Server("radio-web")

@server.tool("search_programs")
async def search_programs(query: str, genre: str = "") -> list[ProgramData]:
    """番組を検索する"""
    ...

@server.tool("list_episodes")
async def list_episodes(program_id: str) -> list[EpisodeData]:
    """エピソードを一覧取得"""
    ...

@server.tool("create_download")
async def create_download(program_id: str, episode_id: str) -> DownloadJobData:
    """ダウンロードを開始"""
    ...
```

**メリット:**
- 🤖 Claude が NHK 番組を自動検索・推薦
- 📊 分析ツール統合 (e.g. Notion + Claude)
- 🔗 ワークフロー自動化

---

### 4. **テスト行いやすさ**

#### 強み
- ✅ `TestClient` で統合テスト実装
- ✅ Dependency injection で Mocking 容易
- ✅ Fixture 充実

#### 改善余地

1. **テストヘルパーの抽出**
   ```python
   # tests/conftest.py (未作成)
   @pytest.fixture
   def test_program():
       return Program(site_id="...", corner_id="...", ...)
   
   @pytest.fixture
   def test_episode():
       return Episode(id="...", ...)
   ```

2. **タイムゾーン対応テスト**
   - 日付パース時にタイムゾーン違いで失敗する可能性
   - テストに `@freeze_time` デコレータを追加

3. **キャッシュ TTL のテスト改善**
   - 現在は手動で時間経過をシミュレート
   - `freezegun` で統一

4. **WebSocket テストの体系化**
   ```python
   # test_coverage_gaps.py では FakeWebSocket を使用
   # → より完全な WebSocket テストハーネス (conftest.py) を用意
   ```

---

### 5. **拡張性・保守性**

#### ルーティングの複雑化リスク

**現況:**
- `app/routes.py` が 889 行で単一ファイル
- 関数 50+ 個が一箇所に集中

**改善提案:**
```
app/
  routes/
    __init__.py
    html_routes.py      # `/`, `/downloads`, `/help` など HTML ルート
    api_v1_routes.py    # `/api/v1/...` JSON API
    ws_routes.py        # WebSocket
    internal_routes.py  # `/api/download`, `/api/cache` など内部エンドポイント
```

#### 設定の一元化

現在の設定分散:
- `app/routes.py`: ジャンル定義、genre ID マッピング
- `nhk_radio_web/constants.py`: API URL
- `nhk_radio_web/config.py`: パス

**改善:**
- `app/config.py` で API 仕様を定義 (バージョン, capabilities, etc.)

---

### 6. **パフォーマンス・スケーラビリティ**

#### メモリ使用量
- `all_programs` を毎回メモリロード → 大規模化で問題
- **改善**: ページネーション (`offset`, `limit`)

#### キャッシュ鮮度性
- TTL 1 時間は固定 → 動的調整がない
- **改善**: 環境変数化 + API で調整可能に

#### DB なしの限界
- JSON ファイルベースキャッシュ
- ファイル I/O 遅延の可能性
- **改善**: Redis キャッシュオプション

---

### 7. **ドキュメント**

#### 充実している
- ✅ README 完備
- ✅ OpenAPI 自動生成
- ✅ CLAUDE.md に設計説明

#### 足りない
- ❌ API 呼び出し例 (curl, Python, TypeScript)
- ❌ エラーコード一覧
- ❌ WebSocket メッセージスキーマ

#### 提案
```markdown
# API ドキュメント拡張

## エラーコード一覧

| Code | HTTP | 説明 |
|------|------|------|
| PROGRAM_NOT_FOUND | 404 | 番組が見つからない |
| EPISODE_NOT_FOUND | 404 | エピソードが見つからない |
| INVALID_GENRE | 422 | 無効なジャンル ID |
| CACHE_CLEAR_FAILED | 500 | キャッシュクリア失敗 |

## WebSocket メッセージ

```json
{
  "job_id": "...",
  "status": "pending|running|done|error",
  "progress": { "percent": 45.2, "eta": "02:30", ... },
  "error": null
}
```
```

---

### 8. **セキュリティ**

#### 現況
- ✅ CORS 設定（確認不可、main.py 短い）
- ✅ 入力バリデーション (Pydantic)
- ✅ SQL インジェクション リスクなし (JSON キャッシュ)

#### 確認項目
- ⚠️ CSRF トークン → htmx で自動か？
- ⚠️ ファイルダウンロード時の Path traversal 検証
- ⚠️ WebSocket 認証なし

#### 提案
```python
# app/main.py に追加
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
)

# WebSocket 認証
@app.websocket("/ws/jobs")
async def ws_jobs(websocket: WebSocket, token: str = Query(...)):
    # トークン検証
    verify_token(token)
    ...
```

---

## 📋 改善優先度

### 🔴 高 (次の sprint)

1. **ダウンロードジョブのバッチ削除 API**
   ```
   DELETE /api/v1/download-jobs?status=completed
   ```

2. **キャッシュ状態 API**
   ```
   GET /api/v1/cache/status
   ```

3. **エラーレスポンス構造化**
   ```python
   ErrorResponse(error={"code": "...", "message": "..."})
   ```

### 🟡 中 (3 月内)

4. **ルーティング分割** (`app/routes/` 構成)
5. **MCP サーバー実装**
6. **conftest.py テストフィクスチャ整備**

### 🟢 低 (将来)

7. **Redis キャッシュオプション**
8. **WebSocket 認証**
9. **ページネーション改善**

---

## 🎯 まとめ

| 観点 | 評価 | 理由 |
|------|------|------|
| **API 完成度** | ⭐⭐⭐⭐ | 基本機能揃い、型安全。バッチ操作・履歴検索は今後 |
| **テスト品質** | ⭐⭐⭐⭐⭐ | 100% カバレッジ、エッジケース対応 |
| **コード構成** | ⭐⭐⭐⭐ | 関心分離良好、ただし routes.py が大きい |
| **拡張性** | ⭐⭐⭐ | 基盤は堅実、バッチ・検索機能でスケーラビリティ確保が必要 |
| **ドキュメント** | ⭐⭐⭐⭐ | README 充実、API スキーマはすぐ見える |
| **保守性** | ⭐⭐⭐⭐ | 型安全、テスト網完備。ただし分割化で改善余地 |

---

## 最終所見

**radio-web は個人学習目的の完成度高いアプリ**。100% テストカバレッジと堅実な設計が特徴。

**Web app 構築に必要な API は揃っている** が、以下の点で拡張を視野に入れるべき：

1. ✅ **基本 CRUD**: 揃っている
2. ✅ **バッチ処理**: 部分的（`/download/batch` のみ、削除は未対応）
3. ✅ **リアルタイム**: WebSocket で完全対応
4. ⚠️ **検索・フィルタ**: 基本は OK だが、`broadcast` や日付範囲検索は未実装
5. ⚠️ **キャッシュ管理**: 削除は OK だが、状態問い合わせ API がない

**MCP 対応** は理想的だが、プロジェクト規模からすると **優先度は低い**（personal tool 想定）。

**次のステップ:**
- [ ] ジョブ一括削除 API
- [ ] キャッシュ状態 API
- [ ] エラーレスポンス統一
- [ ] routes.py 分割
- [ ] 検索フィルタ拡張 (broadcast, date range)

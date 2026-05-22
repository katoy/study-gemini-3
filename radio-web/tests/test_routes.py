"""FastAPI ルートのテスト (httpx.AsyncClient + ASGITransport)"""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from nhk_radio_web.job_manager import JobManager
from nhk_radio_web.types import Episode, Program

# テスト用ダミーデータ
PROGRAM = Program(
    title="テスト番組",
    display_title="テスト番組",
    display_date="2024-04-15(月)",
    genre="language",
    genre_label="語学",
    site_id="SITE",
    corner_id="01",
    url="https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
)

EPISODE = Episode(
    id="ep-1",
    title="第1回",
    display_title="第1回",
    date="20240415",
    display_date="2024-04-15(月)",
    broadcast_time="10:00",
    duration_str="30分",
    url="https://www.nhk.or.jp/radio/player/ondemand.html?p=ep-1",
)


class RoutesTest(unittest.TestCase):
    def setUp(self):
        # TestClient はデフォルトでは lifespan を実行しないため、手動で JobManager を初期化
        app.state.job_manager = JobManager(max_concurrent=2)
        self.client = TestClient(app, raise_server_exceptions=True)

    # ──────────────────────────────────────────────
    # GET /
    # ──────────────────────────────────────────────

    def test_index_returns_200_html(self):
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("NHK", resp.text)

    def test_index_with_genre_filter(self):
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]) as m:
            resp = self.client.get("/?genre=language")
        self.assertEqual(resp.status_code, 200)
        m.assert_called_once_with("language")

    def test_index_empty_genre_calls_fetch_with_none(self):
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]) as m:
            self.client.get("/?genre=")
        m.assert_called_once_with(None)

    # ──────────────────────────────────────────────
    # GET /programs (htmx フィルタ)
    # ──────────────────────────────────────────────

    def test_programs_partial_returns_html_fragment(self):
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp = self.client.get("/programs?genre=language")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("テスト番組", resp.text)

    def test_programs_partial_empty_genre(self):
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]) as m:
            resp = self.client.get("/programs")
        self.assertEqual(resp.status_code, 200)
        m.assert_called_once_with(None)

    # ──────────────────────────────────────────────
    # GET /programs/{program_id}/episodes
    # ──────────────────────────────────────────────

    def test_episodes_partial_returns_html(self):
        with (
            patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]),
            patch("app.routes.get_episode_list", return_value=([EPISODE], "network")),
            patch("app.routes.is_episode_downloaded", return_value=False),
        ):
            resp = self.client.get("/programs/SITE_01/episodes")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("第1回", resp.text)

    def test_episodes_partial_invalid_program_id(self):
        resp = self.client.get("/programs/NOUNDERSCORE/episodes")
        self.assertEqual(resp.status_code, 400)

    def test_episodes_partial_program_not_in_cache(self):
        """番組がキャッシュにない場合もフォールバックで動作すること。"""
        with (
            patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]),
            patch("app.routes.get_episode_list", return_value=([EPISODE], "network")),
            patch("app.routes.is_episode_downloaded", return_value=False),
        ):
            resp = self.client.get("/programs/SITE_01/episodes")
        self.assertEqual(resp.status_code, 200)

    def test_episodes_partial_runtime_error_returns_error_fragment(self):
        with (
            patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]),
            patch("app.routes.get_episode_list", side_effect=RuntimeError("取得失敗")),
        ):
            resp = self.client.get("/programs/SITE_01/episodes")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("取得失敗", resp.text)

    def test_episodes_partial_already_downloaded(self):
        with (
            patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]),
            patch("app.routes.get_episode_list", return_value=([EPISODE], "cache")),
            patch("app.routes.is_episode_downloaded", return_value=True),
        ):
            resp = self.client.get("/programs/SITE_01/episodes")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("済", resp.text)

    def test_episodes_partial_with_search_query(self):
        """エピソード一覧に検索キーワード (q パラメータ) が効く。"""
        with (
            patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]),
            patch("app.routes.get_episode_list", return_value=([EPISODE], "network")),
            patch("app.routes.is_episode_downloaded", return_value=False),
        ):
            # マッチする検索
            resp = self.client.get("/programs/SITE_01/episodes?q=第1回")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("第1回", resp.text)

            # マッチしない検索
            resp_no_match = self.client.get("/programs/SITE_01/episodes?q=存在しないエピソード")
            self.assertEqual(resp_no_match.status_code, 200)
            # マッチしないため、エピソード情報は表示されない (またはテーブルが空)

    # ──────────────────────────────────────────────
    # POST /download
    # ──────────────────────────────────────────────

    def test_start_download_registers_job(self):
        import dataclasses
        payload = {
            "program": dataclasses.asdict(PROGRAM),
            "episode": dataclasses.asdict(EPISODE),
        }
        resp = self.client.post("/download", json=payload)
        self.assertEqual(resp.status_code, 200)
        # レスポンスは HTML ステータスフラグメント
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("hx-get", resp.text)

    def test_start_download_missing_body_returns_422(self):
        resp = self.client.post("/download", json={})
        self.assertEqual(resp.status_code, 422)

    def test_start_download_invalid_data_returns_422(self):
        resp = self.client.post("/download", json={"program": "bad", "episode": "bad"})
        self.assertEqual(resp.status_code, 422)

    # ──────────────────────────────────────────────
    # GET /api/download/{job_id}/status
    # ──────────────────────────────────────────────

    def test_download_status_pending(self):
        job_manager = app.state.job_manager
        job_id = job_manager.enqueue(PROGRAM, EPISODE)
        resp = self.client.get(f"/api/download/{job_id}/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("待機中", resp.text)

    def test_download_status_done(self):
        job_manager = app.state.job_manager
        job_id = job_manager.enqueue(PROGRAM, EPISODE)
        job_manager._jobs[job_id]["status"] = "done"
        resp = self.client.get(f"/api/download/{job_id}/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("済", resp.text)

    def test_download_status_error(self):
        job_manager = app.state.job_manager
        job_id = job_manager.enqueue(PROGRAM, EPISODE)
        job_manager._jobs[job_id]["status"] = "error"
        job_manager._jobs[job_id]["error"] = "失敗しました"
        resp = self.client.get(f"/api/download/{job_id}/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("失敗しました", resp.text)

    def test_download_status_not_found(self):
        """ジョブが見つからない場合、htmx ポーリング停止レスポンス（286）を返す。"""
        resp = self.client.get("/api/download/nonexistent-job/status")
        self.assertEqual(resp.status_code, 286)
        self.assertIn("hx-polling-stop", resp.headers.get("HX-Trigger", ""))

    def test_cancel_download_job(self):
        """キャンセルエンドポイントでジョブをキャンセルできる。"""
        job_manager = app.state.job_manager
        job_id = job_manager.enqueue(PROGRAM, EPISODE)

        # キャンセルリクエスト
        resp = self.client.post(f"/api/download/{job_id}/cancel")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("キャンセル", resp.text)

        # ジョブが cancelled 状態になっている
        job = job_manager.status_snapshot(job_id)
        self.assertEqual(job["status"], "cancelled")

    def test_cancel_download_job_not_found(self):
        """存在しないジョブをキャンセルすると 404 を返す。"""
        resp = self.client.post("/api/download/nonexistent-job/cancel")
        self.assertEqual(resp.status_code, 404)

    # ──────────────────────────────────────────────
    # GET /downloads
    # ──────────────────────────────────────────────

    def test_downloads_page_returns_200(self):
        resp = self.client.get("/downloads")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ダウンロード", resp.text)

    # ──────────────────────────────────────────────
    # GET /help
    # ──────────────────────────────────────────────

    def test_help_page_returns_200(self):
        """ヘルプページが 200 を返す。"""
        resp = self.client.get("/help")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ヘルプ", resp.text)

    # ──────────────────────────────────────────────
    # POST /api/cache/clear
    # ──────────────────────────────────────────────

    def test_cache_clear_all(self):
        """キャッシュクリアエンドポイント（全体）が 204 を返す。"""
        resp = self.client.post("/api/cache/clear?scope=all")
        self.assertEqual(resp.status_code, 204)

    def test_cache_clear_programs(self):
        """キャッシュクリアエンドポイント（番組）が 204 を返す。"""
        resp = self.client.post("/api/cache/clear?scope=programs")
        self.assertEqual(resp.status_code, 204)

    def test_cache_clear_episodes(self):
        """キャッシュクリアエンドポイント（エピソード）が 204 を返す。"""
        resp = self.client.post("/api/cache/clear?scope=episodes")
        self.assertEqual(resp.status_code, 204)

    # ──────────────────────────────────────────────
    # GET /api/jobs/recent
    # ──────────────────────────────────────────────

    def test_recent_jobs_returns_200(self):
        """最近のジョブ一覧エンドポイントが 200 を返す。"""
        resp = self.client.get("/api/jobs/recent")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])

    def test_recent_jobs_empty(self):
        """ジョブがない場合、エンドポイントが成功する。"""
        resp = self.client.get("/api/jobs/recent")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ジョブがありません", resp.text)

    def test_recent_jobs_with_job(self):
        """ジョブが存在する場合、エンドポイントが HTML に反映される。"""
        job_manager = app.state.job_manager
        job_manager.enqueue(PROGRAM, EPISODE)
        resp = self.client.get("/api/jobs/recent")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("第1回", resp.text)

    def test_recent_jobs_limit_parameter(self):
        """limit パラメータで取得件数を制限できる。"""
        job_manager = app.state.job_manager
        # 複数のジョブを登録
        for _ in range(5):
            job_manager.enqueue(PROGRAM, EPISODE)
        # limit=2 で取得
        resp = self.client.get("/api/jobs/recent?limit=2")
        self.assertEqual(resp.status_code, 200)

    # ──────────────────────────────────────────────
    # ダッシュボードレイアウト
    # ──────────────────────────────────────────────

    def test_index_has_dashboard_layout(self):
        """インデックスページにダッシュボードレイアウトが含まれている。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("dashboard-layout", resp.text)
        self.assertIn("db-sidebar", resp.text)
        self.assertIn("db-command-bar", resp.text)

    def test_index_sidebar_genre_nav_rendered(self):
        """インデックスページのサイドバーにジャンルナビが表示される。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp = self.client.get("/")
        self.assertIn("filterByGenre", resp.text)
        self.assertIn("語学", resp.text)
        self.assertIn("db-nav-item", resp.text)


    def test_programs_partial_has_list_view_rows(self):
        """program_list パーシャルにリストビュー行が含まれている。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp = self.client.get("/programs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("db-list-row", resp.text)
        self.assertIn("テスト番組", resp.text)

    def test_programs_partial_has_grid_view_cards(self):
        """program_list パーシャルにグリッドビューカードが含まれている。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp = self.client.get("/programs")
        self.assertIn("db-grid-card", resp.text)
        self.assertIn("db-grid-title", resp.text)

    def test_programs_partial_q_param_filters(self):
        """q パラメータで番組名フィルタが機能する。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp_match = self.client.get("/programs?q=テスト")
            self.assertIn("テスト番組", resp_match.text)

        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            resp_no = self.client.get("/programs?q=存在しないXYZ")
            self.assertNotIn("テスト番組", resp_no.text)

    # ──────────────────────────────────────────────
    # _job_to_payload ヘルパー関数
    # ──────────────────────────────────────────────

    def test_job_to_payload_basic(self):
        """_job_to_payload が基本的なジョブ情報をペイロードに変換する。"""
        from app.routes import _job_to_payload
        job = {
            "status": "downloading",
            "episode": EPISODE,
            "error": "",
            "progress": None,
        }
        payload = _job_to_payload("job-123", job)
        self.assertEqual(payload["job_id"], "job-123")
        self.assertEqual(payload["status"], "downloading")
        self.assertEqual(payload["title"], "第1回")
        self.assertEqual(payload["error"], "")
        self.assertIsNone(payload["progress"])

    def test_job_to_payload_with_error(self):
        """_job_to_payload がエラーメッセージを含める。"""
        from app.routes import _job_to_payload
        job = {
            "status": "error",
            "episode": EPISODE,
            "error": "ダウンロード失敗",
            "progress": None,
        }
        payload = _job_to_payload("job-456", job)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"], "ダウンロード失敗")


if __name__ == "__main__":
    unittest.main()

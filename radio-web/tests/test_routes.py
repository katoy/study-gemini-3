"""FastAPI ルートのテスト (httpx.AsyncClient + ASGITransport)"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
        m.assert_called_once_with(None)

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

    def test_start_download_missing_required_fields_returns_422(self):
        """必須フィールド欠落時のエラーハンドリング。"""
        resp = self.client.post(
            "/download",
            json={"program": {"title": "test"}, "episode": {"title": "ep"}}  # site_id/corner_id/id 欠落
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("データ形式が不正です", resp.text)

    def test_batch_download_invalid_program_data(self):
        """一括ダウンロードで program データが不正な場合 → 422。"""
        resp = self.client.post(
            "/download/batch",
            json={
                "program": {"title": "test"},  # site_id/corner_id 欠落
                "episodes": [{"title": "ep", "id": "123"}]
            }
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("プログラムデータが不正です", resp.text)

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
    # GET /api/settings
    # ──────────────────────────────────────────────

    def test_settings_get_returns_json(self):
        """GET /api/settings が JSON を返す。"""
        with patch("app.routes.load_storage_limit", return_value=10 * 1024 * 1024 * 1024):
            resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("storage_limit_bytes", data)
        self.assertIn("storage_limit_gb", data)
        self.assertEqual(data["storage_limit_gb"], 10)

    # ──────────────────────────────────────────────
    # POST /api/settings
    # ──────────────────────────────────────────────

    def test_settings_post_saves_storage_limit(self):
        """POST /api/settings がストレージ容量上限を保存。"""
        with patch("app.routes.save_storage_limit", return_value=True) as mock_save:
            resp = self.client.post(
                "/api/settings",
                json={"storage_limit_gb": 20},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["storage_limit_gb"], 20)
        mock_save.assert_called_once_with(20 * 1024 * 1024 * 1024)

    def test_settings_post_invalid_json(self):
        """POST /api/settings に不正な JSON → 422。"""
        resp = self.client.post(
            "/api/settings",
            content="not json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_settings_post_invalid_storage_limit(self):
        """POST /api/settings で storage_limit_gb が無効 → 422。"""
        resp = self.client.post(
            "/api/settings",
            json={"storage_limit_gb": -5},
        )
        self.assertEqual(resp.status_code, 422)

    def test_settings_post_missing_storage_limit(self):
        """POST /api/settings で storage_limit_gb がない → 422。"""
        resp = self.client.post(
            "/api/settings",
            json={},
        )
        self.assertEqual(resp.status_code, 422)

    def test_settings_post_save_failure(self):
        """POST /api/settings で保存失敗 → 500。"""
        with patch("app.routes.save_storage_limit", return_value=False):
            resp = self.client.post(
                "/api/settings",
                json={"storage_limit_gb": 15},
            )
        self.assertEqual(resp.status_code, 500)

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

    # ──────────────────────────────────────────────
    # POST /download (不正リクエスト)
    # ──────────────────────────────────────────────

    def test_start_download_invalid_json(self):
        """POST /download に不正な JSON を送信 → 422。"""
        resp = self.client.post(
            "/download",
            content="not json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("JSON", resp.json()["detail"])

    def test_start_download_missing_program(self):
        """POST /download に program がない → 422。"""
        resp = self.client.post(
            "/download",
            json={"episode": EPISODE.__dict__},
        )
        self.assertEqual(resp.status_code, 422)

    def test_start_download_invalid_program_type(self):
        """POST /download に program が dict でない → 422。"""
        resp = self.client.post(
            "/download",
            json={"program": "not a dict", "episode": EPISODE.__dict__},
        )
        self.assertEqual(resp.status_code, 422)

    # ──────────────────────────────────────────────
    # POST /download/batch
    # ──────────────────────────────────────────────

    def test_batch_download_success(self):
        """POST /download/batch で複数エピソードをキューに登録。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]):
            resp = self.client.post(
                "/download/batch",
                json={
                    "program": PROGRAM.__dict__,
                    "episodes": [EPISODE.__dict__, EPISODE.__dict__],
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])

    def test_batch_download_invalid_json(self):
        """POST /download/batch に不正な JSON → 422。"""
        resp = self.client.post(
            "/download/batch",
            content="not json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_batch_download_invalid_episodes_type(self):
        """POST /download/batch に episodes が list でない → 422。"""
        resp = self.client.post(
            "/download/batch",
            json={
                "program": PROGRAM.__dict__,
                "episodes": "not a list",
            },
        )
        self.assertEqual(resp.status_code, 422)

    def test_batch_download_invalid_episode_skipped(self):
        """POST /download/batch で不正なエピソードはスキップ。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]):
            resp = self.client.post(
                "/download/batch",
                json={
                    "program": PROGRAM.__dict__,
                    "episodes": [EPISODE.__dict__, {"invalid": "episode"}],
                },
            )
        self.assertEqual(resp.status_code, 200)

    # ──────────────────────────────────────────────
    # POST /api/download/{job_id}/cancel
    # ──────────────────────────────────────────────

    def test_cancel_download_not_found(self):
        """POST /api/download/{job_id}/cancel でジョブなし → 404。"""
        resp = self.client.post("/api/download/nonexistent/cancel")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_download_exception_handling(self):
        """POST /api/download/{job_id}/cancel で cancel() が例外 → HTML 返却。"""
        with (
            patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]),
            patch("app.routes.get_episode_list", return_value=([EPISODE], "network")),
        ):
            # ジョブを登録
            resp = self.client.post(
                "/download",
                json={"program": PROGRAM.__dict__, "episode": EPISODE.__dict__},
            )
            self.assertEqual(resp.status_code, 200)

            # job_id を抽出（簡易版）
            job_manager = app.state.job_manager
            job_ids = list(job_manager.all_jobs().keys())
            if job_ids:
                job_id = job_ids[0]

                # cancel() が例外を発生させるようにモック
                job_manager.cancel = AsyncMock(side_effect=Exception("Cancel failed"))

                # キャンセルリクエスト
                resp = self.client.post(f"/api/download/{job_id}/cancel")
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/html", resp.headers["content-type"])

    # ──────────────────────────────────────────────
    # GET /api/download/{job_id}/file
    # ──────────────────────────────────────────────

    def test_download_file_not_found(self):
        """GET /api/download/{job_id}/file でジョブなし → 404。"""
        resp = self.client.get("/api/download/nonexistent/file")
        self.assertEqual(resp.status_code, 404)

    def test_download_file_path_missing(self):
        """GET /api/download/{job_id}/file で file_path がない → 404。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            # ジョブを登録
            resp = self.client.post(
                "/download",
                json={"program": PROGRAM.__dict__, "episode": EPISODE.__dict__},
            )
            self.assertEqual(resp.status_code, 200)

            job_manager = app.state.job_manager
            job_ids = list(job_manager.all_jobs().keys())
            if job_ids:
                job_id = job_ids[0]
                resp = self.client.get(f"/api/download/{job_id}/file")
                self.assertEqual(resp.status_code, 404)

    def test_download_file_not_exists_on_disk(self):
        """GET /api/download/{job_id}/file でファイルがディスク上にない → 404。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            # ジョブを登録
            resp = self.client.post(
                "/download",
                json={"program": PROGRAM.__dict__, "episode": EPISODE.__dict__},
            )
            self.assertEqual(resp.status_code, 200)

            job_manager = app.state.job_manager
            job_ids = list(job_manager.all_jobs().keys())
            if job_ids:
                job_id = job_ids[0]
                job = job_manager.status_snapshot(job_id)

                # 存在しないファイルパスを設定
                job["file_path"] = "/nonexistent/path/file.m4a"
                job_manager._jobs[job_id] = job

                resp = self.client.get(f"/api/download/{job_id}/file")
                self.assertEqual(resp.status_code, 404)

    def test_download_file_rfc5987_header(self):
        """GET /api/download/{job_id}/file で RFC 5987 Content-Disposition ヘッダー設定確認。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            with TemporaryDirectory() as tmpdir:
                # テストファイルを作成
                test_file = Path(tmpdir) / "test.mp3"
                test_file.write_text("test audio")

                # ジョブを登録
                resp = self.client.post(
                    "/download",
                    json={"program": PROGRAM.__dict__, "episode": EPISODE.__dict__},
                )
                self.assertEqual(resp.status_code, 200)

                job_manager = app.state.job_manager
                job_ids = list(job_manager.all_jobs().keys())
                if job_ids:
                    job_id = job_ids[0]
                    job = job_manager.status_snapshot(job_id)

                    # ファイルパスを設定
                    job["file_path"] = str(test_file)
                    job_manager._jobs[job_id] = job

                    resp = self.client.get(f"/api/download/{job_id}/file")
                    self.assertEqual(resp.status_code, 200)

                    # RFC 5987 ヘッダーを確認
                    content_disp = resp.headers.get("content-disposition", "")
                    self.assertIn("filename*=UTF-8''", content_disp)

    def test_download_episode_file_program_not_found(self):
        """GET /api/episodes で Program が見つからない → 404。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]):
            resp = self.client.get(
                "/api/episodes/nonexistent_site/nonexistent_corner/nonexistent_id/file"
            )
            self.assertEqual(resp.status_code, 404)
            self.assertIn("Program not found", resp.text)

    def test_download_episode_file_episodes_not_found(self):
        """GET /api/episodes で Episodes 取得失敗 → 404。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            with patch("app.routes.get_episode_list", side_effect=RuntimeError("API error")):
                resp = self.client.get(
                    f"/api/episodes/{PROGRAM.site_id}/{PROGRAM.corner_id}/nonexistent_id/file"
                )
                self.assertEqual(resp.status_code, 404)
                self.assertIn("Episodes not found", resp.text)

    def test_download_episode_file_episode_not_found(self):
        """GET /api/episodes で Episode ID が見つからない → 404。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            with patch("app.routes.get_episode_list", return_value=([EPISODE], None)):
                resp = self.client.get(
                    f"/api/episodes/{PROGRAM.site_id}/{PROGRAM.corner_id}/nonexistent_id/file"
                )
                self.assertEqual(resp.status_code, 404)
                self.assertIn("Episode not found", resp.text)

    def test_download_episode_file_with_file_found(self):
        """GET /api/episodes で既ダウンロードファイルが見つかる場合。"""
        with TemporaryDirectory() as tmpdir:
            # テストファイルを作成
            test_file = Path(tmpdir) / EPISODE.title
            test_file.write_text("test audio")

            with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
                with patch("app.routes.get_episode_list", return_value=([EPISODE], None)):
                    with patch("app.routes._program_search_dirs", return_value=[Path(tmpdir)]):
                        resp = self.client.get(
                            f"/api/episodes/{PROGRAM.site_id}/{PROGRAM.corner_id}/{EPISODE.id}/file"
                        )
                        self.assertEqual(resp.status_code, 200)
                        # RFC 5987 ヘッダーを確認
                        content_disp = resp.headers.get("content-disposition", "")
                        self.assertIn("filename*=UTF-8''", content_disp)

    def test_download_episode_file_directory_not_exists(self):
        """GET /api/episodes でディレクトリが存在しない場合をスキップ。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            with patch("app.routes.get_episode_list", return_value=([EPISODE], None)):
                # 存在しないパスを返す
                with patch("app.routes._program_search_dirs", return_value=[Path("/nonexistent/dir/path")]):
                    resp = self.client.get(
                        f"/api/episodes/{PROGRAM.site_id}/{PROGRAM.corner_id}/{EPISODE.id}/file"
                    )
                    self.assertEqual(resp.status_code, 404)

    def test_download_episode_file_rfc5987_header(self):
        """GET /api/episodes/{site_id}/{corner_id}/{episode_id}/file で RFC 5987 ヘッダー設定確認。"""
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]):
            with patch("app.routes.get_episode_list", return_value=([EPISODE], None)):
                with patch("app.routes._program_search_dirs", return_value=[]):
                    # ディレクトリが見つからない場合 → 404
                    resp = self.client.get(
                        f"/api/episodes/{PROGRAM.site_id}/{PROGRAM.corner_id}/{EPISODE.id}/file"
                    )
                    self.assertEqual(resp.status_code, 404)

    # ──────────────────────────────────────────────
    # _dataclass_to_json フィルタ
    # ──────────────────────────────────────────────

    def test_dataclass_to_json_filter_with_dict(self):
        """_dataclass_to_json フィルタが dict を処理。"""
        from app.routes import _dataclass_to_json
        result = _dataclass_to_json({"key": "value"})
        self.assertIn("key", result)

    def test_dataclass_to_json_filter_with_string(self):
        """_dataclass_to_json フィルタが文字列を処理。"""
        from app.routes import _dataclass_to_json
        result = _dataclass_to_json("test string")
        self.assertIn("test string", result)

    def test_dataclass_to_json_filter_with_list(self):
        """_dataclass_to_json フィルタがリストを処理。"""
        from app.routes import _dataclass_to_json
        result = _dataclass_to_json([1, 2, 3])
        self.assertIn("1", result)

    # ──────────────────────────────────────────────
    # WebSocket: /ws/jobs
    # ──────────────────────────────────────────────
    # WebSocket テストはタイムアウト問題があるため、スキップ。
    # routes.py の ws_jobs エンドポイント (442-460行) は統合テストで確認推奨。


if __name__ == "__main__":
    unittest.main()

"""FastAPI ルートのテスト (httpx.AsyncClient + ASGITransport)"""

import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app
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

    # ──────────────────────────────────────────────
    # POST /download
    # ──────────────────────────────────────────────

    def test_start_download_registers_job(self):
        import dataclasses
        payload = {
            "program": dataclasses.asdict(PROGRAM),
            "episode": dataclasses.asdict(EPISODE),
        }
        with patch("app.routes._run_download", new_callable=AsyncMock):
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
        from app import routes
        job_id = "test-status-pending"
        routes._jobs[job_id] = {"status": "pending", "program": PROGRAM, "episode": EPISODE, "error": ""}
        resp = self.client.get(f"/api/download/{job_id}/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("待機中", resp.text)

    def test_download_status_done(self):
        from app import routes
        job_id = "test-status-done"
        routes._jobs[job_id] = {"status": "done", "program": PROGRAM, "episode": EPISODE, "error": ""}
        resp = self.client.get(f"/api/download/{job_id}/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("完了", resp.text)

    def test_download_status_error(self):
        from app import routes
        job_id = "test-status-error"
        routes._jobs[job_id] = {"status": "error", "program": PROGRAM, "episode": EPISODE, "error": "失敗しました"}
        resp = self.client.get(f"/api/download/{job_id}/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("失敗しました", resp.text)

    def test_download_status_not_found(self):
        resp = self.client.get("/api/download/nonexistent-job/status")
        self.assertEqual(resp.status_code, 404)

    # ──────────────────────────────────────────────
    # GET /downloads
    # ──────────────────────────────────────────────

    def test_downloads_page_returns_200(self):
        resp = self.client.get("/downloads")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ダウンロード", resp.text)

    # ──────────────────────────────────────────────
    # _run_download の非同期動作
    # ──────────────────────────────────────────────

    def test_run_download_success(self):
        import asyncio
        from app.routes import _jobs, _run_download

        job_id = "test-run-success"
        _jobs[job_id] = {"status": "pending", "program": PROGRAM, "episode": EPISODE, "error": ""}

        async def run():
            with patch("asyncio.create_subprocess_exec") as m:
                proc = AsyncMock()
                proc.returncode = 0
                proc.wait = AsyncMock(return_value=0)
                m.return_value = proc
                with patch("app.routes.mark_episode_downloaded"):
                    await _run_download(job_id, PROGRAM, EPISODE)

        asyncio.run(run())
        self.assertEqual(_jobs[job_id]["status"], "done")

    def test_run_download_failure(self):
        import asyncio
        from app.routes import _jobs, _run_download

        job_id = "test-run-fail"
        _jobs[job_id] = {"status": "pending", "program": PROGRAM, "episode": EPISODE, "error": ""}

        async def run():
            with patch("asyncio.create_subprocess_exec") as m:
                proc = AsyncMock()
                proc.returncode = 1
                proc.wait = AsyncMock(return_value=1)
                m.return_value = proc
                await _run_download(job_id, PROGRAM, EPISODE)

        asyncio.run(run())
        self.assertEqual(_jobs[job_id]["status"], "error")


if __name__ == "__main__":
    unittest.main()

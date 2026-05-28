import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.routes import _job_to_api_data, ws_jobs
from nhk_radio_web import cache, config, core, downloads
from nhk_radio_web.job_manager import JobManager
from nhk_radio_web.types import Episode, Program

PROGRAM = Program(
    title="番組A",
    display_title="番組A",
    display_date="2024-04-15(月)",
    genre="language",
    genre_label="語学",
    site_id="SITE",
    corner_id="01",
    url="https://example.com/program",
)

UNCLASSIFIED_PROGRAM = Program(
    title="番組B",
    display_title="番組B",
    display_date="2024-04-16(火)",
    site_id="SITE",
    corner_id="02",
    url="https://example.com/program2",
)

EPISODE = Episode(
    id="ep-1",
    title="第1回",
    display_title="第1回",
    date="20240415",
    display_date="2024-04-15(月)",
    broadcast_time="10:00",
    duration_str="30分",
    url="https://example.com/episode",
)


class RoutesCoverageTest(unittest.TestCase):
    def setUp(self):
        app.state.job_manager = JobManager(max_concurrent=2)
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_job_to_api_data_includes_file_path(self):
        payload = _job_to_api_data(
            "job-1",
            {
                "status": "done",
                "program": PROGRAM,
                "episode": EPISODE,
                "error": "",
                "progress": None,
                "file_path": "/tmp/test.mp3",
            },
        )
        self.assertEqual(payload.file_path, "/tmp/test.mp3")

    def test_api_v1_program_episode_error_paths(self):
        with patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[]):
            resp = self.client.get("/api/v1/programs/SITE_01/episodes/ep-1")
        self.assertEqual(resp.status_code, 404)

        with (
            patch("app.routes.fetch_program_list_async", new_callable=AsyncMock, return_value=[PROGRAM]),
            patch("app.routes.get_episode_list", side_effect=RuntimeError("failure")),
        ):
            resp = self.client.get("/api/v1/programs/SITE_01/episodes/ep-1")
        self.assertEqual(resp.status_code, 502)

    def test_api_v1_create_download_job_validation_errors(self):
        resp = self.client.post(
            "/api/v1/download-jobs",
            json={"program": "bad", "episode": "bad"},
        )
        self.assertEqual(resp.status_code, 422)

        resp = self.client.post(
            "/api/v1/download-jobs",
            json={"program": {"title": "bad"}, "episode": {"title": "bad"}},
        )
        self.assertEqual(resp.status_code, 422)

    def test_api_v1_settings_invalid_json(self):
        resp = self.client.put(
            "/api/v1/settings",
            content="not json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_ws_jobs_direct(self):
        class FakeQueue:
            def __init__(self):
                self._calls = 0

            async def get(self):
                if self._calls == 0:
                    self._calls += 1
                    return {
                        "job_id": "job-live",
                        "status": "done",
                        "title": "ライブ",
                        "error": "",
                        "progress": None,
                    }
                raise WebSocketDisconnect()

        class FakeJobManager:
            def __init__(self):
                self.queue = FakeQueue()
                self.unsubscribed = None

            def all_jobs(self):
                return {
                    "job-existing": {
                        "status": "pending",
                        "program": PROGRAM,
                        "episode": EPISODE,
                        "error": "",
                        "progress": None,
                    }
                }

            def subscribe(self):
                return self.queue

            def unsubscribe(self, queue):
                self.unsubscribed = queue

        class FakeWebSocket:
            def __init__(self, job_manager):
                self.app = SimpleNamespace(state=SimpleNamespace(job_manager=job_manager))
                self.sent = []
                self.accepted = False

            async def accept(self):
                self.accepted = True

            async def send_text(self, text: str):
                self.sent.append(json.loads(text))

        job_manager = FakeJobManager()
        websocket = FakeWebSocket(job_manager)
        asyncio.run(ws_jobs(websocket))

        self.assertTrue(websocket.accepted)
        self.assertEqual(websocket.sent[0]["job_id"], "job-existing")
        self.assertEqual(websocket.sent[1]["job_id"], "job-live")
        self.assertIs(job_manager.unsubscribed, job_manager.queue)


class CacheCoverageTest(unittest.TestCase):
    def test_save_json_cache_cleans_up_temp_file_on_replace_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            with patch("pathlib.Path.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    cache._save_json_cache(cache_path, {"fetched_at": 1, "items": []})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_clear_cache_dir_skips_directory_named_like_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            (cache_dir / "nested.json").mkdir()
            self.assertEqual(cache._clear_cache_dir(cache_dir), 0)

    def test_get_cache_status_nonexistent_dir(self):
        """キャッシュディレクトリが存在しない場合"""
        with patch("nhk_radio_web.config._resolve_cache_root_dir") as mock_resolve:
            mock_resolve.return_value = Path("/nonexistent/cache")
            status = cache.get_cache_status()
            self.assertEqual(status["size_bytes"], 0)
            self.assertEqual(status["last_modified"], 0)

    def test_get_cache_status_with_files(self):
        """キャッシュファイルが存在する場合"""
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cache_file = cache_dir / "cache.json"
            cache_file.write_text('{"data": []}')

            with patch("nhk_radio_web.config._resolve_cache_root_dir") as mock_resolve:
                mock_resolve.return_value = cache_dir
                status = cache.get_cache_status()
                self.assertGreater(status["size_bytes"], 0)
                self.assertGreater(status["last_modified"], 0)


class ConfigCoverageTest(unittest.TestCase):
    def test_default_user_cache_root_non_darwin(self):
        with patch.object(config.sys, "platform", "linux"):
            root = config._default_user_cache_root()
        self.assertEqual(root.name, "nhk_radio_web")

    def test_find_project_root_returns_none(self):
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.is_dir", return_value=False),
        ):
            self.assertIsNone(config._find_project_root())

    def test_save_storage_limit_with_invalid_existing_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            settings_file.write_text("{bad", encoding="utf-8")
            with patch("nhk_radio_web.config._settings_path", return_value=settings_file):
                self.assertTrue(config.save_storage_limit(123))
            payload = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["storage_limit_bytes"], 123)


class CoreCoverageTest(unittest.TestCase):
    def test_http_get_json_async_429_paths(self):
        async def run_success():
            client = AsyncMock(spec=httpx.AsyncClient)
            retry_response = Mock()
            retry_response.headers = {"Retry-After": "0"}
            retry_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429",
                request=Mock(),
                response=Mock(status_code=429, headers={"Retry-After": "0"}),
            )
            success_response = Mock()
            success_response.raise_for_status.return_value = None
            success_response.json.return_value = {"ok": True}
            client.get.side_effect = [retry_response, success_response]
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await core.http_get_json_async(client, "https://example.com")
            self.assertEqual(result, {"ok": True})

        async def run_exhausted():
            client = AsyncMock(spec=httpx.AsyncClient)
            response = Mock()
            response.headers = {"Retry-After": "0"}
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429",
                request=Mock(),
                response=Mock(status_code=429, headers={"Retry-After": "0"}),
            )
            client.get.return_value = response
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaises(httpx.HTTPStatusError):
                    await core.http_get_json_async(client, "https://example.com")

        asyncio.run(run_success())
        asyncio.run(run_exhausted())

    def test_http_get_text_error(self):
        with patch("httpx.Client") as client_mock:
            instance = client_mock.return_value.__enter__.return_value
            instance.get.side_effect = httpx.HTTPError("text error")
            with self.assertRaises(httpx.HTTPError):
                core.http_get_text("https://example.com")

    def test_fetch_program_list_async_and_fetch_all_async_cache_edges(self):
        cached = [PROGRAM]

        async def run_cached_after_lock():
            with (
                patch.object(core, "load_program_cache", side_effect=[None, cached]),
                patch.object(core, "_get_cache_write_lock_async", new_callable=AsyncMock, return_value=asyncio.Lock()),
            ):
                result = await core.fetch_program_list_async("language")
            self.assertEqual(result, cached)

        async def run_new_arrivals():
            with (
                patch.object(core, "NHK_GENRES", []),
                patch.object(
                    core,
                    "http_get_json_async",
                    new_callable=AsyncMock,
                    return_value={"corners": [{"series_site_id": "SITE", "corner_site_id": "01", "title": "番組A"}]},
                ),
            ):
                result = await core._fetch_all_async()
            self.assertEqual(result[0].site_id, "SITE")

        asyncio.run(run_cached_after_lock())
        asyncio.run(run_new_arrivals())

    def test_fetch_by_genre_async_non_dict_and_parse_episode_fallbacks(self):
        with patch.object(core, "http_get_json_async", new_callable=AsyncMock, return_value=[]):
            result = asyncio.run(core._fetch_by_genre_async("language"))
        self.assertEqual(result, [])

        parsed = core._parse_episode_info(
            {"title": "第1回", "webpage_url": "https://example.com/web"},
            PROGRAM,
        )
        self.assertEqual(parsed.url, "https://example.com/web")

    def test_fetch_episodes_verbose_and_download_error_mappings(self):
        with patch("yt_dlp.YoutubeDL") as ydl_mock, patch("nhk_radio_web.core.logger") as logger_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.return_value = {
                "entries": [{"id": "ep-1", "title": "第1回", "url": "https://example.com/ep1"}]
            }
            episodes = core.fetch_episodes(PROGRAM, verbose=True)
        self.assertEqual(len(episodes), 1)
        self.assertGreaterEqual(logger_mock.info.call_count, 2)

        error_cases = [
            ("ffmpeg missing", "ffmpeg が見つからないか、エラーが発生しました。"),
            ("connection timeout", "ネットワーク接続に失敗しました。"),
            ("other failure", "番組情報の解析に失敗しました: other failure"),
        ]
        for message, expected in error_cases:
            with patch("yt_dlp.YoutubeDL") as ydl_mock:
                instance = ydl_mock.return_value.__enter__.return_value
                instance.extract_info.side_effect = core.yt_dlp.utils.DownloadError(message)
                with self.assertRaisesRegex(RuntimeError, expected):
                    core.fetch_episodes(PROGRAM, verbose=False)

    def test_refresh_episode_list_remaining_paths(self):
        async def run_cached():
            with patch.object(core, "load_episode_cache", return_value=[EPISODE]):
                result = await core.refresh_episode_list(PROGRAM)
            self.assertEqual(result, ([EPISODE], "cache"))

        async def run_save_failure():
            with (
                patch.object(core, "load_episode_cache", return_value=None),
                patch.object(core, "fetch_episodes", return_value=[EPISODE]),
                patch.object(core, "save_episode_cache", side_effect=OSError("disk full")),
            ):
                result = await core.refresh_episode_list(PROGRAM)
            self.assertEqual(result, ([EPISODE], "network"))

        async def run_total_failure():
            with (
                patch.object(core, "load_episode_cache", return_value=None),
                patch.object(core, "fetch_episodes", side_effect=[Exception("first"), Exception("second")]),
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                with self.assertRaisesRegex(RuntimeError, "second"):
                    await core.refresh_episode_list(PROGRAM)

        asyncio.run(run_cached())
        asyncio.run(run_save_failure())
        asyncio.run(run_total_failure())


class DownloadsCoverageTest(unittest.TestCase):
    def test_get_cached_glob_files_stat_error_and_lru(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            with (
                patch("pathlib.Path.is_dir", return_value=True),
                patch("pathlib.Path.stat", side_effect=OSError("stat failed")),
            ):
                self.assertEqual(downloads._get_cached_glob_files(target), [])

            downloads._clear_file_scan_cache()
            first = target / "first"
            second = target / "second"
            first.mkdir()
            second.mkdir()
            (first / "a.mp3").write_text("a", encoding="utf-8")
            (second / "b.mp3").write_text("b", encoding="utf-8")
            with patch.object(downloads, "_FILE_SCAN_CACHE_MAX_SIZE", 1):
                first_files = downloads._get_cached_glob_files(first)
                cached_first_files = downloads._get_cached_glob_files(first)
                second_files = downloads._get_cached_glob_files(second)
            self.assertEqual(first_files, cached_first_files)
            self.assertEqual(len(second_files), 1)
            self.assertEqual(len(downloads._FILE_SCAN_CACHE), 1)

    def test_download_lookup_negative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            self.assertFalse(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))
            self.assertIsNone(downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE))

    def test_is_episode_downloaded_via_directory_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            (program_dir / "20240415_番組A_第1回.mp3").write_text("x", encoding="utf-8")
            self.assertTrue(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))

    def test_cleanup_partial_episode_files_error_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            partial = program_dir / "20240415_番組A_第1回.mp3.part"
            partial.write_text("partial", encoding="utf-8")

            with patch.object(Path, "iterdir", side_effect=OSError("denied")):
                downloads.cleanup_partial_episode_files(output_dir, PROGRAM, EPISODE)

            with patch.object(Path, "unlink", side_effect=OSError("denied")):
                downloads.cleanup_partial_episode_files(output_dir, PROGRAM, EPISODE)

    def test_evict_old_files_error_paths_and_format_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            target = download_dir / "file.mp3"
            target.write_text("x" * 10, encoding="utf-8")

            deleted = downloads.evict_old_files(download_dir, 0)
            self.assertEqual(deleted, [])

            with (
                patch.object(downloads, "get_download_dir_size", return_value=100),
                patch("pathlib.Path.exists", return_value=True),
                patch("pathlib.Path.rglob", return_value=[target]),
                patch("pathlib.Path.is_file", return_value=True),
                patch("pathlib.Path.stat", side_effect=OSError("bad stat")),
            ):
                deleted = downloads.evict_old_files(download_dir, 1)
            self.assertEqual(deleted, [])

            with (
                patch.object(downloads, "get_download_dir_size", return_value=100),
                patch("pathlib.Path.exists", return_value=True),
                patch("pathlib.Path.rglob", return_value=[target]),
                patch("pathlib.Path.is_file", return_value=True),
                patch("pathlib.Path.stat", return_value=SimpleNamespace(st_mtime=1, st_size=10)),
                patch.object(Path, "unlink", side_effect=OSError("cannot delete")),
            ):
                deleted = downloads.evict_old_files(download_dir, 1)
            self.assertEqual(deleted, [])

            with (
                patch.object(downloads, "get_download_dir_size", return_value=100),
                patch("pathlib.Path.exists", return_value=True),
                patch("pathlib.Path.rglob", side_effect=OSError("scan failed")),
            ):
                deleted = downloads.evict_old_files(download_dir, 1)
            self.assertEqual(deleted, [])

        self.assertEqual(downloads._format_download_percent(None), "--%")
        self.assertEqual(downloads._format_download_percent(10.24), "10.2%")
        self.assertEqual(downloads._format_download_percent(100.0), "100%")
        self.assertEqual(downloads._format_download_eta(None), "残り --:--")
        self.assertEqual(downloads._format_download_eta("00:12"), "残り 00:12")
        self.assertEqual(downloads._parse_yt_dlp_progress(""), (None, None, None))
        self.assertEqual(downloads._parse_yt_dlp_progress("[ExtractAudio] start"), (100.0, None, "変換中..."))
        self.assertEqual(downloads._parse_yt_dlp_progress("noise"), (None, None, None))

        cmd = downloads._yt_dlp_command(
            "https://example.com",
            "/tmp/out",
            audio_only=True,
            no_playlist=False,
            max_items=3,
        )
        self.assertIn("--playlist-end", cmd)
        self.assertIn("3", cmd)


if __name__ == "__main__":
    unittest.main()

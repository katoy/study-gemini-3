import unittest
import tempfile
import json
import os
import subprocess
import httpx
import yt_dlp
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from nhk_radio import downloads, text, config, cache, cli, core
from nhk_radio.types import Program, Episode

class BackendCoverageCompletionTest(unittest.TestCase):
    
    # --- downloads.py ---
    def test_downloads_file_scan_cache_lru_eviction(self):
        # downloads.py: 204 (LRU eviction logic)
        with (
            patch.object(downloads, "_FILE_SCAN_CACHE_MAX_SIZE", 2),
            patch.object(downloads, "_FILE_SCAN_CACHE", downloads.OrderedDict())
        ):
            # 新しい空の OrderedDict でテスト
            d1, d2, d3 = Path("/dir1"), Path("/dir2"), Path("/dir3")
            downloads._FILE_SCAN_CACHE[d1] = (1.0, [])
            downloads._FILE_SCAN_CACHE[d2] = (1.0, [])
            # 3つ目を入れるのは get_cached_glob_files 経由である必要がある (関数内の len チェックを通すため)
            with (
                patch.object(Path, "is_dir", return_value=True),
                patch.object(Path, "stat", return_value=MagicMock(st_mtime=1.0)),
                patch.object(Path, "iterdir", return_value=[])
            ):
                downloads._get_cached_glob_files(d3)
                self.assertEqual(len(downloads._FILE_SCAN_CACHE), 2)
                self.assertNotIn(d1, downloads._FILE_SCAN_CACHE)

    def test_get_cached_glob_files_oserror_on_stat(self):
        # downloads.py: 191 (OSError on stat)
        with patch.object(Path, "stat", side_effect=OSError("denied")):
            self.assertEqual(downloads._get_cached_glob_files(Path("/tmp/any")), [])

    def test_get_cached_glob_files_oserror_on_iterdir(self):
        # downloads.py: 200 (OSError on iterdir)
        with (
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "stat", return_value=MagicMock(st_mtime=1.0)),
            patch.object(Path, "iterdir", side_effect=OSError("iterdir fail")),
            patch.object(downloads, "logger") as log_mock
        ):
            self.assertEqual(downloads._get_cached_glob_files(Path("/tmp/any")), [])
            log_mock.debug.assert_called()

    # --- text.py ---
    def test_format_onair_date_invalid_started_at(self):
        # text.py: 27 (ValueError/TypeError on fromisoformat)
        # started_at が不正な時、onair_date のパースにフォールバックすることを確認
        self.assertEqual(text._format_onair_date("2024-04-15", started_at="invalid"), "2024-04-15(月)")

    # --- config.py ---
    def test_migrate_legacy_ui_settings_oserror(self):
        # config.py: 90 (OSError on replace)
        with (
            patch.object(config.Path, "exists", side_effect=[True, False]), # legacy exists, target not
            patch.object(config.Path, "replace", side_effect=OSError("rename fail")),
            patch.object(config, "_MIGRATION_DONE", False)
        ):
            config._migrate_legacy_ui_settings()

    def test_save_ui_settings_base_exception_cleanup(self):
        # config.py: 177-182 (BaseException path)
        with (
            patch("os.fdopen", return_value=MagicMock()),
            patch("tempfile.mkstemp", return_value=(99, "/tmp/tmp123")),
            patch.object(config.Path, "replace", side_effect=Exception("critical fail")),
            patch("os.unlink") as unlink_mock,
            patch.object(config, "_MIGRATION_DONE", True)
        ):
            with self.assertRaises(Exception):
                config._save_ui_settings("dark", "12")
            unlink_mock.assert_called_with("/tmp/tmp123")

    # --- cache.py ---
    def test_save_json_cache_base_exception_cleanup(self):
        # cache.py: 82-87 (BaseException path)
        with (
            patch("os.fdopen", return_value=MagicMock()),
            patch("tempfile.mkstemp", return_value=(99, "/tmp/tmp456")),
            patch.object(cache.Path, "replace", side_effect=RuntimeError("abort")),
            patch("os.unlink") as unlink_mock
        ):
            with self.assertRaises(RuntimeError):
                cache._save_json_cache(Path("/tmp/c.json"), {})
            unlink_mock.assert_called_with("/tmp/tmp456")

    # --- cli.py ---
    def test_download_episode_keyboard_interrupt(self):
        # cli.py: 141-149 (KeyboardInterrupt)
        mock_proc = MagicMock()
        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch.object(mock_proc, "stdout", [b"progress"]),
            patch("nhk_radio.cli._parse_yt_dlp_progress", side_effect=KeyboardInterrupt)
        ):
            res = cli.download_episode("url", Path("/tmp"), "tmpl")
            self.assertFalse(res)
            mock_proc.terminate.assert_called()

    def test_download_episode_general_exception(self):
        # cli.py: 151-155 (General Exception)
        with (
            patch("subprocess.Popen", side_effect=RuntimeError("spawn fail")),
            patch.object(cli, "logger") as log_mock
        ):
            res = cli.download_episode("url", Path("/tmp"), "tmpl")
            self.assertFalse(res)
            log_mock.error.assert_called()

    def test_download_url_direct_failure(self):
        # cli.py: 212 (sys.exit on failure)
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with (
            patch.object(cli, "_resolve_program_from_url", return_value=program),
            patch("subprocess.run", return_value=MagicMock(returncode=1)),
            patch("sys.exit") as exit_mock
        ):
            cli.download_url_direct("url", Path("/tmp"), None, True)
            exit_mock.assert_called_with(1)

    # --- core.py ---
    def test_http_get_json_async_errors(self):
        # core.py: 50-54, 64-69, 78-80 (HTTP errors)
        import asyncio
        client = MagicMock(spec=httpx.AsyncClient)
        
        # 1) HTTPStatusError
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        resp.request = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=resp.request, response=resp)
        client.get = AsyncMock(return_value=resp)
        with self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(core.http_get_json_async(client, "url"))

        # 2) ConnectError
        client.get = AsyncMock(side_effect=httpx.ConnectError("fail"))
        with self.assertRaises(httpx.ConnectError):
            asyncio.run(core.http_get_json_async(client, "url"))

        # 3) RequestError
        client.get = AsyncMock(side_effect=httpx.RequestError("fail"))
        with self.assertRaises(httpx.RequestError):
            asyncio.run(core.http_get_json_async(client, "url"))

    def test_http_get_json_sync_errors(self):
        # core.py 同期版の例外パス
        with (
            patch("httpx.Client.get", side_effect=httpx.ConnectError("fail")),
            patch.object(core, "logger") as log_mock
        ):
            with self.assertRaises(httpx.ConnectError):
                core.http_get_json("url")
            log_mock.error.assert_called()

    def test_fetch_episodes_yt_dlp_error_classification(self):
        # core.py: 312-320 (yt-dlp error msg classification)
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        
        # ffmpeg missing
        with patch("yt_dlp.YoutubeDL") as ydl:
            instance = ydl.return_value.__enter__.return_value
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("ffmpeg not found")
            with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                core.fetch_episodes(program)
            
            # Connection timeout
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("connection timeout")
            with self.assertRaisesRegex(RuntimeError, "ネットワーク接続"):
                core.fetch_episodes(program)

if __name__ == "__main__":
    unittest.main()

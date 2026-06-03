import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import yt_dlp  # type: ignore[import-untyped]

from nhk_radio import cache, cli, config, core, downloads, text
from nhk_radio.types import Program


class BackendCoverageCompletionTest(unittest.TestCase):

    # --- downloads.py ---
    def test_downloads_file_scan_cache_lru_eviction(self):
        # downloads.py: 204 (LRU eviction logic)
        from nhk_radio.downloads import filesystem
        with (
            patch("nhk_radio.downloads.filesystem._FILE_SCAN_CACHE_MAX_SIZE", 2),
            patch.object(filesystem, "_FILE_SCAN_CACHE", filesystem.OrderedDict())
        ):
            # 新しい空の OrderedDict でテスト
            d1, d2, d3 = Path("/dir1"), Path("/dir2"), Path("/dir3")
            filesystem._FILE_SCAN_CACHE[d1] = (1.0, [])
            filesystem._FILE_SCAN_CACHE[d2] = (1.0, [])
            # 3つ目を入れるのは get_cached_glob_files 経由である必要がある (関数内の len チェックを通すため)
            with (
                patch.object(Path, "is_dir", return_value=True),
                patch.object(Path, "stat", return_value=MagicMock(st_mtime=1.0)),
                patch.object(Path, "iterdir", return_value=[])
            ):
                downloads._get_cached_glob_files(d3)
                self.assertEqual(len(filesystem._FILE_SCAN_CACHE), 2)
                self.assertNotIn(d1, filesystem._FILE_SCAN_CACHE)

    def test_get_cached_glob_files_oserror_on_stat(self):
        # downloads.py: 191 (OSError on stat)
        with (
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "stat", side_effect=OSError("denied")),
        ):
            self.assertEqual(downloads._get_cached_glob_files(Path("/tmp/any")), [])

    def test_get_cached_glob_files_oserror_on_iterdir(self):
        # downloads.py: 200 (OSError on iterdir)
        with (
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "stat", return_value=MagicMock(st_mtime=1.0)),
            patch.object(Path, "iterdir", side_effect=OSError("iterdir fail")),
            patch("nhk_radio.downloads.filesystem.logger") as log_mock
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
        # config.py: OSError が発生しても握りつぶされること
        with (
            patch("nhk_radio.config._resolve_cache_root_dir", return_value=Path("/tmp/cache")),
            patch("nhk_radio.config._ui_settings_path", return_value=Path("/tmp/config/ui.json")),
            patch.object(config.Path, "exists", side_effect=[True, False]),
            patch.object(config.Path, "replace", side_effect=OSError("rename fail")),
        ):
            # OSError が発生しても例外は握りつぶされ、関数は正常に return する
            try:
                config._migrate_legacy_ui_settings()
            except OSError:
                self.fail("_migrate_legacy_ui_settings は OSError を握りつぶすべき")

    def test_save_ui_settings_base_exception_cleanup(self):
        # config.py: 177-182 (BaseException path)
        with (
            patch("os.fdopen", return_value=MagicMock()),
            patch("tempfile.mkstemp", return_value=(99, "/tmp/tmp123")),
            patch.object(config.Path, "replace", side_effect=RuntimeError("critical fail")),
            patch("os.unlink") as unlink_mock,
        ):
            with self.assertRaises(RuntimeError):
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
        # cli.py: KeyboardInterrupt handling
        with (
            patch.object(cli, "_download_episode_command", return_value=["ls"]),
            patch("nhk_radio.cli.run_yt_dlp_subprocess", side_effect=KeyboardInterrupt)
        ):
            res = cli.download_episode("url", Path("/tmp"), "tmpl")
            self.assertFalse(res)

    def test_download_episode_general_exception(self):
        # downloads.py: run_yt_dlp_subprocess exception handling
        with (
            patch.object(cli, "_download_episode_command", return_value=["ls"]),
            patch("nhk_radio.cli.run_yt_dlp_subprocess", return_value=False)
        ):
            res = cli.download_episode("url", Path("/tmp"), "tmpl")
            self.assertFalse(res)

    def test_download_url_direct_failure(self):
        # cli.py: 212 (sys.exit on failure)
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with (
            patch.object(cli, "_resolve_program_from_url", return_value=program),
            patch("subprocess.run", return_value=MagicMock(returncode=1)),
            patch.object(sys, "exit") as exit_mock
        ):
            cli.download_url_direct("url", Path("/tmp"), None, True)
            exit_mock.assert_called_once_with(1)

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

    # --- types.py ---
    def test_normalize_string_tuple_iterable(self):
        # types.py: 18-20 (Iterable case with values)
        from nhk_radio.types import _normalize_string_tuple
        result = _normalize_string_tuple(["a", "b", "c"])
        self.assertEqual(result, ("a", "b", "c"))

    def test_normalize_string_tuple_iterable_empty(self):
        # types.py: 18 (Iterable case, but empty)
        from nhk_radio.types import _normalize_string_tuple
        result = _normalize_string_tuple([])
        self.assertEqual(result, ())

    def test_normalize_string_tuple_with_fallback(self):
        # types.py: 22-23 (fallback branch)
        from nhk_radio.types import _normalize_string_tuple
        result = _normalize_string_tuple([], fallback="fallback_val")
        self.assertEqual(result, ("fallback_val",))

    def test_normalize_string_tuple_dedup_with_fallback(self):
        # types.py: 22-23 (fallback with existing value)
        from nhk_radio.types import _normalize_string_tuple
        result = _normalize_string_tuple(["a"], fallback="a")
        self.assertEqual(result, ("a",))

    # --- cleanup.py ---
    def test_cleanup_partial_episode_files_no_pattern_match(self):
        # cleanup.py: 27-30 (no pattern match on .part/.ytdl file)
        import tempfile
        from pathlib import Path

        from nhk_radio.downloads import cleanup
        from nhk_radio.types import Episode, Program

        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="E", title="ET", display_title="EDT", date="2024-01-01", display_date="D", broadcast_time="00:00", duration_str="30m", url="U")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            # Create a .part file that doesn't match episode pattern
            part_file = output_dir / "unrelated.part"
            part_file.touch()

            with (
                patch("nhk_radio.downloads.filesystem._program_search_dirs", return_value=[output_dir]),
                patch("nhk_radio.downloads.filesystem._clear_file_scan_cache"),
                patch("nhk_radio.downloads.filesystem._episode_output_patterns", return_value=[]),
            ):
                # Should not crash, just skip the non-matching file
                cleanup.cleanup_partial_episode_files(output_dir, program, episode)
                self.assertTrue(part_file.exists())  # File should still exist

    # --- config.py ---
    def test_load_ui_settings_empty_search_history(self):
        # config.py: 165-166 (normalized が空の場合)
        with (
            patch("nhk_radio.config._migrate_legacy_ui_settings"),
            patch("nhk_radio.config._ui_settings_path", return_value=Path("/tmp/ui.json")),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value='{"program_search_history": [""]}'),  # 空文字列のみ
        ):
            settings = config._load_ui_settings()
            # 正規化後が空なので program_search_history は settings に含まれない
            self.assertNotIn("program_search_history", settings)

    # --- manifest.py ---
    def test_get_downloaded_episode_keys_no_match(self):
        # manifest.py: 165 (any() が False の場合)
        from nhk_radio.downloads import manifest
        import tempfile
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        episode = "ep1"
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            # ファイルがないため any(...) は False
            result = manifest.get_downloaded_episode_keys(output_dir, program, [])
            self.assertEqual(result, set())

    def test_get_downloaded_episode_keys_with_match(self):
        # manifest.py: 165 (any() が True の場合 = 165->166 ブランチ)
        from nhk_radio.downloads import manifest, filesystem
        from nhk_radio.types import Episode
        import tempfile
        program = Program(title="番組A", display_title="番組A", display_date="D", site_id="SITE", corner_id="01", url="U")
        episode = Episode(id="ep1", title="第1回", display_title="第1回", date="20240415", display_date="D", broadcast_time="", duration_str="", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = filesystem._program_output_dir(output_dir, program)
            program_dir.mkdir(parents=True, exist_ok=True)
            # マッチするファイルを作成
            (program_dir / "20240415_番組A_第1回.mp3").write_text("x")
            # マニフェストには記録されていないため、ディレクトリスキャンでマッチする
            result = manifest.get_downloaded_episode_keys(output_dir, program, [episode])
            self.assertIn(filesystem._episode_key(episode), result)

    # --- text.py ---
    def test_program_genre_labels_with_genres(self):
        # text.py: 196 (_program_genres が True で _genre_label が実行)
        program = Program(
            title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U",
            genre="music", genre_label="", genres=("music",), genre_labels=()
        )
        labels = text._program_genre_labels(program)
        self.assertIn("音楽", labels)  # music -> 音楽

    # --- core.py ---
    def test_make_entry_with_none_genre(self):
        # core.py: 182-184 (if genre: false branch)
        from nhk_radio.core import _make_entry
        s = {"title": "Test Program", "site_id": "S", "corner_id": "C"}
        program = _make_entry(s, genre=None)
        self.assertIsNone(program.genre)
        self.assertEqual(program.genres, ())


if __name__ == "__main__":
    unittest.main()

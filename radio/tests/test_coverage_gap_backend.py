import subprocess
import sys
import tempfile
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

    def test_episode_output_matches_empty_sanitized(self):
        from nhk_radio.downloads import filesystem
        from nhk_radio.types import Episode, Program
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        # sanitize_filename が空文字を返すようなタイトル
        episode = Episode(id="1", title="///", display_title="///", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            p = Path(tmp.name)
            self.assertFalse(filesystem._episode_output_matches(p, program, episode))

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
        # cli.py: KeyboardInterrupt handling (M6: 再送出されること)
        with (
            patch.object(cli, "download_episode_command", return_value=["ls"]),
            patch("nhk_radio.cli.run_yt_dlp_subprocess", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            cli.download_episode("url", Path("/tmp"), "tmpl")

    def test_download_episode_general_exception(self):
        # downloads.py: run_yt_dlp_subprocess exception handling
        with (
            patch.object(cli, "download_episode_command", return_value=["ls"]),
            patch("nhk_radio.cli.run_yt_dlp_subprocess", return_value=False)
        ):
            res = cli.download_episode("url", Path("/tmp"), "tmpl")
            self.assertFalse(res)

    def test_download_url_direct_failure(self):
        # cli.py: 212 (sys.exit on failure)
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with (
            patch.object(cli, "resolve_program_from_url", return_value=program),
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
        import tempfile

        from nhk_radio.downloads import manifest
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            # ファイルがないため any(...) は False
            result = manifest.get_downloaded_episode_keys(output_dir, program, [])
            self.assertEqual(result, set())

    def test_get_downloaded_episode_keys_with_match(self):
        # manifest.py: 165 (any() が True の場合 = 165->166 ブランチ)
        import tempfile

        from nhk_radio.downloads import filesystem, manifest
        from nhk_radio.types import Episode
        program = Program(title="番組A", display_title="番組A", display_date="D", site_id="SITE", corner_id="01", url="U")
        episode = Episode(id="ep1", title="第1回", display_title="第1回", date="20240415", display_date="D", broadcast_time="", duration_str="", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = filesystem.program_output_dir(output_dir, program)
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

    # --- cache.py: M3 ---
    def test_load_program_cache_type_error(self):
        # 必須キーが欠けた dict がある場合 TypeError で None を返すこと (M3)
        with patch("nhk_radio.cache._load_json_ttl_cache", return_value=[{}]):
            self.assertIsNone(cache.load_program_cache("genre"))

    def test_load_episode_cache_type_error(self):
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with patch("nhk_radio.cache._load_json_ttl_cache", return_value=[{}]):
            self.assertIsNone(cache.load_episode_cache(program))

    # --- cli.py: H2, M7 ---
    def test_select_program_eof_error(self):
        with patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(cli.select_program([]))

    def test_select_episodes_eof_error(self):
        from nhk_radio.types import Episode
        ep = Episode(id="1", title="T", display_title="T", date="20240101", display_date="D", broadcast_time="", duration_str="", url="U")
        with patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(cli.select_episodes([ep]))

    def test_download_url_direct_timeout(self):
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with (
            patch.object(cli, "resolve_program_from_url", return_value=program),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 3600)),
            patch.object(sys, "exit") as exit_mock,
        ):
            cli.download_url_direct("url", Path("/tmp"), None, True)
            exit_mock.assert_called_once_with(1)

    def test_download_url_direct_file_not_found(self):
        program = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with (
            patch.object(cli, "resolve_program_from_url", return_value=program),
            patch("subprocess.run", side_effect=FileNotFoundError),
            patch.object(sys, "exit") as exit_mock,
        ):
            cli.download_url_direct("url", Path("/tmp"), None, True)
            exit_mock.assert_called_once_with(1)

    # --- core.py: M1, M8, M9 ---
    def test_http_get_json_async_retry_after_http_date(self):
        import asyncio
        client = MagicMock(spec=httpx.AsyncClient)
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.request = MagicMock()
        # HTTP-date format
        resp_429.headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
        resp_429.raise_for_status.side_effect = httpx.HTTPStatusError("429", request=resp_429.request, response=resp_429)

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}
        resp_200.raise_for_status.return_value = None

        client.get = AsyncMock(side_effect=[resp_429, resp_200])
        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
            patch("time.time", return_value=1792567670.0),
        ):
            res = asyncio.run(core.http_get_json_async(client, "http://test"))
            self.assertEqual(res, {"ok": True})
            sleep_mock.assert_called_once()

    def test_http_get_json_async_retry_after_invalid_date(self):
        import asyncio
        client = MagicMock(spec=httpx.AsyncClient)
        resp_429 = MagicMock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.request = MagicMock()
        resp_429.headers = {"Retry-After": "invalid-date-string"}
        resp_429.raise_for_status.side_effect = httpx.HTTPStatusError("429", request=resp_429.request, response=resp_429)

        resp_200 = MagicMock(spec=httpx.Response)
        resp_200.status_code = 200
        resp_200.json.return_value = {"ok": True}
        resp_200.raise_for_status.return_value = None

        client.get = AsyncMock(side_effect=[resp_429, resp_200])
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
            res = asyncio.run(core.http_get_json_async(client, "http://test"))
            self.assertEqual(res, {"ok": True})
            sleep_mock.assert_called_once()

    def test_fetch_program_list_async_partial_failure_warning(self):
        import asyncio

        p = Program(title="P", display_title="P", display_date="D", site_id="S", corner_id="C", url="U")
        with (
            patch("nhk_radio.core.load_program_cache", return_value=None),
            patch("nhk_radio.core._fetch_all_with_status_async", new_callable=AsyncMock, return_value=([p], True)),
            patch("nhk_radio.core.save_program_cache") as save_mock,
            patch("nhk_radio.core.logger.warning") as warn_mock,
        ):
            programs = asyncio.run(core.fetch_program_list_async())
            self.assertEqual(len(programs), 1)
            save_mock.assert_not_called()
            warn_mock.assert_called_once()

    def test_info_dict_to_episode_timestamp_fallback(self):
        info = {
            "id": "ep1",
            "title": "Ep 1",
            "timestamp": 1700000000,
        }
        with patch("zoneinfo.ZoneInfo", side_effect=Exception("zoneinfo error")):
            ep = core._parse_episode_info(info)
            self.assertEqual(ep.date, "1700000000")

    # --- downloads/filesystem.py ---
    def test_filesystem_audio_only_matches_false_for_video(self):
        from nhk_radio.downloads import filesystem
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="第1回", display_title="第1回", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        path = Path("/tmp/20240401_番組_第1回.mp4")
        with patch.object(Path, "is_file", return_value=True):
            self.assertFalse(filesystem._episode_output_matches(path, program, episode, audio_only=True))

    def test_is_episode_downloaded_audio_only_ignores_mp4(self):
        import tempfile

        from nhk_radio.downloads import filesystem, manifest
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="第2回", display_title="第2回", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p_dir = filesystem.program_output_dir(out, program)
            p_dir.mkdir(parents=True, exist_ok=True)
            (p_dir / "20240401_番組_第2回.mp4").write_text("dummy")
            self.assertFalse(manifest.is_episode_downloaded(out, program, episode, audio_only=True))
            self.assertTrue(manifest.is_episode_downloaded(out, program, episode, audio_only=False))

    def test_save_search_history_preserves_persisted_theme(self):
        from nhk_radio.gui.theme_manager import ThemeManager
        with patch("nhk_radio.gui.theme_manager.config._load_ui_settings", return_value={"theme": "dark", "font_size_pt": 12, "program_search_history": []}):
            tm = ThemeManager(MagicMock())
            # プレビュー適用で current_theme が変わる
            tm.current_theme = "light"
            tm.current_font_size = 14
            with patch("nhk_radio.gui.theme_manager.config._save_ui_settings") as save_mock:
                tm.save_search_history(["検索語"])
                # 保存されるのはプレビュー中の light/14 ではなく、元の dark/12 であること (G8)
                save_mock.assert_called_once_with("dark", 12, ["検索語"])

    def test_download_worker_backup_and_restore_on_failure(self):
        import tempfile
        import threading

        from nhk_radio.gui.download_manager import DownloadManager
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="第1回", display_title="第1回", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p_dir = out / "S_C"
            p_dir.mkdir(parents=True)
            original_file = p_dir / "20240401_番組_第1回.mp3"
            original_file.write_text("original content")

            dm = DownloadManager(out, True, MagicMock())
            cancel_ev = threading.Event()

            # DL が失敗するようにモック
            with patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", return_value=False):
                dm._download_worker(program, episode, "ep_key", cancel_ev)

            # 元ファイルが復元されていること (G4)
            self.assertTrue(original_file.exists())
            self.assertEqual(original_file.read_text(), "original content")
            self.assertFalse((p_dir / "20240401_番組_第1回.mp3.bak").exists())

    def test_filesystem_empty_episode_title_matches(self):
        from nhk_radio.downloads import filesystem
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="", display_title="", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        path = Path("/tmp/20240401_番組.mp3")
        with patch.object(Path, "is_file", return_value=True):
            self.assertTrue(filesystem._episode_output_matches(path, program, episode, audio_only=True))

    def test_filesystem_title_variants_with_empty_tv(self):
        from nhk_radio.downloads import filesystem
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="///", display_title="///", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        path = Path("/tmp/20240401_番組_nomatch.mp3")
        with patch.object(Path, "is_file", return_value=True):
            self.assertFalse(filesystem._episode_output_matches(path, program, episode, audio_only=True))

    def test_episode_output_patterns_yt_dlp_sanitize(self):
        from nhk_radio.downloads import filesystem
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="Q&A: 何？/なぜ?", display_title="Q&A: 何？/なぜ?", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        patterns = filesystem._episode_output_patterns(program, episode)
        self.assertTrue(any("何" in p for p in patterns))

    def test_filesystem_module_import_invalid_env(self):
        import importlib

        from nhk_radio.downloads import filesystem
        with patch.dict("os.environ", {"NHK_RADIO_FILE_SCAN_CACHE_SIZE": "invalid"}):
            importlib.reload(filesystem)
            self.assertEqual(filesystem._FILE_SCAN_CACHE_MAX_SIZE, 100)
        importlib.reload(filesystem)

    def test_episode_output_patterns_yt_dlp_sanitize_exception(self):
        from nhk_radio.downloads import filesystem
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="Title", display_title="Title", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        with patch("yt_dlp.utils.sanitize_filename", side_effect=Exception("sanitize fail")):
            patterns = filesystem._episode_output_patterns(program, episode)
            self.assertTrue(len(patterns) > 0)

            path = Path("/tmp/20240401_番組_Title.mp3")
            with patch.object(Path, "is_file", return_value=True):
                self.assertTrue(filesystem._episode_output_matches(path, program, episode, audio_only=True))

    # --- downloads/manifest.py: M2 ---
    def test_manifest_load_non_dict_payload(self):
        import tempfile

        from nhk_radio.downloads import manifest
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p_dir = out / "S_C"
            p_dir.mkdir()
            (p_dir / ".downloaded.json").write_text("[]", encoding="utf-8")
            res = manifest._load_download_manifest(program, out)
            self.assertEqual(res, {})

    # --- downloads/runner.py: M10, G5 ---
    def test_run_yt_dlp_subprocess_cancel_watcher(self):
        import threading
        import time

        from nhk_radio.downloads import runner
        cancel_event = threading.Event()
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, None, 0]
        mock_proc.wait.return_value = 0
        mock_proc.stdout = []
        with patch("subprocess.Popen", return_value=mock_proc):
            cancel_event.set()
            res = runner.run_yt_dlp_subprocess(["test"], cancel_event=cancel_event)
            time.sleep(0.15)
            self.assertFalse(res)

    def test_run_yt_dlp_subprocess_on_process_and_watcher_timeout(self):
        """on_process にプロセスを渡し、未キャンセル時は監視スレッドが待機を繰り返す。"""
        import threading
        import time

        from nhk_radio.downloads import runner

        polls = iter([None, None, None])
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = lambda: next(polls, 0)
        mock_proc.wait.return_value = 0

        def _slow_stdout():
            # 監視スレッドが wait のタイムアウトを複数回経験できるだけ出力を遅らせる
            time.sleep(0.35)
            yield from ()

        mock_proc.stdout = _slow_stdout()
        received = []
        with patch("subprocess.Popen", return_value=mock_proc):
            res = runner.run_yt_dlp_subprocess(
                ["test"], cancel_event=threading.Event(), on_process=received.append
            )
        self.assertTrue(res)
        self.assertEqual(received, [mock_proc])
        self.assertGreaterEqual(mock_proc.poll.call_count, 2)

    def test_run_yt_dlp_subprocess_on_output_path(self):
        from nhk_radio.downloads import runner
        captured = []
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.stdout = ["/path/to/downloaded.mp3\n"]
        with patch("subprocess.Popen", return_value=mock_proc):
            runner.run_yt_dlp_subprocess(["test"], on_output_path=captured.append)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0], Path("/path/to/downloaded.mp3"))

    def test_run_yt_dlp_subprocess_error_logging(self):
        from nhk_radio.downloads import runner
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.wait.return_value = 1
        mock_proc.stdout = ["error message line 1\n"]
        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch("nhk_radio.downloads.runner.logger.error") as log_error,
        ):
            res = runner.run_yt_dlp_subprocess(["test"])
            self.assertFalse(res)
            log_error.assert_called_once()
            self.assertIn("error message line 1", log_error.call_args[0][0])

    def test_failure_reason_prefers_last_error_line(self):
        """失敗理由は最後の ERROR 行、無ければ終了コードになる (F4)。"""
        from nhk_radio.downloads.runner import _failure_reason
        lines = ["[info] x\n", "ERROR: first\n", "ERROR: [generic] HTTP Error 404\n", "done\n"]
        self.assertEqual(_failure_reason(lines, 1), "[generic] HTTP Error 404")
        self.assertEqual(_failure_reason(["ERROR:\n"], 1), "ERROR:")
        self.assertEqual(_failure_reason(["plain\n"], 2), "yt-dlp が終了コード 2 で終了しました")

    def test_run_yt_dlp_subprocess_reports_failure_reason(self):
        """終了コードが 0 以外なら on_error に理由を渡す。"""
        from nhk_radio.downloads import runner
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.wait.return_value = 1
        mock_proc.stdout = ["ERROR: Unsupported URL\n"]
        reasons: list[str] = []
        with patch("subprocess.Popen", return_value=mock_proc):
            self.assertFalse(runner.run_yt_dlp_subprocess(["test"], on_error=reasons.append))
        self.assertEqual(reasons, ["Unsupported URL"])

    def test_run_yt_dlp_subprocess_reports_timeout_and_exception(self):
        """タイムアウトと起動失敗でも on_error に理由を渡す。"""
        from nhk_radio.downloads import runner
        mock_proc = MagicMock()
        mock_proc.stdout = []
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("yt-dlp", 120), 0]
        reasons: list[str] = []
        with patch("subprocess.Popen", return_value=mock_proc):
            self.assertFalse(runner.run_yt_dlp_subprocess(["test"], on_error=reasons.append))
        with patch("subprocess.Popen", side_effect=OSError("not found")):
            self.assertFalse(runner.run_yt_dlp_subprocess(["test"], on_error=reasons.append))
        self.assertEqual(reasons, ["yt-dlp が応答しないため強制終了しました", "yt-dlp の実行エラー: not found"])

    def test_download_worker_passes_failure_reason(self):
        """ワーカーは failed_one の data に失敗理由を載せる (F4)。"""
        import tempfile
        import threading

        from nhk_radio.gui.download_manager import DownloadManager
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="第1回", display_title="第1回", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")

        def _fail(*_args, on_error=None, **_kwargs):
            on_error("HTTP Error 403")
            return False

        with tempfile.TemporaryDirectory() as tmp:
            on_result = MagicMock()
            dm = DownloadManager(Path(tmp), True, on_result)
            with patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", side_effect=_fail):
                dm._download_worker(program, episode, "ep_key", threading.Event())
            self.assertEqual(on_result.call_args.args[0], "failed_one")
            self.assertEqual(on_result.call_args.args[4], "HTTP Error 403")

            on_result.reset_mock()
            with patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", side_effect=RuntimeError("boom")):
                dm._download_worker(program, episode, "ep_key", threading.Event())
            self.assertEqual(on_result.call_args.args[4], "boom")

            on_result.reset_mock()
            with patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", return_value=False):
                dm._download_worker(program, episode, "ep_key", threading.Event())
            self.assertIsNone(on_result.call_args.args[4])

    # --- text.py ---
    def test_format_episode_date_invalid_prefix(self):
        # 99999999_extra で strptime が ValueError になるケース
        formatted = text._format_episode_date("99999999_abc")
        self.assertEqual(formatted, "99999999_abc")

    # --- downloads/cleanup.py ---
    def test_cleanup_partial_episode_files_restores_bak_when_orig_missing(self):
        from nhk_radio.downloads import cleanup
        from nhk_radio.types import Episode
        program = Program(title="テスト番組", display_title="テスト番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="ep1", title="回1", display_title="回1", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="")
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            p_dir = tmp_path / "S_C"
            p_dir.mkdir()
            bak_file = p_dir / ("2024-04-15_テスト番組_回1.m4a" + cleanup.BACKUP_SUFFIX)
            orig_file = p_dir / "2024-04-15_テスト番組_回1.m4a"
            # 別のエピソードの .nhkradio-bak も配置 (2-2 指摘の検証: 巻き込まれて復元・削除されないこと)
            other_bak = p_dir / ("2024-04-16_テスト番組_回2.m4a" + cleanup.BACKUP_SUFFIX)
            bak_file.write_text("backup-content", encoding="utf-8")
            other_bak.write_text("other-backup", encoding="utf-8")

            cleanup.cleanup_partial_episode_files(tmp_path, program, episode)

            self.assertFalse(bak_file.exists())
            self.assertTrue(orig_file.exists())
            self.assertEqual(orig_file.read_text(encoding="utf-8"), "backup-content")
            # 別のエピソードのバックアップはそのまま残っていること
            self.assertTrue(other_bak.exists())

    def test_cleanup_partial_episode_files_removes_bak_when_orig_exists(self):
        from nhk_radio.downloads import cleanup
        from nhk_radio.types import Episode
        program = Program(title="テスト番組", display_title="テスト番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="ep1", title="回1", display_title="回1", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="")
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            p_dir = tmp_path / "S_C"
            p_dir.mkdir()
            orig_file = p_dir / "2024-04-15_テスト番組_回1.m4a"
            bak_file = p_dir / ("2024-04-15_テスト番組_回1.m4a" + cleanup.BACKUP_SUFFIX)
            other_bak = p_dir / ("2024-04-16_テスト番組_回2.m4a" + cleanup.BACKUP_SUFFIX)
            orig_file.write_text("orig-content", encoding="utf-8")
            bak_file.write_text("backup-content", encoding="utf-8")
            other_bak.write_text("other-backup", encoding="utf-8")

            cleanup.cleanup_partial_episode_files(tmp_path, program, episode)

            self.assertTrue(orig_file.exists())
            self.assertFalse(bak_file.exists())
            # 別のエピソードのバックアップはそのまま残っていること
            self.assertTrue(other_bak.exists())

    def test_cleanup_residual_backup_files(self):
        from nhk_radio.downloads import cleanup
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            p_dir1 = tmp_path / "prog1"
            p_dir2 = tmp_path / "prog2"
            p_dir1.mkdir()
            p_dir2.mkdir()

            # prog1: .nhkradio-bak のみ -> 復元される (2-1)
            bak1 = p_dir1 / "file1.m4a.nhkradio-bak"
            bak1.write_text("c1", encoding="utf-8")

            # prog1: ユーザーが作成した .bak (file2.m4a.bak) と orig -> 勝手に削除されない (2-3)
            bak2 = p_dir1 / "file2.m4a.bak"
            orig2 = p_dir1 / "file2.m4a"
            bak2.write_text("c2-bak", encoding="utf-8")
            orig2.write_text("c2-orig", encoding="utf-8")

            # prog1: 既存ファイルがある場合の .nhkradio-bak -> .nhkradio-bak が削除される
            bak1_dup = p_dir1 / "file4.m4a.nhkradio-bak"
            orig4 = p_dir1 / "file4.m4a"
            bak1_dup.write_text("c4-bak", encoding="utf-8")
            orig4.write_text("c4-orig", encoding="utf-8")

            # 2-1 検証: 一般ファイル (memo.txt.bak, memo.txt.nhkradio-bak) は変更・削除されないこと
            memo_root_bak = tmp_path / "memo.txt.bak"
            memo_root_bak.write_text("memo-bak-content", encoding="utf-8")
            memo_prog_bak = p_dir1 / "memo.txt.bak"
            memo_prog = p_dir1 / "memo.txt"
            memo_prog_bak.write_text("prog-memo-bak", encoding="utf-8")
            memo_prog.write_text("prog-memo-orig", encoding="utf-8")
            memo_prog_nhkbak = p_dir1 / "memo.txt.nhkradio-bak"
            memo_prog_nhkbak.write_text("prog-memo-nhkbak", encoding="utf-8")

            # prog2: active_program_dirs に指定 -> スキップされる (2-2)
            bak3 = p_dir2 / "file3.m4a.nhkradio-bak"
            bak3.write_text("c3", encoding="utf-8")

            cleaned = cleanup.cleanup_residual_backup_files(tmp_path, active_program_dirs={p_dir2})
            self.assertEqual(cleaned, 2)
            self.assertTrue((p_dir1 / "file1.m4a").exists())
            self.assertFalse(bak1.exists())
            self.assertTrue(orig2.exists())
            # ユーザー作成の .bak は削除されず残る (2-3)
            self.assertTrue(bak2.exists())
            self.assertTrue(orig4.exists())
            self.assertFalse(bak1_dup.exists())
            self.assertTrue(bak3.exists())

            # 一般ファイルは一切影響を受けていないこと (2-1)
            self.assertTrue(memo_root_bak.exists())
            self.assertEqual(memo_root_bak.read_text(encoding="utf-8"), "memo-bak-content")
            self.assertFalse((tmp_path / "memo.txt").exists())
            self.assertTrue(memo_prog_bak.exists())
            self.assertEqual(memo_prog_bak.read_text(encoding="utf-8"), "prog-memo-bak")
            self.assertTrue(memo_prog.exists())
            self.assertEqual(memo_prog.read_text(encoding="utf-8"), "prog-memo-orig")
            self.assertTrue(memo_prog_nhkbak.exists())
            self.assertEqual(memo_prog_nhkbak.read_text(encoding="utf-8"), "prog-memo-nhkbak")

            # min_age_seconds のテスト (2-2)
            recent_bak = p_dir1 / "recent.mp3.nhkradio-bak"
            recent_bak.write_text("recent", encoding="utf-8")
            # min_age_seconds=10.0 のとき、直近作成ファイルはスキップされる
            cleaned_recent = cleanup.cleanup_residual_backup_files(tmp_path, active_program_dirs={p_dir2}, min_age_seconds=10.0)
            self.assertEqual(cleaned_recent, 0)
            self.assertTrue(recent_bak.exists())

            # stat で OSError が発生した場合も安全にスキップ
            with patch.object(Path, "stat", side_effect=OSError("stat fail")):
                self.assertEqual(cleanup.cleanup_residual_backup_files(tmp_path, active_program_dirs={p_dir2}, min_age_seconds=10.0), 0)

            # mtime が過去（30秒前）のファイルは min_age_seconds=10.0 でも処理される (分岐カバレッジ 123->128)
            import os
            import time
            old_time = time.time() - 30.0
            os.utime(recent_bak, (old_time, old_time))
            cleaned_old = cleanup.cleanup_residual_backup_files(tmp_path, active_program_dirs={p_dir2}, min_age_seconds=10.0)
            self.assertEqual(cleaned_old, 1)
            self.assertTrue((p_dir1 / "recent.mp3").exists())
            self.assertFalse(recent_bak.exists())

            # 存在しないディレクトリの場合は 0
            self.assertEqual(cleanup.cleanup_residual_backup_files(tmp_path / "nonexistent"), 0)

            # candidate_dirs の走査で OSError が発生した場合
            with patch.object(Path, "iterdir", side_effect=OSError("disk error")):
                self.assertEqual(cleanup.cleanup_residual_backup_files(tmp_path), 0)

            # 各ディレクトリ内の走査で OSError が発生した場合はスキップされる
            with patch.object(Path, "iterdir", side_effect=OSError("dir read error")):
                self.assertEqual(cleanup.cleanup_residual_backup_files(tmp_path), 0)

            # replace / unlink 時に OSError が発生しても例外をキャッチして継続する
            bak_err = p_dir1 / "err.m4a.bak"
            bak_err.write_text("err", encoding="utf-8")
            with patch.object(Path, "replace", side_effect=OSError("replace error")):
                self.assertEqual(cleanup.cleanup_residual_backup_files(tmp_path), 0)

    def test_terminate_process_killpg(self):
        from nhk_radio.downloads import runner
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        with (
            patch("sys.platform", "linux"),
            patch("os.getpgid", return_value=12345) as mock_getpgid,
            patch("os.killpg") as mock_killpg,
        ):
            runner._terminate_process(mock_proc)
            mock_getpgid.assert_called_once_with(12345)
            mock_killpg.assert_called_once()
            mock_proc.terminate.assert_called_once()

        # killpg が OSError を出しても terminate が呼ばれる
        mock_proc.reset_mock()
        with (
            patch("sys.platform", "darwin"),
            patch("os.getpgid", side_effect=ProcessLookupError),
        ):
            runner._terminate_process(mock_proc)
            mock_proc.terminate.assert_called_once()

    def test_download_manager_active_program_dirs(self):
        from nhk_radio.gui.download_manager import DownloadManager
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        ep = Episode(id="ep1", title="回1", display_title="回1", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        dm = DownloadManager(Path("/tmp/test_out"), True, MagicMock())
        self.assertEqual(dm.get_active_program_dirs(), set())
        with patch("threading.Thread"):
            dm.start_download(program, ep)
            self.assertEqual(len(dm.get_active_program_dirs()), 1)
            self.assertIn(Path("/tmp/test_out/S_C"), dm.get_active_program_dirs())

    # --- downloads/runner.py ---
    def test_build_yt_dlp_options_includes_progress_with_after_move(self):
        from nhk_radio.downloads import runner
        cmd = runner._yt_dlp_command("https://example.com", "/out/%(title)s.%(ext)s", audio_only=True, no_playlist=True, print_filepath=True)
        self.assertIn("--progress", cmd)
        self.assertIn("--print", cmd)
        self.assertIn("after_move:filepath", cmd)

    # --- downloads/filesystem.py ---
    def test_filesystem_matches_excludes_bak(self):
        from nhk_radio.downloads import filesystem
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        ep = Episode(id="ep1", title="回1", display_title="回1", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="")
        bak_path = Path("/dummy/2024-04-15_回1.m4a.bak")
        nhk_bak_path = Path("/dummy/2024-04-15_回1.m4a.nhkradio-bak")
        self.assertFalse(filesystem._episode_output_matches(bak_path, program, ep, audio_only=True))
        self.assertFalse(filesystem._episode_output_matches(nhk_bak_path, program, ep, audio_only=True))

    def test_cleanup_partial_episode_files_restores_nhkradio_bak_and_ignores_memo_bak(self):
        from nhk_radio.downloads import cleanup
        from nhk_radio.types import Episode
        program = Program(title="テスト番組", display_title="テスト番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="ep1", title="回1", display_title="回1", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="")
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            p_dir = tmp_path / "S_C"
            p_dir.mkdir()
            bak_file = p_dir / "2024-04-15_テスト番組_回1.m4a.nhkradio-bak"
            bak_file.write_text("backup-content", encoding="utf-8")
            memo_bak = p_dir / "memo.txt.bak"
            memo_bak.write_text("memo-content", encoding="utf-8")

            cleanup.cleanup_partial_episode_files(tmp_path, program, episode)

            self.assertFalse(bak_file.exists())
            self.assertTrue((p_dir / "2024-04-15_テスト番組_回1.m4a").exists())
            # memo.txt.bak は一般ファイルなので一切触れられないこと (2-1)
            self.assertTrue(memo_bak.exists())
            self.assertEqual(memo_bak.read_text(encoding="utf-8"), "memo-content")

    def test_browser_start_residual_backup_cleanup(self):
        from nhk_radio.gui.browser import EpisodeGuiBrowser
        mock_self = MagicMock(spec=EpisodeGuiBrowser)
        mock_self.output_dir = Path("/tmp/dummy")
        mock_self.download_manager = MagicMock()
        mock_self.download_manager.get_active_program_dirs.return_value = {Path("/tmp/dummy/S_C")}

        with (
            patch("threading.Thread") as mock_thread,
            patch("nhk_radio.downloads.cleanup.cleanup_residual_backup_files") as mock_cleanup,
        ):
            EpisodeGuiBrowser._start_residual_backup_cleanup(mock_self)
            mock_thread.assert_called_once()
            target_fn = mock_thread.call_args[1]["target"]
            # ワーカーを実行して cleanup_residual_backup_files の呼び出しを確認
            target_fn()
            mock_cleanup.assert_called_once_with(
                Path("/tmp/dummy"),
                active_program_dirs={Path("/tmp/dummy/S_C")},
                min_age_seconds=10.0,
            )

    def test_episode_filter_change_debounce_and_clear(self):
        from nhk_radio.gui.listing.episodes import GuiEpisodeMixin
        mock_mixin = MagicMock(spec=GuiEpisodeMixin)
        mock_mixin.root = MagicMock()
        mock_mixin.root.after.return_value = 123
        mock_mixin.displayed_program = "PROG"
        mock_mixin.displayed_episodes = []
        mock_mixin._episode_search_timer = 999
        mock_mixin.episode_search_var = MagicMock()
        mock_mixin.episode_search_entry = MagicMock()

        # _on_episode_filter_change: 前のタイマーがキャンセルされ新しいタイマーがセットされる
        GuiEpisodeMixin._on_episode_filter_change(mock_mixin)
        mock_mixin.root.after_cancel.assert_called_once_with(999)
        mock_mixin.root.after.assert_called_once_with(150, mock_mixin._apply_episode_filter)

        # _apply_episode_filter
        GuiEpisodeMixin._apply_episode_filter(mock_mixin)
        mock_mixin._render_episode_rows.assert_called_once_with("PROG", [], clear_selection=False)

        # _clear_episode_search
        mock_mixin.root.after_cancel.reset_mock()
        mock_mixin._episode_search_timer = 123
        res = GuiEpisodeMixin._clear_episode_search(mock_mixin)
        self.assertEqual(res, "break")
        mock_mixin.root.after_cancel.assert_called_once_with(123)
        mock_mixin.episode_search_var.set.assert_called_once_with("")
        mock_mixin.episode_search_entry.focus_set.assert_called_once()

    def test_download_worker_backup_mtime_is_refreshed(self):
        import os
        import threading
        import time

        from nhk_radio.gui.download_manager import DownloadManager
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="第1回", display_title="第1回", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p_dir = out / "S_C"
            p_dir.mkdir(parents=True)
            original_file = p_dir / "20240401_番組_第1回.mp3"
            original_file.write_text("original content")
            # 元ファイルの mtime を過去にしておく
            os.utime(original_file, (1_000_000_000, 1_000_000_000))
            backup_file = p_dir / ("20240401_番組_第1回.mp3" + downloads.BACKUP_SUFFIX)
            observed: dict[str, float] = {}

            def fake_run(*_args, **_kwargs):
                # DL 実行中に、退避ファイルの mtime が現在時刻に更新されていること (followup-3 2-2)
                observed["age"] = time.time() - backup_file.stat().st_mtime
                # 別プロセスの起動時整理が走っても、直近の退避ファイルは復元されないこと
                observed["cleaned"] = downloads.cleanup_residual_backup_files(out, min_age_seconds=10.0)
                return False

            dm = DownloadManager(out, True, MagicMock())
            with patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", side_effect=fake_run):
                dm._download_worker(program, episode, "ep_key", threading.Event())

            self.assertLess(observed["age"], 10.0)
            self.assertEqual(observed["cleaned"], 0)
            # 失敗時は元ファイルに復元されること
            self.assertEqual(original_file.read_text(), "original content")

    def test_download_worker_backup_heartbeat_during_long_download(self):
        import os
        import threading
        import time

        from nhk_radio.gui.download_manager import DownloadManager
        from nhk_radio.types import Episode
        program = Program(title="番組", display_title="番組", display_date="D", site_id="S", corner_id="C", url="U")
        episode = Episode(id="1", title="第1回", display_title="第1回", date="20240401", display_date="D", broadcast_time="", duration_str="", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            p_dir = out / "S_C"
            p_dir.mkdir(parents=True)
            original_file = p_dir / "20240401_番組_第1回.mp3"
            original_file.write_text("original content")
            backup_file = p_dir / ("20240401_番組_第1回.mp3" + downloads.BACKUP_SUFFIX)
            observed: dict[str, int] = {}

            def fake_run(*_args, **_kwargs):
                # 長時間 DL を模擬: 退避ファイルの mtime を古くした後、ハートビートで更新されること
                os.utime(backup_file, (1_000_000_000, 1_000_000_000))
                time.sleep(0.3)
                observed["cleaned"] = downloads.cleanup_residual_backup_files(out, min_age_seconds=1.0)
                return False

            dm = DownloadManager(out, True, MagicMock())
            with (
                patch("nhk_radio.gui.download_manager.BACKUP_HEARTBEAT_INTERVAL_SECONDS", 0.05),
                patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", side_effect=fake_run),
            ):
                dm._download_worker(program, episode, "ep_key", threading.Event())

            # DL 継続中の退避ファイルは、別プロセスの整理で復元されないこと (followup-3 2-2)
            self.assertEqual(observed["cleaned"], 0)
            self.assertEqual(original_file.read_text(), "original content")
            self.assertFalse(backup_file.exists())

    def test_run_yt_dlp_subprocess_terminates_child_on_keyboard_interrupt(self):
        from nhk_radio.downloads import runner
        process = MagicMock()
        process.stdout = iter(["start\n"])
        process.poll.return_value = None
        with (
            patch("nhk_radio.downloads.runner.subprocess.Popen", return_value=process),
            patch("nhk_radio.downloads.runner._parse_yt_dlp_progress", side_effect=KeyboardInterrupt),
            patch("nhk_radio.downloads.runner._terminate_process") as terminate_mock,
        ):
            with self.assertRaises(KeyboardInterrupt):
                runner.run_yt_dlp_subprocess(["yt-dlp"], on_progress=MagicMock())
            # Ctrl+C でも子プロセス (別セッション) を止めてから再送出すること (followup-4 2-2)
            terminate_mock.assert_called_once_with(process)
            process.wait.assert_called()

    def test_run_yt_dlp_subprocess_terminates_child_on_exception(self):
        from nhk_radio.downloads import runner
        process = MagicMock()
        process.stdout = iter(["start\n"])
        process.poll.return_value = None
        with (
            patch("nhk_radio.downloads.runner.subprocess.Popen", return_value=process),
            patch("nhk_radio.downloads.runner._parse_yt_dlp_progress", side_effect=RuntimeError("unexpected")),
            patch("nhk_radio.downloads.runner._terminate_process") as terminate_mock,
        ):
            result = runner.run_yt_dlp_subprocess(["yt-dlp"], on_progress=MagicMock())
            self.assertFalse(result)
            terminate_mock.assert_called_once_with(process)
            process.wait.assert_called()

    def test_run_yt_dlp_subprocess_keyboard_interrupt_before_process_created(self):
        from nhk_radio.downloads import runner
        with (
            patch("nhk_radio.downloads.runner.subprocess.Popen", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            runner.run_yt_dlp_subprocess(["yt-dlp"])


if __name__ == "__main__":
    unittest.main()

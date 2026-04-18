import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio import cli, core, downloads, text


class CoverageGapTest(unittest.TestCase):
    def test_cli_select_episodes_empty(self):
        # cli.py: 68-69 (Empty episodes)
        with patch("builtins.print") as mock_print:
            self.assertIsNone(cli.select_episodes([]))
            mock_print.assert_called_with("  利用可能なエピソードがありません。")

    def test_cli_interactive_fallback_selected_none(self):
        # cli.py: 174-175 (selected is None)
        program = {"site_id": "S", "corner_id": "01", "title": "P", "display_title": "D"}
        with (
            patch.object(cli, "select_program", return_value=program),
            patch.object(cli, "get_episode_list", return_value=([], "cache")),
            patch.object(cli, "select_episodes", return_value=None),
            patch("builtins.print")
        ):
            cli._interactive_cli_fallback([program], Path("/tmp"), audio_only=True)

    def test_cli_interactive_mode_end(self):
        # cli.py: 199-200, 242
        program = {"site_id": "S", "corner_id": "01", "title": "P", "display_title": "D"}
        with (
            patch.object(cli, "fetch_program_list", return_value=[program]),
            patch.object(cli, "browse_programs", return_value=(None, None)),
            patch("nhk_radio.cli.logger")
        ):
            cli.interactive_mode(Path("/tmp"))

    def test_core_http_get_text_full(self):
        # core.py: 40-41 (http_get_text)
        mock_resp = MagicMock()
        mock_resp.text = "content"
        with patch("httpx.Client.get", return_value=mock_resp):
            self.assertEqual(core.http_get_text("http://e.com"), "content")
            mock_resp.raise_for_status.assert_called()

    def test_core_fetch_by_genre_unknown_error(self):
        # core.py: 223 (fetch_by_genre_async error log)
        with (
            patch("httpx.AsyncClient.get", side_effect=Exception("err")),
            patch("nhk_radio.core.logger") as mock_logger
        ):
            import asyncio
            res = asyncio.run(core._fetch_by_genre_async("unknown_genre"))
            self.assertEqual(res, [])
            mock_logger.error.assert_called()

    def test_core_refresh_episode_list_exhausted(self):
        # core.py: 318, 321 (stale cache fail path)
        program = {"site_id": "S", "corner_id": "01", "title": "P", "url": "U"}
        with (
            patch.object(core, "fetch_episodes", side_effect=Exception("network-fail")),
            patch.object(core, "load_episode_cache", return_value=None),
            patch("time.sleep"), self.assertRaisesRegex(RuntimeError, "network-fail")
        ):
            core.refresh_episode_list(program)

    def test_downloads_episode_output_matches_not_file(self):
        # downloads.py: 218 (path.is_file() is False)
        program = {"site_id": "S", "corner_id": "01", "title": "P"}
        episode = {"title": "E"}
        with patch("pathlib.Path.is_file", return_value=False):
            self.assertFalse(downloads._episode_output_matches(Path("any"), program, episode))

    def test_text_char_width_narrow(self):
        # text.py: 159 (return 1)
        self.assertEqual(text._char_width("a"), 1)
        self.assertEqual(text._char_width("1"), 1)


class CoverageGapExtraTest(unittest.TestCase):
    """追加カバレッジ (cache/cli/core/downloads/text の未カバー行を補完)"""

    def test_load_program_cache_returns_none_when_missing(self):
        # cache.py: 42 (items is None path)
        from nhk_radio import cache as cache_mod
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(cache_mod, "PROGRAM_CACHE_DIR", Path(tmp) / "missing"),
        ):
            self.assertIsNone(cache_mod.load_program_cache("language"))

    def test_load_episode_cache_returns_none_when_missing(self):
        from nhk_radio import cache as cache_mod
        from nhk_radio.types import Program
        program = Program(
            title="P", display_title="P", display_date="----",
            site_id="SITE", corner_id="01", url="U",
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(cache_mod, "EPISODE_CACHE_DIR", Path(tmp) / "missing"),
        ):
            self.assertIsNone(cache_mod.load_episode_cache(program))

    def test_load_episode_cache_returns_episodes_when_valid(self):
        # cache.py: 84 (episodes成功パス)
        from nhk_radio import cache as cache_mod
        from nhk_radio.types import Episode, Program
        program = Program(
            title="P", display_title="P", display_date="----",
            site_id="SITE2", corner_id="01", url="U",
        )
        episode = Episode(
            id="ep1", title="Ep", display_title="Ep",
            date="20240415", display_date="2024-04-15",
            broadcast_time="", duration_str="", url="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with (
                patch.object(cache_mod, "EPISODE_CACHE_DIR", base / "episodes"),
                patch.object(cache_mod.time, "time", return_value=1000.0),
            ):
                cache_mod.save_episode_cache(program, [episode])
                loaded = cache_mod.load_episode_cache(program, ttl_seconds=10**9)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded[0].id, "ep1")

    def test_download_selected_episodes_success_path(self):
        # cli.py: 178-180 (successful download path)
        from nhk_radio.types import Episode, Program
        program = Program(
            title="P", display_title="P", display_date="----",
            site_id="S", corner_id="01", url="U",
        )
        episode = Episode(
            id="ep1", title="E", display_title="E",
            date="20240415", display_date="2024-04-15",
            broadcast_time="", duration_str="", url="https://e.com/ep1",
        )
        with (
            patch.object(cli, "is_episode_downloaded", return_value=False),
            patch.object(cli, "download_episode", return_value=True),
            patch.object(cli, "resolve_episode_downloaded_path", return_value=Path("/tmp/out.mp3")),
            patch.object(cli, "mark_episode_downloaded") as mark_mock,
            patch.object(cli, "_program_output_dir", return_value=Path("/tmp")),
            patch.object(cli, "_program_filename_template", return_value="%(id)s.%(ext)s"),
        ):
            count = cli._download_selected_episodes(
                program, [episode], Path("/tmp"), audio_only=True
            )
            self.assertEqual(count, 1)
            mark_mock.assert_called_once()

    def test_http_get_json_async_executes_body(self):
        # core.py: 45-46 (http_get_json_async actual execution)
        import asyncio
        from unittest.mock import AsyncMock
        mock_resp = MagicMock()
        mock_resp.json = MagicMock(return_value={"k": "v"})
        mock_resp.raise_for_status = MagicMock()
        client = MagicMock()
        client.get = AsyncMock(return_value=mock_resp)
        result = asyncio.run(core.http_get_json_async(client, "https://e.com"))
        self.assertEqual(result, {"k": "v"})
        mock_resp.raise_for_status.assert_called_once()

    def test_fetch_all_async_merges_genre_over_new_corners(self):
        # core.py: 206-207 (genre補完パス: corner が new_arrivals と重複した時 genre を上書き)
        import asyncio
        from unittest.mock import AsyncMock
        new_corners = {
            "corners": [
                {"series_site_id": "A", "corner_site_id": "01", "title": "番組A"},
            ]
        }

        async def fake_http(client, url, timeout=15):
            if "corners/new_arrivals" in url:
                return new_corners
            if "language" in url:
                return {
                    "series": [
                        {"series_site_id": "A", "corner_site_id": "01", "title": "番組A"},
                    ]
                }
            return {"series": []}

        with patch.object(core, "http_get_json_async", new=AsyncMock(side_effect=fake_http)):
            programs = asyncio.run(core._fetch_all_async())
            self.assertTrue(any(p.site_id == "A" and p.genre == "language" for p in programs))

    def test_fetch_by_genre_async_non_dict_returns_empty(self):
        # core.py: 228 (data is not dict path)
        import asyncio
        from unittest.mock import AsyncMock
        with patch.object(core, "http_get_json_async", new=AsyncMock(return_value=[])):
            res = asyncio.run(core._fetch_by_genre_async("music"))
            self.assertEqual(res, [])

    def test_fetch_episodes_verbose_logs(self):
        # core.py: 304, 323 (verbose=True logging paths)
        from nhk_radio.types import Program
        program = Program(
            title="P", display_title="P", display_date="----",
            site_id="S", corner_id="01", url="https://example.com/p",
        )
        mock_info = {"entries": [{"id": "ep-1", "title": "第1回"}]}
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info
            episodes = core.fetch_episodes(program, verbose=True)
            self.assertEqual(len(episodes), 1)

    def test_clear_file_scan_cache_without_directory_clears_all(self):
        # downloads.py: 206 (_FILE_SCAN_CACHE.clear() branch)
        downloads._FILE_SCAN_CACHE[Path("/tmp/a")] = (0.0, [])
        downloads._FILE_SCAN_CACHE[Path("/tmp/b")] = (0.0, [])
        downloads._clear_file_scan_cache()
        self.assertEqual(downloads._FILE_SCAN_CACHE, {})

    def test_episode_output_candidates_dedupes_seen_paths(self):
        # downloads.py: 219 (if path in seen: continue)
        from nhk_radio.types import Episode, Program
        program = Program(
            title="番組A", display_title="番組A", display_date="----",
            site_id="S", corner_id="01", url="U",
        )
        episode = Episode(
            id="ep1", title="第1回", display_title="第1回",
            date="20240415", display_date="2024-04-15",
            broadcast_time="", duration_str="", url="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            f = d / "20240415_番組A_第1回.mp3"
            f.write_text("x", encoding="utf-8")
            # 同一ファイルを2回返してdedup分岐を踏ませる
            with patch.object(downloads, "_get_cached_glob_files", return_value=[f, f]):
                candidates = downloads._episode_output_candidates(d, program, episode)
                self.assertEqual(candidates, [f])

    def test_cleanup_partial_episode_files_oserror_logged(self):
        # downloads.py: 320-321 (unlink OSError path)
        from nhk_radio.types import Episode, Program
        program = Program(
            title="番組A", display_title="番組A", display_date="----",
            site_id="S", corner_id="01", url="U",
        )
        episode = Episode(
            id="ep1", title="第1回", display_title="第1回",
            date="20240415", display_date="2024-04-15",
            broadcast_time="", duration_str="", url="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            part = d / "20240415_番組A_第1回.mp3.part"
            part.write_text("x", encoding="utf-8")
            with (
                patch.object(downloads, "_program_search_dirs", return_value=[d]),
                patch.object(Path, "unlink", side_effect=OSError("denied")),
                patch.object(downloads, "logger") as log_mock,
            ):
                downloads.cleanup_partial_episode_files(d, program, episode)
                log_mock.warning.assert_called()

    def test_program_display_title_combines_title_and_corner(self):
        # text.py: 159 (f"[{title}] {corner}" path)
        result = text._program_display_title("番組A", "コーナーB")
        self.assertEqual(result, "[番組A] コーナーB")

    def test_safe_name_strips_trailing_dots_and_spaces(self):
        # text.py: Windows 互換のため末尾のドット/空白を除去する
        self.assertEqual(text._safe_name("番組A "), "番組A")
        self.assertEqual(text._safe_name("番組A."), "番組A")
        self.assertEqual(text._safe_name("番組A . "), "番組A")
        # 全て除去されて空になった場合は fallback を返す
        self.assertEqual(text._safe_name(". ", fallback="x"), "x")

    def test_clear_cache_dir_logs_warning_on_unlink_failure(self):
        # cache.py: _clear_cache_dir で OSError が発生した場合に warning ログが出て継続することを確認
        from nhk_radio import cache as cache_mod
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.json").write_text("{}", encoding="utf-8")
            (d / "b.json").write_text("{}", encoding="utf-8")
            with (
                patch.object(Path, "unlink", side_effect=[OSError("denied"), None]),
                patch.object(cache_mod, "logger") as log_mock,
            ):
                removed = cache_mod._clear_cache_dir(d)
            self.assertEqual(removed, 1)
            log_mock.warning.assert_called()

    def test_refresh_episode_list_returns_fresh_even_when_save_cache_fails(self):
        # core.py: save_episode_cache 失敗時でも取得済みエピソードを返す
        from nhk_radio.types import Episode, Program
        program = Program(
            title="P", display_title="P", display_date="----",
            site_id="S", corner_id="01", url="U",
        )
        fresh = [Episode(
            id="ep1", title="E", display_title="E",
            date="20240415", display_date="2024-04-15",
            broadcast_time="", duration_str="", url="",
        )]
        with (
            patch.object(core, "fetch_episodes", return_value=fresh),
            patch.object(core, "save_episode_cache", side_effect=OSError("disk full")),
            patch("nhk_radio.core.logger") as logger_mock,
        ):
            episodes, source = core.refresh_episode_list(program)
        self.assertEqual((episodes, source), (fresh, "network"))
        logger_mock.warning.assert_called()


if __name__ == "__main__":
    unittest.main()

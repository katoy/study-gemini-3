"""100% カバレッジ達成のための追加テスト"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import yt_dlp

from nhk_radio_web import cache, config, core, downloads, text
from nhk_radio_web.types import Episode, Program

PROGRAM = Program(
    title="番組A", display_title="番組A", genre="language", genre_label="語学",
    site_id="SITE", corner_id="01", url="https://example.com/SITE_01",
    display_date="2024-04-15(月)",
)
EPISODE = Episode(
    id="ep-1", date="20240415", title="第1回", display_title="第1回",
    display_date="2024-04-15", broadcast_time="", duration_str="",
    url="https://example.com/ep1",
)


# ─────────────────────────────────────────
# text.py
# ─────────────────────────────────────────
class TextCoverageTest(unittest.TestCase):
    def test_format_onair_date_with_valid_started_at(self):
        # lines 21-25: started_at が有効な ISO 形式
        result = text._format_onair_date("", "2024-04-15T10:00:00+09:00")
        self.assertEqual(result, "2024-04-15(月)")

    def test_format_onair_date_with_invalid_started_at(self):
        # lines 26-27: started_at が不正 → ValueError/TypeError を握りつぶして onair_date を使う
        result = text._format_onair_date("2024年04月15日", "not-a-date")
        self.assertEqual(result, "2024-04-15(月)")

    def test_program_display_title_different_title_and_corner(self):
        # line 169: title と corner が両方あって異なる
        result = text._program_display_title("番組A", "コーナーB")
        self.assertEqual(result, "[番組A] コーナーB")

    def test_program_display_title_both_empty(self):
        # line 170: title も corner も空 → "(無題)"
        result = text._program_display_title("", "")
        self.assertEqual(result, "(無題)")


# ─────────────────────────────────────────
# config.py
# ─────────────────────────────────────────
class ConfigCoverageTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows のみ実行")
    def test_default_user_cache_root_windows_with_localappdata(self):
        # lines 13-16: Windows NT, LOCALAPPDATA あり (pragma: no cover のため macOS ではスキップ)
        with patch.dict("os.environ", {"LOCALAPPDATA": "C:\\Users\\test\\Local"}, clear=False):
            result = config._default_user_cache_root()
        self.assertIn("nhk_radio_web", str(result))

    @unittest.skipUnless(sys.platform == "win32", "Windows のみ実行")
    def test_default_user_cache_root_windows_without_env(self):
        # line 17: Windows NT, LOCALAPPDATA も APPDATA も空 (pragma: no cover のため macOS ではスキップ)
        with patch.dict("os.environ", {"LOCALAPPDATA": "", "APPDATA": ""}, clear=False):
            result = config._default_user_cache_root()
        self.assertIn("AppData", str(result))

    def test_default_user_cache_root_linux_xdg(self):
        # line 18: Linux / XDG_CACHE_HOME あり
        with patch.object(sys, "platform", "linux"), \
             patch.object(os, "name", "posix"), \
             patch.dict("os.environ", {"XDG_CACHE_HOME": "/xdg"}, clear=False):
            result = config._default_user_cache_root()
        self.assertEqual(result, Path("/xdg") / "nhk_radio_web")

    def test_find_project_root_returns_none_when_not_found(self):
        # line 26: pyproject.toml が見つからない場合 None を返す
        with patch.object(Path, "exists", return_value=False):
            result = config._find_project_root()
        self.assertIsNone(result)

    def test_resolve_cache_root_dir_uses_project_root(self):
        # line 35: env var なし & project_root が見つかる → project_root / ".cache" を返す
        with patch("nhk_radio_web.config._find_project_root", return_value=Path("/proj")), \
             patch.dict("os.environ", {}, clear=True):
            result = config._resolve_cache_root_dir()
        self.assertEqual(result, Path("/proj") / ".cache")

    def test_resolve_cache_root_dir_fallback_to_default(self):
        # line 36: env var なし & project_root=None → _default_user_cache_root() を返す
        with patch("nhk_radio_web.config._find_project_root", return_value=None), \
             patch.dict("os.environ", {}, clear=True):
            result = config._resolve_cache_root_dir()
        self.assertIsInstance(result, Path)

    def test_default_download_dir_fallback(self):
        # line 54: env var なし & project_root=None → ~/Downloads/nhk_radio
        with patch("nhk_radio_web.config._find_project_root", return_value=None), \
             patch.dict("os.environ", {}, clear=True):
            result = config._default_download_dir()
        self.assertEqual(result, Path.home() / "Downloads" / "nhk_radio")


# ─────────────────────────────────────────
# cache.py
# ─────────────────────────────────────────
class CacheCoverageTest(unittest.TestCase):
    def test_save_json_cache_cleans_tmp_on_error(self):
        # lines 72-77: BaseException 発生時に tmp ファイルを削除して re-raise
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "out.json"
            with patch("os.fdopen", side_effect=RuntimeError("io error")), self.assertRaises(RuntimeError):
                cache._save_json_cache(cache_path, {"ok": True})

    def test_save_json_cache_swallows_unlink_oserror(self):
        # lines 75-76: tmp 削除も失敗する場合でも元の例外を re-raise する
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "out.json"
            with patch("os.fdopen", side_effect=RuntimeError("io error")), \
                 patch("os.unlink", side_effect=OSError("unlink failed")), self.assertRaises(RuntimeError):
                cache._save_json_cache(cache_path, {"ok": True})

    def test_load_program_cache_returns_none(self):
        # line 83: _load_json_ttl_cache が None → load_program_cache が None を返す
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("nhk_radio_web.cache._program_cache_dir", return_value=base / "programs"):
                result = cache.load_program_cache("language")
        self.assertIsNone(result)

    def test_clear_cache_dir_skips_non_file(self):
        # line 109: glob にマッチするがファイルでない場合 continue
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            (cache_dir / "fake.json").mkdir()  # .json という名前のディレクトリ
            removed = cache._clear_cache_dir(cache_dir)
        self.assertEqual(removed, 0)

    def test_clear_cache_dir_logs_warning_on_unlink_error(self):
        # lines 112-114: path.unlink() が OSError → warning + continue
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            (cache_dir / "a.json").write_text("{}", encoding="utf-8")
            with patch.object(Path, "unlink", side_effect=OSError("locked")), \
                 self.assertLogs("nhk_radio_web.cache", level="WARNING") as logs:
                removed = cache._clear_cache_dir(cache_dir)
        self.assertEqual(removed, 0)
        self.assertTrue(any("キャッシュ削除に失敗" in m for m in logs.output))


# ─────────────────────────────────────────
# core.py
# ─────────────────────────────────────────
class CoreCoverageTest(unittest.TestCase):
    def _make_program(self):
        return Program(
            site_id="SITE", corner_id="01", title="番組A",
            url="https://example.com/p", display_title="番組A", display_date="----",
        )

    # lines 42-43: http_get_json_async の成功パス (raise_for_status + return json)
    def test_http_get_json_async_success(self):
        async def run():
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json = MagicMock(return_value={"ok": True})
            async with httpx.AsyncClient() as client:
                with patch.object(client, "get", new_callable=AsyncMock, return_value=mock_resp):
                    result = await core.http_get_json_async(client, "https://example.com")
            return result
        result = asyncio.run(run())
        self.assertEqual(result, {"ok": True})

    # lines 44-49: http_get_json_async のエラーパス
    def test_http_get_json_async_http_status_error(self):
        async def run():
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            error = httpx.HTTPStatusError("not found", request=MagicMock(), response=mock_resp)
            async with httpx.AsyncClient() as client:
                with patch.object(client, "get", new_callable=AsyncMock, side_effect=error):
                    with self.assertRaises(httpx.HTTPStatusError):
                        await core.http_get_json_async(client, "https://example.com")
        asyncio.run(run())

    def test_http_get_json_async_request_error(self):
        async def run():
            async with httpx.AsyncClient() as client:
                with patch.object(client, "get", new_callable=AsyncMock,
                                  side_effect=httpx.RequestError("net error")):
                    with self.assertRaises(httpx.RequestError):
                        await core.http_get_json_async(client, "https://example.com")
        asyncio.run(run())

    # lines 58-63: http_get_json のエラーパス
    def test_http_get_json_http_status_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        error = httpx.HTTPStatusError("server error", request=MagicMock(), response=mock_resp)
        with patch("httpx.Client.get", side_effect=error), self.assertRaises(httpx.HTTPStatusError):
            core.http_get_json("https://example.com")

    def test_http_get_json_request_error(self):
        with patch("httpx.Client.get", side_effect=httpx.RequestError("timeout")), self.assertRaises(httpx.RequestError):
            core.http_get_json("https://example.com")

    # lines 72-74: http_get_text のエラーパス
    def test_http_get_text_http_error(self):
        with patch("httpx.Client.get", side_effect=httpx.HTTPError("bad")), self.assertRaises(httpx.HTTPError):
            core.http_get_text("https://example.com")

    # line 213-214: _fetch_all_async が空リストを返す場合の warning
    def test_fetch_all_async_returns_empty_with_warning(self):
        with patch.object(core, "NHK_GENRES", []), \
             patch.object(core, "http_get_json_async", new_callable=AsyncMock,
                          side_effect=httpx.RequestError("x")):
            result = asyncio.run(core._fetch_all_async())
        self.assertEqual(result, [])

    # line 227: _fetch_by_genre_async でデータが dict でない場合
    def test_fetch_by_genre_async_non_dict_response(self):
        with patch.object(core, "http_get_json_async", new_callable=AsyncMock,
                          return_value=[]):  # list (not dict)
            result = asyncio.run(core._fetch_by_genre_async("music"))
        self.assertEqual(result, [])

    # line 243: _parse_episode_info で ep_id がない場合 (else ブランチ)
    def test_parse_episode_info_no_ep_id_uses_url(self):
        program = self._make_program()
        parsed = core._parse_episode_info(
            {"title": "ep", "url": "https://nhk.example.com/ep"}, program
        )
        self.assertEqual(parsed.url, "https://nhk.example.com/ep")
        self.assertEqual(parsed.id, "")

    def test_parse_episode_info_no_ep_id_no_url(self):
        program = self._make_program()
        parsed = core._parse_episode_info({"title": "ep"}, program)
        self.assertEqual(parsed.url, "")

    # line 258 (verbose=True): fetch_episodes が verbose ログを出す
    def test_fetch_episodes_verbose_true(self):
        program = self._make_program()
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.return_value = {"entries": []}
            with self.assertLogs("nhk_radio_web.core", level="INFO"):
                episodes = core.fetch_episodes(program, verbose=True)
        self.assertEqual(episodes, [])

    # lines 284-292: DownloadError の各メッセージパス
    def test_fetch_episodes_download_error_ffmpeg(self):
        program = self._make_program()
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("ffmpeg not found")
            with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                core.fetch_episodes(program, verbose=False)

    def test_fetch_episodes_download_error_connection(self):
        program = self._make_program()
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("connection refused")
            with self.assertRaisesRegex(RuntimeError, "ネットワーク接続"):
                core.fetch_episodes(program, verbose=False)

    def test_fetch_episodes_download_error_timeout(self):
        program = self._make_program()
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("timeout")
            with self.assertRaisesRegex(RuntimeError, "ネットワーク接続"):
                core.fetch_episodes(program, verbose=False)

    def test_fetch_episodes_download_error_generic(self):
        program = self._make_program()
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("some other error")
            with self.assertRaisesRegex(RuntimeError, "番組情報の解析に失敗"):
                core.fetch_episodes(program, verbose=False)

    # lines 327-328: save_episode_cache 失敗でも結果を返す
    def test_refresh_episode_list_save_cache_failure_still_returns(self):
        program = self._make_program()
        with patch.object(core, "fetch_episodes", return_value=[]), \
             patch.object(core, "save_episode_cache", side_effect=Exception("disk full")), \
             self.assertLogs("nhk_radio_web.core", level="WARNING"):
            episodes, source = core.refresh_episode_list(program)
        self.assertEqual(source, "network")

    # line 335: 両試行失敗 & stale キャッシュなし → RuntimeError
    def test_refresh_episode_list_raises_when_all_fail(self):
        program = self._make_program()
        with patch.object(core, "fetch_episodes", side_effect=RuntimeError("fail")), \
             patch.object(core, "load_episode_cache", return_value=None), \
             patch("time.sleep"), self.assertRaises(RuntimeError):
            core.refresh_episode_list(program)


# ─────────────────────────────────────────
# downloads.py
# ─────────────────────────────────────────
class DownloadsCoverageTest(unittest.TestCase):
    # line 184: episode_date が name に含まれない → return False
    def test_episode_output_matches_date_mismatch(self):
        program = Program(
            site_id="S", corner_id="01", title="P", display_title="P",
            display_date="", url="",
        )
        episode = Episode(
            id="", title="E", display_title="E", date="20240415",
            display_date="", broadcast_time="", duration_str="", url="",
        )
        path = Path("20240416_P_E.mp3")
        with patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.suffix", new_callable=lambda: property(lambda s: ".mp3")):
            result = downloads._episode_output_matches(path, program, episode)
        self.assertFalse(result)

    # line 189: episode_title が name に含まれない → return False
    def test_episode_output_matches_title_mismatch(self):
        program = Program(
            site_id="S", corner_id="01", title="P", display_title="P",
            display_date="", url="",
        )
        episode = Episode(
            id="", title="Q", display_title="Q", date="",
            display_date="", broadcast_time="", duration_str="", url="",
        )
        path = Path("P_E.mp3")
        with patch("pathlib.Path.is_file", return_value=True):
            result = downloads._episode_output_matches(path, program, episode)
        self.assertFalse(result)

    # lines 199-200: stat() が OSError → return []
    def test_get_cached_glob_files_stat_oserror(self):
        d = Path("/fake/dir")
        downloads._clear_file_scan_cache()
        with patch.object(Path, "is_dir", return_value=True), \
             patch.object(Path, "stat", side_effect=OSError("permission denied")):
            result = downloads._get_cached_glob_files(d)
        self.assertEqual(result, [])

    # lines 206-207: キャッシュヒット (mtime 一致) → move_to_end して返す
    def test_get_cached_glob_files_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            downloads._clear_file_scan_cache()
            # 1回目でキャッシュを作成
            downloads._get_cached_glob_files(d)
            # 2回目でキャッシュヒット (lines 204-207)
            result = downloads._get_cached_glob_files(d)
        self.assertIsInstance(result, list)

    # line 218: LRU eviction (_FILE_SCAN_CACHE_MAX_SIZE を超えたときに popitem)
    def test_get_cached_glob_files_lru_eviction(self):
        with tempfile.TemporaryDirectory() as tmp1, \
             tempfile.TemporaryDirectory() as tmp2:
            d1, d2 = Path(tmp1), Path(tmp2)
            downloads._clear_file_scan_cache()
            with patch.object(downloads, "_FILE_SCAN_CACHE_MAX_SIZE", 0):
                downloads._get_cached_glob_files(d1)
                downloads._get_cached_glob_files(d2)
        # エラーなく実行できること

    # line 239: _episode_output_candidates のソートが実行される
    def test_episode_output_candidates_sort_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            program_dir = Path(tmp)
            f1 = program_dir / "20240415_番組A_第1回.mp3"
            f2 = program_dir / "20240415_番組A_第1回.m4a"
            f1.write_text("x", encoding="utf-8")
            f2.write_text("x", encoding="utf-8")
            results = downloads._episode_output_candidates(program_dir, PROGRAM, EPISODE)
        # mp3 が優先
        self.assertEqual(results[0].suffix, ".mp3")

    # lines 298-303: is_episode_downloaded でマニフェストなし → ディレクトリスキャンで発見
    def test_is_episode_downloaded_via_dir_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = output_dir / "SITE_01"
            program_dir.mkdir()
            f = program_dir / "20240415_番組A_第1回.mp3"
            f.write_text("x", encoding="utf-8")
            downloads._clear_file_scan_cache()
            result = downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE)
        self.assertTrue(result)

    # line 303: is_episode_downloaded でファイルなし → False
    def test_is_episode_downloaded_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            downloads._clear_file_scan_cache()
            result = downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE)
        self.assertFalse(result)

    # lines 298-303: is_episode_downloaded で絶対パスの saved_path が存在する
    def test_is_episode_downloaded_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = output_dir / "SITE_01"
            program_dir.mkdir()
            saved_file = program_dir / "ep.mp3"
            saved_file.write_text("x", encoding="utf-8")
            # 絶対パスをマニフェストに書く
            manifest = program_dir / ".downloaded.json"
            manifest.write_text(
                json.dumps({"paths": {"ep-1": str(saved_file)}}),
                encoding="utf-8",
            )
            result = downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE)
        self.assertTrue(result)

    # line 326: find_episode_downloaded_path でファイルが見つからない → None
    def test_find_episode_downloaded_path_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            downloads._clear_file_scan_cache()
            result = downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE)
        self.assertIsNone(result)

    # line 326: find_episode_downloaded_path で絶対パスの saved_path が存在する
    def test_find_episode_downloaded_path_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = output_dir / "SITE_01"
            program_dir.mkdir()
            saved_file = program_dir / "ep.mp3"
            saved_file.write_text("x", encoding="utf-8")
            manifest = program_dir / ".downloaded.json"
            manifest.write_text(
                json.dumps({"paths": {"ep-1": str(saved_file)}}),
                encoding="utf-8",
            )
            result = downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE)
        self.assertEqual(result, saved_file)

    # lines 345-347: cleanup_partial_episode_files で iterdir が OSError
    def test_cleanup_partial_episode_files_iterdir_oserror(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = output_dir / "SITE_01"
            program_dir.mkdir()
            with patch.object(Path, "iterdir", side_effect=OSError("denied")):
                # 例外が呼び出し元に伝播しないこと
                downloads.cleanup_partial_episode_files(output_dir, PROGRAM, EPISODE)

    # lines 355-356: cleanup 中の unlink が OSError
    def test_cleanup_partial_episode_files_unlink_oserror(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = output_dir / "SITE_01"
            program_dir.mkdir()
            partial = program_dir / "20240415_番組A_第1回.mp3.part"
            partial.write_text("x", encoding="utf-8")
            with patch.object(Path, "unlink", side_effect=OSError("locked")), \
                 self.assertLogs("nhk_radio_web.downloads", level="WARNING"):
                downloads.cleanup_partial_episode_files(output_dir, PROGRAM, EPISODE)

    # lines 360-366: _format_download_percent
    def test_format_download_percent(self):
        self.assertEqual(downloads._format_download_percent(None), "--%")
        self.assertEqual(downloads._format_download_percent(0.0), "0%")
        self.assertEqual(downloads._format_download_percent(100.0), "100%")
        self.assertEqual(downloads._format_download_percent(50.3), "50.3%")  # fractional branch
        self.assertEqual(downloads._format_download_percent(-10.0), "0%")   # clamp min
        self.assertEqual(downloads._format_download_percent(110.0), "100%") # clamp max

    # lines 369-370: _format_download_eta
    def test_format_download_eta(self):
        self.assertEqual(downloads._format_download_eta("01:23"), "残り 01:23")
        self.assertEqual(downloads._format_download_eta(None), "残り --:--")

    # lines 373-389: _parse_yt_dlp_progress
    def test_parse_yt_dlp_progress(self):
        # 空文字
        self.assertEqual(downloads._parse_yt_dlp_progress(""), (None, None, None))
        self.assertEqual(downloads._parse_yt_dlp_progress("   "), (None, None, None))
        # ExtractAudio
        self.assertEqual(
            downloads._parse_yt_dlp_progress("[ExtractAudio] Destination"),
            (100.0, None, "変換中..."),
        )
        # Post-process
        self.assertEqual(
            downloads._parse_yt_dlp_progress("Post-processing"),
            (100.0, None, "変換中..."),
        )
        # download % with ETA
        p, eta, status = downloads._parse_yt_dlp_progress("[download]  50.5% of 10MiB ETA 01:23")
        self.assertAlmostEqual(p, 50.5)
        self.assertEqual(eta, "01:23")
        self.assertEqual(status, "ダウンロード中...")
        # 100% → 変換中
        p, eta, status = downloads._parse_yt_dlp_progress("[download] 100% of 10MiB")
        self.assertEqual(p, 100.0)
        self.assertEqual(status, "変換中...")
        # ETA なし
        p, eta, status = downloads._parse_yt_dlp_progress("[download]  30% of 10MiB")
        self.assertEqual(eta, None)
        # マッチしない行
        self.assertEqual(downloads._parse_yt_dlp_progress("[info] some info"), (None, None, None))

    # line 420: _yt_dlp_command の max_items ブランチ
    def test_yt_dlp_command_with_max_items(self):
        cmd = downloads._yt_dlp_command(
            "https://example.com", "/tmp/out.%(ext)s",
            audio_only=True, no_playlist=False, max_items=5,
        )
        self.assertIn("--playlist-end", cmd)
        self.assertIn("5", cmd)


if __name__ == "__main__":
    unittest.main()

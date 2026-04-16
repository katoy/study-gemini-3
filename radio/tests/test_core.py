import asyncio
import io
import json
import subprocess
import unittest
from unittest.mock import AsyncMock, patch

from tests import _support  # noqa: F401

from nhk_radio import core


class CoreHelpersTest(unittest.TestCase):
    def test_http_get_helpers(self):
        # http_get_json (sync) のテスト。httpx.Client をモック
        mock_resp = unittest.mock.Mock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status.return_value = None

        with patch("httpx.Client.get", return_value=mock_resp):
            self.assertEqual(core.http_get_json("https://example.com"), {"ok": True})

        mock_resp.text = "hello"
        with patch("httpx.Client.get", return_value=mock_resp):
            self.assertEqual(core.http_get_text("https://example.com"), "hello")

    def test_fetch_program_list_prefers_cache_and_stale_cache(self):
        cached = [{"title": "cached"}]
        with patch.object(core, "load_program_cache", return_value=cached):
            self.assertEqual(core.fetch_program_list("language"), cached)

        fresh = [{"title": "fresh"}]
        with (
            patch.object(core, "load_program_cache", side_effect=[None]),
            patch.object(core, "_fetch_by_genre_async", new_callable=AsyncMock, return_value=fresh),
            patch.object(core, "save_program_cache") as save_mock,
        ):
            self.assertEqual(core.fetch_program_list("language"), fresh)
            save_mock.assert_called_once_with("language", fresh)

        stale = [{"title": "stale"}]
        with (
            patch.object(core, "load_program_cache", side_effect=[None, stale]),
            patch.object(core, "_fetch_all_async", new_callable=AsyncMock, return_value=[]),
        ):
            self.assertEqual(core.fetch_program_list(None), stale)

    def test_url_to_program_and_resolve_program_from_url(self):
        self.assertIsNone(core._url_to_program("https://example.com"))
        self.assertIsNone(core._resolve_program_from_url("https://example.com"))
        parsed = core._url_to_program("https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01")
        self.assertEqual(parsed["site_id"], "SITE")

        cached_program = {
            "title": "番組A",
            "display_title": "番組A",
            "display_date": "2024-04-15(月)",
            "genre": "language",
            "genre_label": "語学",
            "site_id": "SITE",
            "corner_id": "01",
            "url": "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
        }
        with patch.object(core, "load_program_cache", return_value=[cached_program]) as load_cache_mock:
            resolved = core._resolve_program_from_url("https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01")

        self.assertEqual(resolved, cached_program)
        load_cache_mock.assert_called_once_with(None)

        with patch.object(core, "load_program_cache", side_effect=[None, None]) as load_cache_mock:
            resolved = core._resolve_program_from_url(
                "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
                genre="music",
            )

        self.assertEqual(resolved["title"], "SITE_01")
        self.assertEqual(resolved["genre"], "music")
        self.assertEqual(resolved["genre_label"], "音楽")
        self.assertEqual(load_cache_mock.call_count, 2)

    def test_make_entry_and_fallback_program_list(self):
        entry = core._make_entry({"series_site_id": "SITE", "corner_site_id": "01", "corner_name": "コーナー"}, genre="language")
        self.assertEqual(entry["title"], "コーナー")
        self.assertEqual(entry["display_title"], "コーナー")
        fallback = core._fallback_program_list()
        self.assertEqual(fallback[0]["genre"], "language")

    def test_fetch_all_merges_genres_and_falls_back(self):
        # http_get_json_async をモック
        with (
            patch.object(core, "NHK_GENRES", ["language", "music"]),
            patch.object(
                core,
                "http_get_json_async",
                new_callable=AsyncMock,
                side_effect=[
                    {"corners": [{"series_site_id": "SITE", "corner_site_id": "01", "title": "番組A"}]},
                    {"series": [{"series_site_id": "SITE", "corner_site_id": "01", "title": "番組A"}]},
                    {"series": [{"series_site_id": "S2", "corner_site_id": "02", "title": "番組B"}]},
                ],
            ),
        ):
            programs = asyncio.run(core._fetch_all_async())
        self.assertEqual(len(programs), 2)
        self.assertEqual(programs[0]["genre"], "language")
        self.assertEqual(programs[1]["genre"], "music")

        with (
            patch.object(core, "NHK_GENRES", ["language"]),
            patch.object(core, "http_get_json_async", new_callable=AsyncMock, side_effect=RuntimeError("x")),
            patch.object(core, "_fallback_program_list", return_value=[{"title": "fallback"}]),
        ):
            self.assertEqual(asyncio.run(core._fetch_all_async()), [{"title": "fallback"}])

    def test_fetch_by_genre_success_and_failure_paths(self):
        with patch.object(core, "http_get_json_async", new_callable=AsyncMock, return_value={"series": [{"site_id": "SITE", "title": "番組A"}]}):
            programs = asyncio.run(core._fetch_by_genre_async("music"))
        self.assertEqual(len(programs), 1)

        with (
            patch.object(core, "http_get_json_async", new_callable=AsyncMock, side_effect=RuntimeError("bad")),
            patch.object(core, "_fallback_program_list", return_value=[{"title": "fallback"}]),
        ):
            self.assertEqual(asyncio.run(core._fetch_by_genre_async("language")), [{"title": "fallback"}])

        with patch.object(core, "http_get_json_async", new_callable=AsyncMock, side_effect=RuntimeError("bad")):
            self.assertEqual(asyncio.run(core._fetch_by_genre_async("news")), [])

    def test_parse_episode_info_and_report_fetch_result(self):
        program = {"site_id": "SITE", "corner_id": "01"}
        parsed = core._parse_episode_info({"id": "ep1", "title": "第1回", "upload_date": "20240415", "duration": 60}, program)
        self.assertIn("ep1", parsed["url"])
        # ep_id がある場合は stream URL より NHK プレイヤー URL を優先する（期限切れ防止）
        parsed_absolute = core._parse_episode_info({"id": "ep1", "url": "https://example.com"}, program)
        self.assertEqual(parsed_absolute["url"], "https://www.nhk.or.jp/radio/player/ondemand.html?p=ep1")

        with patch("builtins.print") as print_mock:
            core._report_fetch_result([{"id": "ep"}], "", verbose=True)
            core._report_fetch_result([], "ERROR: failed\n", verbose=True)
            core._report_fetch_result([], "", verbose=True)
            core._report_fetch_result([], "", verbose=False)
        self.assertGreaterEqual(print_mock.call_count, 3)

    def test_fetch_episodes_success_and_failure(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組A", "url": "https://example.com/program"}
        success = subprocess.CompletedProcess(
            args=["yt-dlp"],
            returncode=0,
            stdout='\n{"id":"ep-1","title":"第1回","url":"https://example.com/ep1"}\nnot-json\n',
            stderr="",
        )
        with patch.object(core.subprocess, "run", return_value=success), patch("builtins.print") as print_mock:
            core.fetch_episodes(program, verbose=True)
        print_mock.assert_called()

        with patch.object(core.subprocess, "run", return_value=success):
            episodes = core.fetch_episodes(program, verbose=False)
        self.assertEqual(len(episodes), 1)

        failed = subprocess.CompletedProcess(args=["yt-dlp"], returncode=1, stdout="", stderr="")
        with patch.object(core.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "yt-dlp exited with code 1"):
                core.fetch_episodes(program, verbose=False)

        failed_with_detail = subprocess.CompletedProcess(args=["yt-dlp"], returncode=1, stdout="", stderr="ERROR: failed to fetch\n")
        with patch.object(core.subprocess, "run", return_value=failed_with_detail):
            with self.assertRaisesRegex(RuntimeError, "failed to fetch"):
                core.fetch_episodes(program, verbose=False)

        # returncode != 0 でも stdout にエピソードがあれば返す（一部期限切れのケース）
        partial = subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=1,
            stdout='{"id":"ep-1","title":"第1回","url":"https://example.com/ep1"}\n',
            stderr="ERROR: some episodes expired\n",
        )
        with patch.object(core.subprocess, "run", return_value=partial):
            episodes = core.fetch_episodes(program, verbose=False)
        self.assertEqual(len(episodes), 1)

    def test_get_episode_list_and_refresh_episode_list_paths(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組A", "url": "https://example.com/program"}
        cached = [{"id": "cached"}]
        with patch.object(core, "load_episode_cache", return_value=cached):
            self.assertEqual(core.get_episode_list(program), (cached, "cache"))

        with patch.object(core, "refresh_episode_list", return_value=([], "network")) as refresh_mock:
            self.assertEqual(core.get_episode_list(program, use_cache=False), ([], "network"))
            refresh_mock.assert_called_once_with(program, retry_delay=1.0)

        with patch.object(core, "load_episode_cache", return_value=None), patch.object(core, "refresh_episode_list", return_value=([], "network")) as refresh_mock:
            self.assertEqual(core.get_episode_list(program), ([], "network"))
            refresh_mock.assert_called_once_with(program, retry_delay=1.0)

        with (
            patch.object(core, "fetch_episodes", return_value=[]) as fetch_mock,
            patch.object(core, "save_episode_cache") as save_cache_mock,
        ):
            episodes, source = core.refresh_episode_list(program)
        self.assertEqual((episodes, source), ([], "network"))
        fetch_mock.assert_called_once_with(program, verbose=False)
        save_cache_mock.assert_called_once_with(program, [])

        expected = [{"id": "ep-1", "title": "第1回", "url": "https://example.com/ep1"}]
        with (
            patch.object(core, "fetch_episodes", side_effect=[RuntimeError("timeout"), expected]) as fetch_mock,
            patch.object(core, "save_episode_cache") as save_cache_mock,
            patch.object(core.time, "sleep") as sleep_mock,
        ):
            episodes, source = core.refresh_episode_list(program, retry_delay=0.25)
        self.assertEqual((episodes, source), (expected, "network"))
        self.assertEqual(fetch_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.25)
        save_cache_mock.assert_called_once_with(program, expected)

        with (
            patch.object(core, "fetch_episodes", side_effect=[RuntimeError("timeout"), RuntimeError("timeout")]),
            patch.object(core, "load_episode_cache", return_value=[{"id": "stale"}]),
            patch.object(core.time, "sleep"),
        ):
            self.assertEqual(core.refresh_episode_list(program), ([{"id": "stale"}], "stale-cache"))

        with (
            patch.object(core, "fetch_episodes", side_effect=[RuntimeError("timeout"), RuntimeError("timeout")]),
            patch.object(core, "load_episode_cache", return_value=None),
            patch.object(core.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                core.refresh_episode_list(program)


class EpisodeUrlRegressionTest(unittest.TestCase):
    """
    エピソード URL が期限付き m3u8 ストリーム URL になるバグの再発防止テスト。

    修正前: info["url"] (vod-stream.nhk.jp の m3u8) をそのまま保存 → キャッシュ後に期限切れ
    修正後: ep_id がある場合は常に NHK プレイヤー URL を使用 → yt-dlp がダウンロード時に最新 URL を取得
    """

    PROGRAM = {"site_id": "M65G6QLKMY", "corner_id": "01"}
    STREAM_URL = (
        "https://vod-stream.nhk.jp/radioondemand/r/M65G6QLKMY/s/"
        "stream_M65G6QLKMY_abc123/index_48k.m3u8"
    )

    def test_episode_url_is_nhk_player_not_stream_when_ep_id_present(self):
        """ep_id がある場合、期限付きストリーム URL ではなく NHK プレイヤー URL を使う。"""
        info = {"id": "M65G6QLKMY_01_4311868", "url": self.STREAM_URL}
        parsed = core._parse_episode_info(info, self.PROGRAM)
        self.assertNotIn("vod-stream.nhk.jp", parsed["url"], "ストリーム URL が保存されている（期限切れバグ再発）")
        self.assertIn("nhk.or.jp/radio/player", parsed["url"])
        self.assertIn("M65G6QLKMY_01_4311868", parsed["url"])

    def test_episode_player_url_format(self):
        """生成される URL が NHK プレイヤーの正しい形式になっている。"""
        info = {"id": "M65G6QLKMY_01_4311868", "url": self.STREAM_URL}
        parsed = core._parse_episode_info(info, self.PROGRAM)
        expected = "https://www.nhk.or.jp/radio/player/ondemand.html?p=M65G6QLKMY_01_4311868"
        self.assertEqual(parsed["url"], expected)

    def test_episode_id_not_duplicated_in_url(self):
        """ep_id が URL 内で二重になっていない（旧バグ: ?p=M65G6QLKMY_01_M65G6QLKMY_01_4311868）。"""
        info = {"id": "M65G6QLKMY_01_4311868", "url": self.STREAM_URL}
        parsed = core._parse_episode_info(info, self.PROGRAM)
        self.assertNotIn("M65G6QLKMY_01_M65G6QLKMY_01", parsed["url"], "ep_id が二重になっている（テンプレートバグ再発）")

    def test_fallback_to_webpage_url_when_no_ep_id(self):
        """ep_id がない場合は webpage_url にフォールバックする。"""
        info = {"url": self.STREAM_URL, "webpage_url": "https://www.nhk.or.jp/radio/player/ondemand.html?p=M65G6QLKMY_01"}
        parsed = core._parse_episode_info(info, self.PROGRAM)
        self.assertEqual(parsed["url"], "https://www.nhk.or.jp/radio/player/ondemand.html?p=M65G6QLKMY_01")

    def test_fallback_to_stream_url_when_no_ep_id_and_no_webpage_url(self):
        """ep_id も webpage_url もない場合は url にフォールバックする。"""
        info = {"url": self.STREAM_URL}
        parsed = core._parse_episode_info(info, self.PROGRAM)
        self.assertEqual(parsed["url"], self.STREAM_URL)


if __name__ == "__main__":
    unittest.main()

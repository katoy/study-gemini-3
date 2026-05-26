import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from nhk_radio_web import core
from nhk_radio_web.types import Episode, Program


class CoreHelpersTest(unittest.TestCase):
    def test_http_get_helpers(self):
        mock_resp = unittest.mock.Mock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status.return_value = None
        with patch("httpx.Client.get", return_value=mock_resp):
            self.assertEqual(core.http_get_json("https://example.com"), {"ok": True})

        mock_resp.text = "hello"
        with patch("httpx.Client.get", return_value=mock_resp):
            self.assertEqual(core.http_get_text("https://example.com"), "hello")

    def test_http_get_json_error_handling(self):
        """http_get_json のエラーハンドリング。"""
        # HTTPStatusError
        with patch("httpx.Client") as client_mock:
            instance = client_mock.return_value.__enter__.return_value
            mock_resp = unittest.mock.Mock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404", request=unittest.mock.Mock(), response=unittest.mock.Mock(status_code=404)
            )
            instance.get.return_value = mock_resp
            with self.assertRaises(httpx.HTTPStatusError):
                core.http_get_json("https://example.com")

        # RequestError
        with patch("httpx.Client") as client_mock:
            instance = client_mock.return_value.__enter__.return_value
            instance.get.side_effect = httpx.RequestError("Network error")
            with self.assertRaises(httpx.RequestError):
                core.http_get_json("https://example.com")

    def test_http_get_json_async_error_handling(self):
        """http_get_json_async のエラーハンドリング。"""
        async def run_test():
            # HTTPStatusError
            client = AsyncMock(spec=httpx.AsyncClient)
            mock_resp = unittest.mock.Mock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500", request=unittest.mock.Mock(), response=unittest.mock.Mock(status_code=500)
            )
            client.get.return_value = mock_resp
            with self.assertRaises(httpx.HTTPStatusError):
                await core.http_get_json_async(client, "https://example.com")

            # RequestError
            client = AsyncMock(spec=httpx.AsyncClient)
            client.get.side_effect = httpx.RequestError("Async network error")
            with self.assertRaises(httpx.RequestError):
                await core.http_get_json_async(client, "https://example.com")

        asyncio.run(run_test())

    def test_fetch_by_genre_async_error(self):
        with (
            patch.object(core, "http_get_json_async", side_effect=httpx.RequestError("API Error")),
            patch("nhk_radio_web.core.logger") as logger_mock,
        ):
            result = asyncio.run(core._fetch_by_genre_async("music"))
            self.assertEqual(result, [])
            logger_mock.error.assert_called()

    def test_fetch_episodes_error_cases(self):
        program = Program(
            site_id="SITE", corner_id="01", title="番組A",
            url="https://example.com/program", display_title="番組A", display_date="----",
        )
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.return_value = None
            with self.assertRaisesRegex(RuntimeError, "番組情報の取得に失敗しました"):
                core.fetch_episodes(program, verbose=False)

    def test_refresh_episode_list_stale_cache(self):
        program = Program(site_id="SITE", corner_id="01", title="P", url="U", display_title="P", display_date="----")
        stale = [
            Episode(
                id="stale", title="stale", display_title="stale",
                date="2024-04-15", display_date="2024-04-15",
                broadcast_time="", duration_str="", url="",
            )
        ]
        async def run_test():
            def load_cache_side_effect(prog, ttl_seconds=None):
                # デフォルト TTL で呼ばれたら None を返す（API 失敗をシミュレート）
                # ttl_seconds=10**12 で呼ばれたら stale を返す
                if ttl_seconds is None or ttl_seconds < 10**12:
                    return None
                return stale
            with (
                patch.object(core, "fetch_episodes", side_effect=Exception("network-fail")),
                patch.object(core, "load_episode_cache", side_effect=load_cache_side_effect),
                patch("asyncio.sleep"),
            ):
                episodes, source = await core.refresh_episode_list(program)
                self.assertEqual(episodes, stale)
                self.assertEqual(source, "stale-cache")
        asyncio.run(run_test())

        cached = [
            Program(
                title="cached", display_title="cached", display_date="----",
                site_id="S", corner_id="01", url="U", genre="language", genre_label="語学",
            )
        ]
        with patch.object(core, "load_program_cache", return_value=cached):
            self.assertEqual(core.fetch_program_list("language"), cached)

        fresh = [
            Program(
                title="fresh", display_title="fresh", display_date="----",
                site_id="S", corner_id="01", url="U", genre="language", genre_label="語学",
            )
        ]
        with (
            patch.object(core, "load_program_cache", side_effect=[None, None]),
            patch.object(core, "_fetch_by_genre_async", new_callable=AsyncMock, return_value=fresh),
            patch.object(core, "save_program_cache") as save_mock,
        ):
            self.assertEqual(core.fetch_program_list("language"), fresh)
            save_mock.assert_called_once_with("language", fresh)

        stale_list = [
            Program(title="stale", display_title="stale", display_date="----", site_id="S", corner_id="01", url="U")
        ]
        with (
            patch.object(core, "load_program_cache", side_effect=[None, None, stale_list]),
            patch.object(core, "_fetch_all_async", new_callable=AsyncMock, return_value=[]),
        ):
            self.assertEqual(core.fetch_program_list(None), stale_list)

    def test_url_to_program_and_resolve_program_from_url(self):
        self.assertIsNone(core._url_to_program("https://example.com"))
        self.assertIsNone(core._resolve_program_from_url("https://example.com"))
        parsed = core._url_to_program("https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01")
        self.assertEqual(parsed.site_id, "SITE")

        cached_program = Program(
            title="番組A", display_title="番組A", display_date="2024-04-15(月)",
            genre="language", genre_label="語学", site_id="SITE", corner_id="01",
            url="https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
        )
        with patch.object(core, "load_program_cache", return_value=[cached_program]) as load_cache_mock:
            resolved = core._resolve_program_from_url(
                "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01"
            )
        self.assertEqual(resolved, cached_program)
        load_cache_mock.assert_called_once_with(None)

        with patch.object(core, "load_program_cache", side_effect=[None, None]) as load_cache_mock:
            resolved = core._resolve_program_from_url(
                "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
                genre="music",
            )
        self.assertEqual(resolved.title, "SITE_01")
        self.assertEqual(resolved.genre, "music")
        self.assertEqual(resolved.genre_label, "音楽")
        self.assertEqual(load_cache_mock.call_count, 2)

    def test_make_entry_with_corner_name_and_genre(self):
        entry = core._make_entry(
            {"series_site_id": "SITE", "corner_site_id": "01", "corner_name": "コーナー"}, genre="language"
        )
        self.assertEqual(entry.title, "コーナー")
        self.assertEqual(entry.display_title, "コーナー")
        self.assertEqual(entry.genre, "language")

    def test_fetch_all_merges_genres_and_falls_back(self):
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
        self.assertEqual(programs[0].genre, "new_series")
        self.assertEqual(programs[1].genre, "music")

        with (
            patch.object(core, "NHK_GENRES", ["language"]),
            patch.object(core, "http_get_json_async", new_callable=AsyncMock, side_effect=httpx.RequestError("x")),
        ):
            res = asyncio.run(core._fetch_all_async())
            self.assertEqual(res, [])

    def test_fetch_by_genre_success_and_failure_paths(self):
        with patch.object(
            core,
            "http_get_json_async",
            new_callable=AsyncMock,
            return_value={"series": [{"site_id": "SITE", "title": "番組A"}]},
        ):
            programs = asyncio.run(core._fetch_by_genre_async("music"))
        self.assertEqual(len(programs), 1)

        with patch.object(core, "http_get_json_async", new_callable=AsyncMock, side_effect=httpx.HTTPError("bad")):
            self.assertEqual(asyncio.run(core._fetch_by_genre_async("language")), [])
            self.assertEqual(asyncio.run(core._fetch_by_genre_async("news")), [])

    def test_parse_episode_info(self):
        program = Program(
            site_id="SITE", corner_id="01", title="P", url="U", display_title="P", display_date="----"
        )
        parsed = core._parse_episode_info(
            {"id": "ep1", "title": "第1回", "upload_date": "20240415", "duration": 60}, program
        )
        self.assertIn("ep1", parsed.url)
        parsed_absolute = core._parse_episode_info({"id": "ep1", "url": "https://example.com"}, program)
        self.assertEqual(parsed_absolute.url, "https://www.nhk.or.jp/radio/player/ondemand.html?p=ep1")

    def test_fetch_episodes_success_and_failure(self):
        program = Program(
            site_id="SITE", corner_id="01", title="番組A",
            url="https://example.com/program", display_title="番組A", display_date="----",
        )
        mock_info = {"entries": [{"id": "ep-1", "title": "第1回", "url": "https://example.com/ep1"}]}
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info
            episodes = core.fetch_episodes(program, verbose=False)
            self.assertEqual(len(episodes), 1)
            self.assertEqual(episodes[0].id, "ep-1")

        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.side_effect = Exception("failed to fetch")
            with self.assertRaisesRegex(RuntimeError, "failed to fetch"):
                core.fetch_episodes(program, verbose=False)

    def test_get_episode_list_and_refresh_episode_list_paths(self):
        program = Program(
            site_id="SITE", corner_id="01", title="番組A",
            url="https://example.com/program", display_title="番組A", display_date="----",
        )
        cached = [
            Episode(
                id="cached", title="t", display_title="t",
                date="2024-04-15", display_date="2024-04-15",
                broadcast_time="", duration_str="", url="",
            )
        ]
        async def run_test():
            with patch.object(core, "load_episode_cache", return_value=cached):
                self.assertEqual(await core.get_episode_list(program), (cached, "cache"))

            with patch.object(core, "refresh_episode_list", new_callable=AsyncMock, return_value=([], "network")) as refresh_mock:
                self.assertEqual(await core.get_episode_list(program, use_cache=False), ([], "network"))
                refresh_mock.assert_called_once_with(program, retry_delay=1.0)

            with (
                patch.object(core, "load_episode_cache", return_value=None),
                patch.object(core, "refresh_episode_list", new_callable=AsyncMock, return_value=([], "network")) as refresh_mock,
            ):
                self.assertEqual(await core.get_episode_list(program), ([], "network"))
                refresh_mock.assert_called_once_with(program, retry_delay=1.0)

            with (
                patch.object(core, "fetch_episodes", return_value=[]) as fetch_mock,
                patch.object(core, "save_episode_cache") as save_cache_mock,
            ):
                episodes, source = await core.refresh_episode_list(program)
            self.assertEqual((episodes, source), ([], "network"))
            fetch_mock.assert_called_once_with(program, verbose=False)
            save_cache_mock.assert_called_once_with(program, [])
        asyncio.run(run_test())

        expected = [
            Episode(
                id="ep-1", title="第1回", display_title="第1回",
                date="2024-04-15", display_date="2024-04-15",
                broadcast_time="", duration_str="", url="https://example.com/ep1",
            )
        ]
        async def run_test_retry():
            with (
                patch.object(core, "fetch_episodes", side_effect=[RuntimeError("timeout"), expected]) as fetch_mock,
                patch.object(core, "save_episode_cache"),
                patch("asyncio.sleep"),
            ):
                episodes, source = await core.refresh_episode_list(program, retry_delay=0.25)
            self.assertEqual((episodes, source), (expected, "network"))
            self.assertEqual(fetch_mock.call_count, 2)
        asyncio.run(run_test_retry())


if __name__ == "__main__":
    unittest.main()

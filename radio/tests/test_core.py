import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import yt_dlp  # type: ignore[import-untyped]

from nhk_radio import core
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401


class CoreHelpersTest(unittest.TestCase):
    def test_http_get_json_async_retries_on_request_error(self):
        # リクエストエラー → バックオフ → 成功
        mock_resp = unittest.mock.Mock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status.return_value = None

        mock_client = unittest.mock.AsyncMock()
        mock_client.get = unittest.mock.AsyncMock(
            side_effect=[
                httpx.RequestError("connection 1"),
                httpx.RequestError("connection 2"),
                mock_resp,
            ]
        )

        with patch("nhk_radio.core.logger"):
            result = asyncio.run(core.http_get_json_async(mock_client, "https://example.com"))
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_client.get.call_count, 3)

    def test_http_get_json_async_retries_on_429(self):
        # 429 エラー → バックオフ → 成功
        mock_resp = unittest.mock.Mock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status.return_value = None

        error_resp = unittest.mock.Mock()
        error_resp.status_code = 429
        error_resp.headers = {}

        mock_client = unittest.mock.AsyncMock()
        mock_client.get = unittest.mock.AsyncMock(
            side_effect=[
                httpx.HTTPStatusError("429", request=unittest.mock.Mock(), response=error_resp),
                httpx.HTTPStatusError("429", request=unittest.mock.Mock(), response=error_resp),
                mock_resp,
            ]
        )

        with patch("nhk_radio.core.logger"):
            result = asyncio.run(core.http_get_json_async(mock_client, "https://example.com"))
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_client.get.call_count, 3)

    def test_http_get_json_async_retries_on_5xx(self):
        # 500 エラー → バックオフ → 成功
        mock_resp = unittest.mock.Mock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status.return_value = None

        error_resp = unittest.mock.Mock()
        error_resp.status_code = 503
        error_resp.headers = {}

        mock_client = unittest.mock.AsyncMock()
        mock_client.get = unittest.mock.AsyncMock(
            side_effect=[
                httpx.HTTPStatusError("503", request=unittest.mock.Mock(), response=error_resp),
                mock_resp,
            ]
        )

        with patch("nhk_radio.core.logger"):
            result = asyncio.run(core.http_get_json_async(mock_client, "https://example.com"))
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_client.get.call_count, 2)

    def test_http_get_json_async_429_retry_after_header(self):
        # 429 + Retry-After ヘッダー → ヘッダー値を使用
        mock_resp = unittest.mock.Mock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status.return_value = None

        error_resp = unittest.mock.Mock()
        error_resp.status_code = 429
        error_resp.headers = {"Retry-After": "1.5"}

        mock_client = unittest.mock.AsyncMock()
        mock_client.get = unittest.mock.AsyncMock(
            side_effect=[
                httpx.HTTPStatusError("429", request=unittest.mock.Mock(), response=error_resp),
                mock_resp,
            ]
        )

        with (
            patch("nhk_radio.core.logger"),
            patch("nhk_radio.core.asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
        ):
            result = asyncio.run(core.http_get_json_async(mock_client, "https://example.com"))
        self.assertEqual(result, {"ok": True})
        sleep_mock.assert_called_once_with(1.5)

    def test_http_get_json_async_exhausts_retries(self):
        # すべての retry が失敗 → 例外を起こす
        error_resp = unittest.mock.Mock()
        error_resp.status_code = 429
        error_resp.headers = {}

        mock_client = unittest.mock.AsyncMock()
        mock_client.get = unittest.mock.AsyncMock(
            side_effect=httpx.HTTPStatusError("429", request=unittest.mock.Mock(), response=error_resp)
        )

        with (
            patch("nhk_radio.core.logger"),
            patch("nhk_radio.core.asyncio.sleep", new_callable=AsyncMock),
        ):
            with self.assertRaisesRegex(httpx.HTTPStatusError, "429"):
                asyncio.run(core.http_get_json_async(mock_client, "https://example.com"))

    def test_fetch_by_genre_async_error(self):
        # ジャンル取得失敗時の空リスト返却 (language 以外)
        # 注: http_get_json_async がリトライするようになったため、
        # RequestError が複数回発生してから最終的に例外になる
        with (
            patch.object(core, "http_get_json_async", side_effect=httpx.RequestError("API Error")),
            patch("nhk_radio.core.logger") as logger_mock
        ):
            result = asyncio.run(core._fetch_by_genre_async("music"))
            self.assertEqual(result, [])
            logger_mock.error.assert_called()

    def test_fetch_episodes_error_cases(self):
        program = Program(site_id="SITE", corner_id="01", title="番組A", url="https://example.com/program", display_title="番組A", display_date="----")
        # ydl.extract_info が None を返すケース
        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.return_value = None
            with self.assertRaisesRegex(RuntimeError, "番組情報の取得に失敗しました"):
                core.fetch_episodes(program, verbose=False)

    def test_refresh_episode_list_stale_cache(self):
        program = Program(site_id="SITE", corner_id="01", title="P", url="U", display_title="P", display_date="----")
        stale = [Episode(id="stale", title="stale", display_title="stale", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        with (
            patch.object(core, "fetch_episodes", side_effect=Exception("network-fail")),
            patch.object(core, "load_episode_cache", return_value=stale),
            patch("time.sleep")
        ):
            episodes, source = core.refresh_episode_list(program)
            self.assertEqual(episodes, stale)
            self.assertEqual(source, "stale-cache")
        cached = [Program(title="cached", display_title="cached", display_date="----", site_id="S", corner_id="01", url="U", genre="language", genre_label="語学")]
        with patch.object(core, "load_program_cache", return_value=cached):
            self.assertEqual(core.fetch_program_list("language"), cached)

        fresh = [Program(title="fresh", display_title="fresh", display_date="----", site_id="S", corner_id="01", url="U", genre="language", genre_label="語学")]
        with (
            patch.object(core, "load_program_cache", side_effect=[None]),
            patch.object(core, "_fetch_by_genre_async", new_callable=AsyncMock, return_value=fresh),
            patch.object(core, "save_program_cache") as save_mock,
        ):
            self.assertEqual(core.fetch_program_list("language"), fresh)
            save_mock.assert_called_once_with("language", fresh)

        stale_list = [Program(title="stale", display_title="stale", display_date="----", site_id="S", corner_id="01", url="U")]
        with (
            patch.object(core, "load_program_cache", side_effect=[None, stale_list]),
            patch.object(core, "_fetch_all_async", new_callable=AsyncMock, return_value=[]),
        ):
            self.assertEqual(core.fetch_program_list(None), stale_list)

    def test_url_to_program_and_resolve_program_from_url(self):
        self.assertIsNone(core._url_to_program("https://example.com"))
        self.assertIsNone(core._resolve_program_from_url("https://example.com"))
        parsed = core._url_to_program("https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01")
        self.assertEqual(parsed.site_id, "SITE")

        cached_program = Program(
            title="番組A",
            display_title="番組A",
            display_date="2024-04-15(月)",
            genre="language",
            genre_label="語学",
            site_id="SITE",
            corner_id="01",
            url="https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
        )
        with patch.object(core, "load_program_cache", return_value=[cached_program]) as load_cache_mock:
            resolved = core._resolve_program_from_url("https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01")

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
        self.assertEqual(resolved.genres, ("music",))
        self.assertEqual(resolved.genre_labels, ("音楽",))
        self.assertEqual(load_cache_mock.call_count, 2)

    def test_make_entry_with_corner_name_and_genre(self):
        entry = core._make_entry(
            {
                "series_site_id": "SITE",
                "corner_site_id": "01",
                "corner_name": "コーナー",
                "genre_label": "語学講座",
            },
            genre="language",
        )
        self.assertEqual(entry.title, "コーナー")
        self.assertEqual(entry.display_title, "コーナー")
        self.assertEqual(entry.genre, "language")
        self.assertEqual(entry.genres, ("language",))
        self.assertEqual(entry.genre_labels, ("語学講座",))

    def test_fetch_all_concurrency_limited(self):
        """_fetch_all_async() が MAX_CONCURRENT_API_REQUESTS を超える同時リクエストを送らないことを確認"""
        from nhk_radio.constants import MAX_CONCURRENT_API_REQUESTS

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def mock_http_get_json_async(client, url, **kwargs):
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
            try:
                await asyncio.sleep(0.05)
                return {"series": []}
            finally:
                async with lock:
                    concurrent_count -= 1

        with (
            patch.object(core, "NHK_GENRES", ["language", "music", "news", "drama", "sports", "documentary", "variety"]),
            patch.object(core, "http_get_json_async", new_callable=AsyncMock, side_effect=mock_http_get_json_async),
            patch("nhk_radio.core.logger"),
        ):
            asyncio.run(core._fetch_all_async())
        self.assertLessEqual(max_concurrent, MAX_CONCURRENT_API_REQUESTS)

    def test_fetch_all_merges_genres_and_falls_back(self):
        # http_get_json_async をモック
        with (
            patch.object(core, "NHK_GENRES", ["hobby", "music"]),
            patch.object(
                core,
                "http_get_json_async",
                new_callable=AsyncMock,
                side_effect=[
                    {
                        "corners": [
                            {
                                "series_site_id": "SITE",
                                "corner_site_id": "01",
                                "title": "番組A",
                                "genre_label": "新番組",
                            }
                        ]
                    },
                    {
                        "series": [
                            {
                                "series_site_id": "SITE",
                                "corner_site_id": "01",
                                "title": "番組A",
                                "genre_label": "趣味/教養",
                            }
                        ]
                    },
                    {"series": [{"series_site_id": "S2", "corner_site_id": "02", "title": "番組B"}]},
                ],
            ),
        ):
            programs = asyncio.run(core._fetch_all_async())
        self.assertEqual(len(programs), 2)
        self.assertEqual(programs[0].genre, "hobby")
        self.assertEqual(programs[0].genre_labels, ("新番組", "趣味/教養"))
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

    def test_parse_episode_info_and_report_fetch_result(self):
        program = Program(site_id="SITE", corner_id="01", title="P", url="U", display_title="P", display_date="----")
        parsed = core._parse_episode_info(
            {"id": "ep1", "title": "第1回", "upload_date": "20240415", "duration": 60}
        )
        self.assertIn("ep1", parsed.url)
        # ep_id がある場合は stream URL より NHK プレイヤー URL を優先する（期限切れ防止）
        parsed_absolute = core._parse_episode_info({"id": "ep1", "url": "https://example.com"})
        self.assertEqual(parsed_absolute.url, "https://www.nhk.or.jp/radio/player/ondemand.html?p=ep1")

    def test_fetch_episodes_success_and_failure(self):
        program = Program(site_id="SITE", corner_id="01", title="番組A", url="https://example.com/program", display_title="番組A", display_date="----")

        # yt_dlp.YoutubeDL をモック
        mock_info = {
            "entries": [
                {"id": "ep-1", "title": "第1回", "url": "https://example.com/ep1"}
            ]
        }

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

        with patch("yt_dlp.YoutubeDL") as ydl_mock:
            instance = ydl_mock.return_value.__enter__.return_value
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("playlist parse error")

            with self.assertRaisesRegex(RuntimeError, "番組情報の解析に失敗しました: playlist parse error"):
                core.fetch_episodes(program, verbose=False)

    def test_get_episode_list_and_refresh_episode_list_paths(self):
        program = Program(site_id="SITE", corner_id="01", title="番組A", url="https://example.com/program", display_title="番組A", display_date="----")
        cached = [Episode(id="cached", title="t", display_title="t", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        with patch.object(core, "load_episode_cache", return_value=cached):
            self.assertEqual(core.get_episode_list(program), (cached, "cache"))

        with patch.object(core, "refresh_episode_list", return_value=([], "network")) as refresh_mock:
            self.assertEqual(core.get_episode_list(program, use_cache=False), ([], "network"))
            refresh_mock.assert_called_once_with(program, retry_delay=1.0)

        with (
            patch.object(core, "load_episode_cache", return_value=None),
            patch.object(core, "refresh_episode_list", return_value=([], "network")) as refresh_mock,
        ):
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

        expected = [Episode(id="ep-1", title="第1回", display_title="第1回", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="https://example.com/ep1")]
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

        stale_ep = [Episode(id="stale", title="t", display_title="t", date="2024-04-15", display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        with (
            patch.object(core, "fetch_episodes", side_effect=[RuntimeError("timeout"), RuntimeError("timeout"), RuntimeError("timeout")]),
            patch.object(core, "load_episode_cache", return_value=stale_ep),
            patch.object(core.time, "sleep"),
        ):
            self.assertEqual(core.refresh_episode_list(program), (stale_ep, "stale-cache"))

        with (
            patch.object(core, "fetch_episodes", side_effect=[RuntimeError("timeout"), RuntimeError("timeout"), RuntimeError("timeout")]),
            patch.object(core, "load_episode_cache", return_value=None),
            patch.object(core.time, "sleep"),
            self.assertRaisesRegex(RuntimeError, "timeout"),
        ):
            core.refresh_episode_list(program)


class EpisodeUrlRegressionTest(unittest.TestCase):
    """
    エピソード URL が期限付き m3u8 ストリーム URL になるバグの再発防止テスト。

    修正前: info["url"] (vod-stream.nhk.jp の m3u8) をそのまま保存 → キャッシュ後に期限切れ
    修正後: ep_id がある場合は常に NHK プレイヤー URL を使用 → yt-dlp がダウンロード時に最新 URL を取得
    """

    PROGRAM = Program(site_id="M65G6QLKMY", corner_id="01", title="P", url="U", display_title="P", display_date="----")
    STREAM_URL = "https://vod-stream.nhk.jp/radioondemand/r/M65G6QLKMY/s/stream_M65G6QLKMY_abc123/index_48k.m3u8"

    def test_episode_url_is_nhk_player_not_stream_when_ep_id_present(self):
        """ep_id がある場合、期限付きストリーム URL ではなく NHK プレイヤー URL を使う。"""
        info = {"id": "M65G6QLKMY_01_4311868", "url": self.STREAM_URL}
        parsed = core._parse_episode_info(info)
        self.assertNotIn("vod-stream.nhk.jp", parsed.url, "ストリーム URL が保存されている（期限切れバグ再発）")
        self.assertIn("nhk.or.jp/radio/player", parsed.url)
        self.assertIn("M65G6QLKMY_01_4311868", parsed.url)

    def test_episode_player_url_format(self):
        """生成される URL が NHK プレイヤーの正しい形式になっている。"""
        info = {"id": "M65G6QLKMY_01_4311868", "url": self.STREAM_URL}
        parsed = core._parse_episode_info(info)
        expected = "https://www.nhk.or.jp/radio/player/ondemand.html?p=M65G6QLKMY_01_4311868"
        self.assertEqual(parsed.url, expected)

    def test_episode_id_not_duplicated_in_url(self):
        """ep_id が URL 内で二重になっていない（旧バグ: ?p=M65G6QLKMY_01_M65G6QLKMY_01_4311868）。"""
        info = {"id": "M65G6QLKMY_01_4311868", "url": self.STREAM_URL}
        parsed = core._parse_episode_info(info)
        self.assertNotIn(
            "M65G6QLKMY_01_M65G6QLKMY_01", parsed.url, "ep_id が二重になっている（テンプレートバグ再発）"
        )

    def test_fallback_to_webpage_url_when_no_ep_id(self):
        """ep_id がない場合は webpage_url にフォールバックする。"""
        info = {
            "url": self.STREAM_URL,
            "webpage_url": "https://www.nhk.or.jp/radio/player/ondemand.html?p=M65G6QLKMY_01",
        }
        parsed = core._parse_episode_info(info)
        self.assertEqual(parsed.url, "https://www.nhk.or.jp/radio/player/ondemand.html?p=M65G6QLKMY_01")

    def test_fallback_to_stream_url_when_no_ep_id_and_no_webpage_url(self):
        """ep_id も webpage_url もない場合は url にフォールバックする。"""
        info = {"url": self.STREAM_URL}
        parsed = core._parse_episode_info(info)
        self.assertEqual(parsed.url, self.STREAM_URL)

    def test_merge_program_genres_with_no_primary_label(self):
        """primary_label が未設定で primary_genre がある場合、_genre_label() で label を取得。"""
        from nhk_radio.text import _genre_label
        program = Program(
            title="Test", display_title="Test", display_date="2024-01-01",
            site_id="S", corner_id="C", url="", genre="education", genre_label="",  # label empty
            genres=(), genre_labels=()
        )
        merged = core._merge_program_genres(program)
        # primary_genre="education" → _genre_label("education") = "教養"
        self.assertEqual(merged.genre_label, _genre_label("education"))

    def test_normalize_string_tuple_with_string(self):
        """文字列を値として _normalize_string_tuple に渡す（行 16-17）。"""
        from nhk_radio.types import _normalize_string_tuple
        result = _normalize_string_tuple("test")
        self.assertEqual(result, ("test",))


if __name__ == "__main__":
    unittest.main()

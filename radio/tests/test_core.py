import unittest
import subprocess
from unittest.mock import patch

from tests import _support  # noqa: F401

from nhk_radio import core


class CoreHelpersTest(unittest.TestCase):
    def test_resolve_program_from_url_uses_cached_program_metadata_only(self):
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

    def test_resolve_program_from_url_falls_back_without_network_fetch(self):
        with patch.object(core, "load_program_cache", side_effect=[None, None]) as load_cache_mock:
            resolved = core._resolve_program_from_url(
                "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
                genre="music",
            )

        self.assertEqual(resolved["title"], "SITE_01")
        self.assertEqual(resolved["genre"], "music")
        self.assertEqual(resolved["genre_label"], "音楽")
        self.assertEqual(load_cache_mock.call_count, 2)

    def test_refresh_episode_list_caches_empty_results_without_retry(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組A", "url": "https://example.com/program"}
        with (
            patch.object(core, "fetch_episodes", return_value=[]) as fetch_mock,
            patch.object(core, "save_episode_cache") as save_cache_mock,
        ):
            episodes, source = core.refresh_episode_list(program)

        self.assertEqual(episodes, [])
        self.assertEqual(source, "network")
        fetch_mock.assert_called_once_with(program, verbose=False)
        save_cache_mock.assert_called_once_with(program, [])

    def test_refresh_episode_list_retries_after_exception(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組A", "url": "https://example.com/program"}
        expected = [{"id": "ep-1", "title": "第1回", "url": "https://example.com/ep1"}]
        with (
            patch.object(core, "fetch_episodes", side_effect=[RuntimeError("timeout"), expected]) as fetch_mock,
            patch.object(core, "save_episode_cache") as save_cache_mock,
            patch.object(core.time, "sleep") as sleep_mock,
        ):
            episodes, source = core.refresh_episode_list(program, retry_delay=0.25)

        self.assertEqual(episodes, expected)
        self.assertEqual(source, "network")
        self.assertEqual(fetch_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.25)
        save_cache_mock.assert_called_once_with(program, expected)

    def test_fetch_episodes_raises_on_nonzero_exit(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組A", "url": "https://example.com/program"}
        failed = subprocess.CompletedProcess(
            args=["yt-dlp"],
            returncode=1,
            stdout="",
            stderr="ERROR: failed to fetch playlist\n",
        )
        with patch.object(core.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "failed to fetch playlist"):
                core.fetch_episodes(program, verbose=False)


if __name__ == "__main__":
    unittest.main()

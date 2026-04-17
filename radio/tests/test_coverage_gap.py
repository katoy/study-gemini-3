import argparse
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import httpx
import yt_dlp
import tempfile
import time

from nhk_radio import cli, core, text, downloads

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
            patch("time.sleep")
        ):
            with self.assertRaisesRegex(RuntimeError, "network-fail"):
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

if __name__ == "__main__":
    unittest.main()

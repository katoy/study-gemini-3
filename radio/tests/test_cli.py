import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _support  # noqa: F401

from nhk_radio import cli


class CliHelpersTest(unittest.TestCase):
    def test_download_episode_passes_audio_only_flag(self):
        with (
            patch.object(cli, "_download_episode_command", return_value=["yt-dlp"]) as command_mock,
            patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(args=["yt-dlp"], returncode=0)),
        ):
            success = cli.download_episode(
                "https://example.com/episode",
                Path("/tmp/out"),
                "%(title)s.%(ext)s",
                audio_only=False,
                verbose=False,
            )

        self.assertTrue(success)
        command_mock.assert_called_once_with(
            "https://example.com/episode",
            Path("/tmp/out"),
            "%(title)s.%(ext)s",
            audio_only=False,
        )

    def test_interactive_cli_fallback_uses_default_episode_cache(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組"}
        episodes = [{"id": "ep-1", "title": "第1回", "url": "https://example.com/ep1"}]
        with (
            patch.object(cli, "select_program", return_value=program),
            patch.object(cli, "get_episode_list", return_value=(episodes, "cache")) as get_episode_list_mock,
            patch.object(cli, "select_episodes", return_value=episodes),
            patch.object(cli, "_download_selected_episodes", return_value=1),
        ):
            cli._interactive_cli_fallback([program], Path("/tmp/out"), audio_only=True)

        get_episode_list_mock.assert_called_once_with(program)


if __name__ == "__main__":
    unittest.main()

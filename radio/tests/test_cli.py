import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _support  # noqa: F401

from nhk_radio import cli


class CliHelpersTest(unittest.TestCase):
    def test_select_program_paths(self):
        programs = [{"title": "番組A", "display_title": "番組A", "display_date": "----"}]
        with patch("builtins.input", side_effect=["0"]):
            self.assertIsNone(cli.select_program(programs))

        with patch("builtins.input", side_effect=["u", "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01"]):
            selected = cli.select_program(programs)
        self.assertEqual(selected["site_id"], "SITE")

        with patch("builtins.input", side_effect=["bad", "2", "1"]):
            self.assertEqual(cli.select_program(programs), programs[0])

    def test_url_to_program_and_select_episodes_paths(self):
        self.assertIsNone(cli._url_to_program("https://example.com"))
        self.assertEqual(
            cli._url_to_program("https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01")["corner_id"],
            "01",
        )

        episodes = [
            {"id": "ep1", "title": "第1回", "date": "20240415", "display_date": "2024-04-15(月)"},
            {"id": "ep2", "title": "第2回", "date": "20240416", "display_date": "2024-04-16(火)", "broadcast_time": "07:00", "duration_str": "5分0秒"},
        ]
        self.assertIsNone(cli.select_episodes([]))
        with patch("builtins.input", side_effect=["0"]):
            self.assertIsNone(cli.select_episodes(episodes))
        with patch("builtins.input", side_effect=["a"]):
            self.assertEqual(cli.select_episodes(episodes), episodes)
        with patch("builtins.input", side_effect=["3", "1,2"]):
            self.assertEqual(cli.select_episodes(episodes), episodes)
        with patch("builtins.input", side_effect=[EOFError(), "1"]):
            self.assertEqual(cli.select_episodes(episodes), [episodes[0]])

    def test_download_episode_passes_audio_only_flag(self):
        with (
            patch.object(cli, "_download_episode_command", return_value=["yt-dlp"]) as command_mock,
            patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(args=["yt-dlp"], returncode=0)),
            patch("builtins.print") as print_mock,
        ):
            success = cli.download_episode(
                "https://example.com/episode",
                Path("/tmp/out"),
                "%(title)s.%(ext)s",
                audio_only=False,
            )

        self.assertTrue(success)
        print_mock.assert_called_with("  → https://example.com/episode")
        command_mock.assert_called_once_with(
            "https://example.com/episode",
            Path("/tmp/out"),
            "%(title)s.%(ext)s",
            audio_only=False,
        )

    def test_download_url_direct_paths(self):
        with patch.object(cli, "_resolve_program_from_url", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                cli.download_url_direct("bad", Path("/tmp/out"), None, True)
            self.assertEqual(ctx.exception.code, 1)

        program = {"site_id": "SITE", "corner_id": "01", "title": "番組A"}
        with (
            patch.object(cli, "_resolve_program_from_url", return_value=program),
            patch.object(cli, "_program_output_dir", return_value=Path("/tmp/out/SITE_01")),
            patch.object(cli, "_program_filename_template", return_value="%(title)s.%(ext)s"),
            patch.object(cli, "_yt_dlp_command", return_value=["yt-dlp"]) as cmd_mock,
            patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(args=["yt-dlp"], returncode=0)),
        ):
            cli.download_url_direct("https://example.com", Path("/tmp/out"), 3, False, genre="music")
        cmd_mock.assert_called_once()

        with (
            patch.object(cli, "_resolve_program_from_url", return_value=program),
            patch.object(cli, "_program_output_dir", return_value=Path("/tmp/out/SITE_01")),
            patch.object(cli, "_program_filename_template", return_value="%(title)s.%(ext)s"),
            patch.object(cli, "_yt_dlp_command", return_value=["yt-dlp"]),
            patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(args=["yt-dlp"], returncode=9)),
        ):
            with self.assertRaises(SystemExit) as ctx:
                cli.download_url_direct("https://example.com", Path("/tmp/out"), None, True)
            self.assertEqual(ctx.exception.code, 9)

    def test_download_selected_episodes_paths(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組A"}
        episodes = [
            {"id": "ep1", "title": "第1回", "display_title": "第1回", "url": "https://example.com/1"},
            {"id": "ep2", "title": "第2回", "display_title": "第2回", "url": "https://example.com/2"},
            {"id": "ep3", "title": "第3回", "display_title": "第3回", "url": "https://example.com/3"},
        ]
        with (
            patch.object(cli, "_program_output_dir", return_value=Path("/tmp/out/SITE_01")),
            patch.object(cli, "_program_filename_template", return_value="%(title)s.%(ext)s"),
            patch.object(cli, "is_episode_downloaded", side_effect=[True, False, False]),
            patch.object(cli, "download_episode", side_effect=[False, True]),
            patch.object(cli, "resolve_episode_downloaded_path", return_value=Path("/tmp/out/SITE_01/file.mp3")),
            patch.object(cli, "mark_episode_downloaded") as mark_mock,
        ):
            completed = cli._download_selected_episodes(program, episodes, Path("/tmp/out"), audio_only=True)

        self.assertEqual(completed, 1)
        mark_mock.assert_called_once()

    def test_interactive_cli_fallback_paths(self):
        program = {"site_id": "SITE", "corner_id": "01", "title": "番組"}
        episodes = [{"id": "ep-1", "title": "第1回", "url": "https://example.com/ep1"}]
        with patch.object(cli, "select_program", return_value=None):
            cli._interactive_cli_fallback([program], Path("/tmp/out"), audio_only=True)

        with (
            patch.object(cli, "select_program", return_value=program),
            patch.object(cli, "get_episode_list", side_effect=RuntimeError("bad")),
        ):
            with self.assertRaises(SystemExit) as ctx:
                cli._interactive_cli_fallback([program], Path("/tmp/out"), audio_only=True)
            self.assertEqual(ctx.exception.code, 1)

        with (
            patch.object(cli, "select_program", return_value=program),
            patch.object(cli, "get_episode_list", return_value=(episodes, "cache")) as get_episode_list_mock,
            patch.object(cli, "select_episodes", return_value=None),
        ):
            cli._interactive_cli_fallback([program], Path("/tmp/out"), audio_only=True)
        get_episode_list_mock.assert_called_once_with(program)

        with (
            patch.object(cli, "select_program", return_value=program),
            patch.object(cli, "get_episode_list", return_value=(episodes, "cache")),
            patch.object(cli, "select_episodes", return_value=episodes),
            patch.object(cli, "_download_selected_episodes", return_value=1),
        ):
            cli._interactive_cli_fallback([program], Path("/tmp/out"), audio_only=True)

    def test_interactive_mode_paths(self):
        programs = [{"site_id": "SITE", "corner_id": "01", "title": "番組A"}]
        with patch.object(cli, "fetch_program_list", return_value=[]):
            with self.assertRaises(SystemExit) as ctx:
                cli.interactive_mode(Path("/tmp/out"))
            self.assertEqual(ctx.exception.code, 1)

        with (
            patch.object(cli, "fetch_program_list", return_value=programs),
            patch.object(cli, "browse_programs", return_value=(programs[0], [{"id": "ep"}])),
            patch.object(cli, "_download_selected_episodes", return_value=1),
        ):
            cli.interactive_mode(Path("/tmp/out"))

        with (
            patch.object(cli, "fetch_program_list", return_value=programs),
            patch.object(cli, "browse_programs", side_effect=RuntimeError("gui-fail")),
            patch.object(cli, "browse_programs_tui", return_value=(programs[0], [{"id": "ep"}])),
            patch.object(cli, "_download_selected_episodes", return_value=1),
        ):
            cli.interactive_mode(Path("/tmp/out"))

        with (
            patch.object(cli, "fetch_program_list", return_value=programs),
            patch.object(cli, "browse_programs", side_effect=RuntimeError("gui-fail")),
            patch.object(cli, "browse_programs_tui", side_effect=RuntimeError("tui-fail")),
            patch.object(cli, "_interactive_cli_fallback") as fallback_mock,
        ):
            cli.interactive_mode(Path("/tmp/out"))
        fallback_mock.assert_called_once()

    def test_main_dispatch_paths(self):
        with patch("sys.argv", ["nhk-radio", "--clear-cache"]), patch.object(cli, "clear_all_cache", return_value=2):
            cli.main()

        with (
            patch("sys.argv", ["nhk-radio", "https://example.com", "--keep-video", "-g", "music"]),
            patch.object(cli, "download_url_direct") as direct_mock,
        ):
            cli.main()
        direct_mock.assert_called_once_with("https://example.com", Path("./downloads"), None, audio_only=False, genre="music")

        with (
            patch("sys.argv", ["nhk-radio", "-o", "~/out"]),
            patch.object(cli, "interactive_mode") as interactive_mock,
        ):
            cli.main()
        interactive_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()

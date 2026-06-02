import argparse
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio import cli
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401


class CliHelpersTest(unittest.TestCase):
    def test_create_parser_has_all_arguments(self):
        """パーサーが期待されるすべての引数を定義しているか検証する"""
        parser = cli.create_parser()

        # 定義されているべき引数のチェック
        expected_args = {
            "url", "output_dir", "max_items", "keep_video", "clear_cache", "genre", "verbose"
        }
        actions = {a.dest for action in parser._actions for a in [action] if a.dest != "help"}
        for arg in expected_args:
            with self.subTest(arg=arg):
                self.assertIn(arg, actions, f"引数 '{arg}' がパーサーに定義されていません")

    def test_parser_actual_parsing(self):
        """モックを使わず、実際の文字列リストをパースして Namespace を検証する"""
        parser = cli.create_parser()

        # 1) フルオプション
        args = parser.parse_args(["http://test", "-o", "/tmp/out", "-n", "5", "--keep-video", "--verbose"])
        self.assertEqual(args.url, "http://test")
        self.assertEqual(args.output_dir, "/tmp/out")
        self.assertEqual(args.max_items, 5)
        self.assertTrue(args.keep_video)
        self.assertTrue(args.verbose)

        # 2) デフォルト値
        args = parser.parse_args([])
        self.assertEqual(args.output_dir, "./downloads")
        self.assertIsNone(args.max_items)
        self.assertFalse(args.clear_cache)

    def test_select_program_paths(self):
        programs = [
            Program(site_id="SITE", corner_id="01", title="番組A", display_title="番組A", display_date="2024-04-15(月)", url="U"),
        ]
        with patch("builtins.input", side_effect=["1"]):
            self.assertEqual(cli.select_program(programs), programs[0])

    def test_select_episodes_paths(self):
        episodes = [
            Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="2024-04-15(月)", broadcast_time="", duration_str="", url="U"),
        ]
        with patch("builtins.input", side_effect=["1"]):
            self.assertEqual(cli.select_episodes(episodes), episodes)

    def test_download_episode_logging(self):
        with (
            patch.object(cli, "_download_episode_command", return_value=["ls"]),
            patch.object(cli.subprocess, "Popen") as popen_mock,
            patch("nhk_radio.cli.logger") as logger_mock,
        ):
            process = popen_mock.return_value
            process.stdout = []
            process.wait.return_value = 0
            cli.download_episode("http://url", Path("/tmp"), "tmpl")
            logger_mock.debug.assert_called_with("ダウンロード開始: http://url")

    def test_download_episode_reports_progress_and_newline(self):
        with (
            patch.object(cli, "_download_episode_command", return_value=["ls"]),
            patch("nhk_radio.cli.run_yt_dlp_subprocess") as run_mock,
            patch.object(cli.sys.stdout, "write") as write_mock,
            patch.object(cli.sys.stdout, "flush") as flush_mock,
        ):
            def simulate_progress(cmd, on_progress, cancel_event=None):
                if on_progress:
                    on_progress(10.0, None, "downloading")
                return True
            run_mock.side_effect = simulate_progress
            self.assertTrue(cli.download_episode("http://url", Path("/tmp"), "tmpl"))
        write_mock.assert_any_call("\r  進捗:  10.0%")
        write_mock.assert_any_call("\n")
        self.assertGreaterEqual(flush_mock.call_count, 2)

    def test_download_episode_cleans_up_process_on_unexpected_error(self):
        with (
            patch.object(cli, "_download_episode_command", return_value=["ls"]),
            patch("nhk_radio.cli.run_yt_dlp_subprocess") as run_mock,
            patch("nhk_radio.cli.logger") as logger_mock,
        ):
            run_mock.return_value = False
            self.assertFalse(cli.download_episode("http://url", Path("/tmp"), "tmpl"))
            logger_mock.debug.assert_called_with("ダウンロード開始: http://url")

    def test_download_url_direct_success(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="D", display_date="----", url="U")
        with (
            patch.object(cli, "_resolve_program_from_url", return_value=program),
            patch.object(cli, "_program_output_dir", return_value=Path("/tmp/out")),
            patch.object(cli, "_program_filename_template", return_value="t"),
            patch.object(cli, "_yt_dlp_command", return_value=["ls"]),
            patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(args=[], returncode=0)) as run_mock,
        ):
            cli.download_url_direct("http://url", Path("/tmp"), None, True)
            # subprocess.run が呼ばれることを確認
            run_mock.assert_called_once()
            cmd_args = run_mock.call_args[0][0]
            self.assertIn("ls", cmd_args)

    def test_download_url_direct_invalid_url(self):
        with patch.object(cli, "_resolve_program_from_url", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                cli.download_url_direct("bad", Path("/tmp"), None, True)
            self.assertEqual(ctx.exception.code, 1)

    def test_download_selected_episodes_with_skip(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="2024-04-15(月)", broadcast_time="", duration_str="", url="U")]
        with (
            patch.object(cli, "is_episode_downloaded", return_value=True),
            patch("nhk_radio.cli.logger") as logger_mock,
        ):
            count = cli._download_selected_episodes(program, episodes, Path("/tmp"), audio_only=True)
            self.assertEqual(count, 0)
            logger_mock.info.assert_any_call("スキップ: E1 (保存済み)")

    def test_download_selected_episodes_warns_when_history_sync_fails(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="2024-04-15(月)", broadcast_time="", duration_str="", url="U")]
        with (
            patch.object(cli, "is_episode_downloaded", return_value=False),
            patch.object(cli, "download_episode", return_value=True),
            patch.object(cli, "sync_episode_download_history", return_value=None),
            patch("nhk_radio.cli.logger") as logger_mock,
        ):
            count = cli._download_selected_episodes(program, episodes, Path("/tmp"), audio_only=True)
        self.assertEqual(count, 1)
        logger_mock.warning.assert_called_with("ダウンロード履歴の記録に失敗: E1")

    def test_interactive_cli_fallback_flow(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="2024-04-15(月)", broadcast_time="", duration_str="", url="U")]
        with (
            patch.object(cli, "select_program", return_value=program) as select_program_mock,
            patch.object(cli, "get_episode_list", return_value=(episodes, "net")) as get_episode_list_mock,
            patch.object(cli, "select_episodes", return_value=episodes) as select_episodes_mock,
            patch.object(cli, "_download_selected_episodes", return_value=1) as download_mock,
            patch("builtins.print"),
        ):
            cli._interactive_cli_fallback([program], Path("/tmp"), audio_only=True)
            # 各関数が正しい引数で呼ばれたことを確認
            select_program_mock.assert_called_once_with([program])
            get_episode_list_mock.assert_called_once_with(program)
            select_episodes_mock.assert_called_once_with(episodes)
            download_mock.assert_called_once_with(program, episodes, Path("/tmp"), audio_only=True)

    def test_run_cli_dispatch(self):
        # 正常系: --clear-cache
        args = argparse.Namespace(
            url=None, output_dir="/tmp", max_items=None,
            keep_video=False, clear_cache=True, genre=None, verbose=False
        )
        with patch.object(cli, "clear_all_cache", return_value=1):
            self.assertEqual(cli.run_cli(args), 0)

        # 正常系: URL指定
        args.clear_cache = False
        args.url = "http://test"
        with patch.object(cli, "download_url_direct") as direct_mock:
            self.assertEqual(cli.run_cli(args), 0)
            direct_mock.assert_called_once()

    def test_main_exit_code(self):
        """main が run_cli の戻り値を sys.exit に渡しているか検証する"""
        with (
            patch.object(cli, "create_parser"),
            patch.object(cli, "run_cli", return_value=42),
            self.assertRaises(SystemExit) as ctx
        ):
            cli.main()
        self.assertEqual(ctx.exception.code, 42)


if __name__ == "__main__":
    unittest.main()

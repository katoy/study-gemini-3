import argparse
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio import cli
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401


class CliExtendedTest(unittest.TestCase):
    def test_select_program_cancel(self):
        programs = [Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")]
        with patch("builtins.input", side_effect=["0"]):
            self.assertIsNone(cli.select_program(programs))

    def test_select_program_url_input_success(self):
        programs = [Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")]
        target_program = Program(site_id="TARGET", corner_id="02", title="Target", display_title="Target", display_date="----", url="U")
        with (
            patch("builtins.input", side_effect=["u", "http://example.com"]),
            patch("nhk_radio.cli._url_to_program", return_value=target_program),
        ):
            self.assertEqual(cli.select_program(programs), target_program)

    def test_select_program_url_input_invalid_then_retry(self):
        programs = [Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")]
        # 1回目 'u' -> 無効なURL -> 再度入力を求められる -> '1' を入力
        with (
            patch("builtins.input", side_effect=["u", "bad-url", "1"]),
            patch("nhk_radio.cli._url_to_program", return_value=None),
            patch("builtins.print") as print_mock,
        ):
            self.assertEqual(cli.select_program(programs), programs[0])
            print_mock.assert_any_call("  URL の形式が正しくありません: bad-url")

    def test_select_program_invalid_input_then_retry(self):
        programs = [Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")]
        # 数字以外、範囲外、最後に正しい番号
        with patch("builtins.input", side_effect=["abc", "99", "1"]):
            self.assertEqual(cli.select_program(programs), programs[0])

    def test_select_episodes_no_episodes(self):
        with patch("builtins.print") as print_mock:
            self.assertIsNone(cli.select_episodes([]))
            print_mock.assert_any_call("  利用可能なエピソードがありません。")

    def test_select_episodes_cancel(self):
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url="")]
        with patch("builtins.input", side_effect=["0"]):
            self.assertIsNone(cli.select_episodes(episodes))

    def test_select_episodes_with_meta(self):
        episodes = [
            Episode(
                id="ep1",
                title="E1",
                display_title="E1",
                date="20240415",
                display_date="20240415",
                broadcast_time="10:00",
                duration_str="15:00",
                url=""
            )
        ]
        with patch("builtins.input", side_effect=["1"]):
            self.assertEqual(cli.select_episodes(episodes), [episodes[0]])

    def test_select_episodes_all(self):
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url="")]
        with patch("builtins.input", side_effect=["a"]):
            self.assertEqual(cli.select_episodes(episodes), episodes)

    def test_select_episodes_multiple(self):
        episodes = [
            Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url=""),
            Episode(id="ep2", title="E2", display_title="E2", date="20240416", display_date="20240416", broadcast_time="", duration_str="", url=""),
            Episode(id="ep3", title="E3", display_title="E3", date="20240417", display_date="20240417", broadcast_time="", duration_str="", url=""),
        ]
        with patch("builtins.input", side_effect=["1, 3"]):
            selected = cli.select_episodes(episodes)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selected[0].id, "ep1")
            self.assertEqual(selected[1].id, "ep3")

    def test_select_episodes_invalid_then_retry(self):
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url="")]
        # 数字以外、範囲外、最後に正しい番号
        with patch("builtins.input", side_effect=["xyz", "5", "1"]):
            self.assertEqual(cli.select_episodes(episodes), [episodes[0]])

    def test_download_selected_episodes_failure(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url="U")]
        with (
            patch.object(cli, "is_episode_downloaded", return_value=False),
            patch.object(cli, "download_episode", return_value=False),
            patch("nhk_radio.cli.logger") as logger_mock,
        ):
            count = cli._download_selected_episodes(program, episodes, Path("/tmp"), audio_only=True)
            self.assertEqual(count, 0)
            logger_mock.error.assert_called_with("失敗: E1")

    def test_interactive_cli_fallback_no_program(self):
        with patch.object(cli, "select_program", return_value=None):
            cli._interactive_cli_fallback([], Path("/tmp"), audio_only=True)

    def test_interactive_cli_fallback_fetch_error(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        with (
            patch.object(cli, "select_program", return_value=program),
            patch.object(cli, "get_episode_list", side_effect=RuntimeError("error")),
            patch("nhk_radio.cli.logger") as logger_mock,
            self.assertRaises(SystemExit) as ctx
        ):
            cli._interactive_cli_fallback([program], Path("/tmp"), audio_only=True)
        self.assertEqual(ctx.exception.code, 1)
        logger_mock.error.assert_any_call("エピソード一覧を取得できませんでした: error")

    def test_interactive_cli_fallback_no_selection(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url="U")]
        with (
            patch.object(cli, "select_program", return_value=program),
            patch.object(cli, "get_episode_list", return_value=(episodes, "net")),
            patch("builtins.input", return_value="0"),
            patch("builtins.print") as print_mock,
        ):
            cli._interactive_cli_fallback([program], Path("/tmp"), audio_only=True)
            print_mock.assert_any_call("終了します。")

    def test_interactive_mode_gui_fallback(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        with (
            patch.object(cli, "browse_programs", side_effect=RuntimeError("GUI Error")),
            patch.object(cli, "fetch_program_list", return_value=[program]),
            patch.object(cli, "_interactive_cli_fallback") as fallback_mock,
            patch("nhk_radio.cli.logger") as logger_mock,
        ):
            cli.interactive_mode(Path("/tmp"), genre="music")
            logger_mock.warning.assert_called_with("GUI を起動できませんでした: GUI Error")
            # 非同期化により browse_programs が先に呼ばれる
            fallback_mock.assert_called_once()

    def test_interactive_mode_gui_success(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episodes = [Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url="U")]
        with (
            patch.object(cli, "browse_programs", return_value=(program, episodes)),
            patch.object(cli, "_download_selected_episodes", autospec=True, return_value=1) as download_mock,
        ):
            cli.interactive_mode(Path("/tmp"))
            download_mock.assert_called_once_with(program, episodes, Path("/tmp"), audio_only=True)

    def test_interactive_mode_sets_tk_silence_deprecation_on_darwin(self):
        with (
            patch.object(cli.sys, "platform", "darwin"),
            patch.dict(cli.os.environ, {}, clear=True),
            patch.object(cli, "browse_programs", return_value=(None, None)),
        ):
            cli.interactive_mode(Path("/tmp"))
            self.assertEqual(cli.os.environ["TK_SILENCE_DEPRECATION"], "1")

    def test_interactive_mode_no_programs(self):
        # GUI 起動に失敗し、フォールバックで番組が見つからないケース
        with (
            patch.object(cli, "browse_programs", side_effect=RuntimeError("GUI Fail")),
            patch.object(cli, "fetch_program_list", return_value=[]),
            patch("nhk_radio.cli.logger") as logger_mock,
            self.assertRaises(SystemExit) as ctx
        ):
            cli.interactive_mode(Path("/tmp"))
        self.assertEqual(ctx.exception.code, 1)
        logger_mock.error.assert_called_with("番組が見つかりませんでした。")

    def test_download_url_direct_failure(self):
        program = Program(site_id="S", corner_id="01", title="P", display_title="D", display_date="----", url="U")
        with (
            patch.object(cli, "_resolve_program_from_url", return_value=program),
            patch.object(cli, "_program_output_dir", return_value=Path("/tmp/out")),
            patch.object(cli, "_program_filename_template", return_value="t"),
            patch.object(cli, "_yt_dlp_command", return_value=["ls"]),
            patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(args=[], returncode=1)),
            patch("nhk_radio.cli.logger") as logger_mock,
            self.assertRaises(SystemExit) as ctx
        ):
            cli.download_url_direct("http://url", Path("/tmp"), None, True)
        self.assertEqual(ctx.exception.code, 1)
        logger_mock.error.assert_any_call("エラー (終了コード: 1)")

    def test_run_cli_verbose(self):
        args = argparse.Namespace(
            url=None, output_dir="/tmp", max_items=None,
            keep_video=False, clear_cache=False, genre=None, verbose=True
        )
        with (
            patch("nhk_radio.cli.logging.basicConfig") as basicConfig_mock,
            patch.object(cli, "interactive_mode")
        ):
            cli.run_cli(args)
            basicConfig_mock.assert_called_once()
            call_args = basicConfig_mock.call_args[1]
            self.assertEqual(call_args["level"], cli.logging.DEBUG)

if __name__ == "__main__":
    unittest.main()

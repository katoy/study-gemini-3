"""レビュー L6（cli.py）の回帰テスト。"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from nhk_radio import cli
from nhk_radio.types import Episode, Program

PROGRAM = Program(title="P", display_title="P", display_date="", site_id="S", corner_id="01", url="U")


def _episode(episode_id: str) -> Episode:
    """テスト用の Episode を作る。"""
    return Episode(
        id=episode_id, title=episode_id, display_title=episode_id, date="20240415",
        display_date="2024-04-15", broadcast_time="", duration_str="", url=f"https://example.com/{episode_id}",
    )


# ── tkinter が無い環境 ─────────────────────────────


def test_cli_imports_without_tkinter() -> None:
    """tkinter が無くても cli を import でき、URL モードを使える。"""
    code = (
        "import sys\n"
        "sys.modules['tkinter'] = None\n"
        "import nhk_radio.cli as cli\n"
        "print(cli.browse_programs is None)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_interactive_mode_without_gui_uses_cli_fallback(tmp_path: Path) -> None:
    """GUI を import できなかった環境では、対話モードは CLI のフォールバックで動く。"""
    with (
        patch.object(cli, "browse_programs", None),
        patch.object(cli, "fetch_program_list", return_value=[PROGRAM]),
        patch.object(cli, "_interactive_cli_fallback", return_value=0) as fallback_mock,
    ):
        assert cli.interactive_mode(tmp_path) == 0

    fallback_mock.assert_called_once()


# ── -n の検証 ───────────────────────────────────


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_max_items_rejects_non_positive(value: str, capsys: pytest.CaptureFixture[str]) -> None:
    """-n に 0 以下や整数でない値を渡すとエラーで終了する。"""
    parser = cli.create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["https://example.com", "-n", value])

    assert exc_info.value.code == 2
    assert "1 以上の整数" in capsys.readouterr().err


def test_max_items_accepts_positive() -> None:
    """-n に 1 以上を渡すとそのまま使う。"""
    args = cli.create_parser().parse_args(["https://example.com", "-n", "3"])
    assert args.max_items == 3


# ── 対話モードの終了コード ──────────────────────────


def test_download_selected_episodes_counts_failures(tmp_path: Path) -> None:
    """完了件数と失敗件数を返す。保存済みでスキップした回はどちらにも数えない。"""
    episodes = [_episode("ok"), _episode("ng"), _episode("skip")]

    def is_downloaded(_output_dir, _program, episode, *, audio_only):
        return episode.id == "skip"

    with (
        patch.object(cli, "is_episode_downloaded", side_effect=is_downloaded),
        patch.object(cli, "download_episode", side_effect=lambda url, *_a, **_k: url.endswith("ok")),
        patch.object(cli, "sync_episode_download_history", return_value=tmp_path / "ok.mp3"),
    ):
        assert cli._download_selected_episodes(PROGRAM, episodes, tmp_path, audio_only=True) == (1, 1)


@pytest.mark.parametrize(("failed", "expected_code"), [(0, 0), (2, 1)])
def test_interactive_mode_returns_exit_code(tmp_path: Path, failed: int, expected_code: int) -> None:
    """GUI で選んだ回のダウンロードに失敗があれば、終了コード 1 を返す。"""
    with (
        patch.object(cli, "browse_programs", return_value=(PROGRAM, [_episode("e1")])),
        patch.object(cli, "_download_selected_episodes", return_value=(1, failed)),
    ):
        assert cli.interactive_mode(tmp_path) == expected_code


@pytest.mark.parametrize(("failed", "expected_code"), [(0, 0), (1, 1)])
def test_interactive_cli_fallback_returns_exit_code(tmp_path: Path, failed: int, expected_code: int) -> None:
    """CLI のフォールバックでも、失敗があれば終了コード 1 を返す。"""
    with (
        patch.object(cli, "select_program", return_value=PROGRAM),
        patch.object(cli, "get_episode_list", return_value=([_episode("e1")], "network")),
        patch.object(cli, "select_episodes", return_value=[_episode("e1")]),
        patch.object(cli, "_download_selected_episodes", return_value=(0, failed)),
    ):
        assert cli._interactive_cli_fallback([PROGRAM], tmp_path, audio_only=True) == expected_code


def test_run_cli_returns_interactive_exit_code(tmp_path: Path) -> None:
    """run_cli は対話モードの終了コードをそのまま返す。"""
    args = cli.create_parser().parse_args(["-o", str(tmp_path)])
    with patch.object(cli, "interactive_mode", return_value=1):
        assert cli.run_cli(args) == 1

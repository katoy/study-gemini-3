"""削除・退避の直前に、シンボリックリンクを解決して保存先の外を触らないことを確かめる回帰テスト。

マニフェストのパス検証 (G13 で字句的な比較にした) は、保存先の中のディレクトリが
外を指すシンボリックリンクだと見抜けない。ファイルを壊す操作の直前だけ解決して確かめる。
"""

import json
import os
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from nhk_radio import downloads
from nhk_radio.gui.download_manager import DownloadManager
from nhk_radio.types import Episode, Program

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="シンボリックリンクの作成に権限が要る")

PROGRAM = Program(title="P", display_title="P", display_date="", site_id="S", corner_id="01", url="U")
EPISODE = Episode(id="ep1", title="t", display_title="t", date="20240415", display_date="",
                  broadcast_time="", duration_str="", url="https://example.com/ep1")


def _setup_symlinked_dir(tmp_path: Path) -> tuple[Path, Path]:
    """番組ディレクトリの中に外を指すディレクトリのリンクを作り、マニフェストからその先のファイルを指す。"""
    output_dir = tmp_path / "out"
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.mp3"
    victim.write_text("important", encoding="utf-8")
    program_dir = downloads.program_output_dir(output_dir, PROGRAM)
    program_dir.mkdir(parents=True)
    os.symlink(outside, program_dir / "sub")
    (program_dir / ".downloaded.json").write_text(
        json.dumps({"paths": {downloads._episode_key(EPISODE): "sub/victim.mp3"}}), encoding="utf-8"
    )
    return output_dir, victim


def test_is_within_output_dir_rejects_symlinked_parent(tmp_path: Path) -> None:
    """親ディレクトリのリンクが保存先の外を指していれば、外と判定する。"""
    output_dir, victim = _setup_symlinked_dir(tmp_path)
    path = downloads.program_output_dir(output_dir, PROGRAM) / "sub" / "victim.mp3"

    assert downloads.is_within_output_dir(path, output_dir) is False
    assert downloads.is_within_output_dir(victim, output_dir) is False


def test_is_within_output_dir_accepts_regular_and_file_symlink(tmp_path: Path) -> None:
    """保存先の下の普通のファイルと、保存先の下に置いたファイルのリンクは中と判定する。

    ファイル自体のリンクは、削除してもリンクが消えるだけなので問題ない。
    """
    output_dir = tmp_path / "out"
    program_dir = downloads.program_output_dir(output_dir, PROGRAM)
    program_dir.mkdir(parents=True)
    regular = program_dir / "a.mp3"
    regular.write_text("x", encoding="utf-8")
    link = program_dir / "link.mp3"
    os.symlink(tmp_path, link)

    assert downloads.is_within_output_dir(regular, output_dir) is True
    assert downloads.is_within_output_dir(link, output_dir) is True


def test_download_worker_does_not_move_file_outside_output_dir(tmp_path: Path) -> None:
    """再ダウンロード時の退避で、リンクの先 (保存先の外) のファイルを動かしたり消したりしない。"""
    output_dir, victim = _setup_symlinked_dir(tmp_path)
    manager = DownloadManager(output_dir, True, lambda *_args: None)
    with (
        patch("nhk_radio.gui.download_manager.download_episode_command", return_value=["yt-dlp"]),
        patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", return_value=True),
        patch("nhk_radio.gui.download_manager.sync_episode_download_history", return_value=None),
    ):
        manager._download_worker(PROGRAM, EPISODE, "ep1", threading.Event())

    assert victim.read_text(encoding="utf-8") == "important"
    assert not list(victim.parent.glob("*.nhkradio-bak"))


def test_is_within_output_dir_returns_false_on_os_error(tmp_path: Path) -> None:
    """パスを解決できないときは、安全側に倒して外と判定する。"""
    with patch.object(Path, "resolve", side_effect=OSError("loop")):
        assert downloads.is_within_output_dir(tmp_path / "a.mp3", tmp_path) is False


def test_delete_episode_file_refuses_file_outside_output_dir(tmp_path: Path) -> None:
    """GUI の削除は、リンクをたどると保存先の外を指すファイルを消さない。"""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from nhk_radio.gui.listing.operations import GuiOperationsMixin

    output_dir, victim = _setup_symlinked_dir(tmp_path)
    status = MagicMock()
    fake_self = SimpleNamespace(
        displayed_episode_map={"item": EPISODE},
        displayed_program=PROGRAM,
        output_dir=output_dir,
        audio_only=True,
        status_var=status,
    )
    with patch("nhk_radio.gui.listing.operations.mb.askyesno") as ask_mock:
        GuiOperationsMixin._delete_episode_file(fake_self, "item")  # type: ignore[arg-type]

    ask_mock.assert_not_called()
    assert victim.read_text(encoding="utf-8") == "important"
    assert "保存先の外" in status.set.call_args.args[0]

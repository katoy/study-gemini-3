"""レビュー G14（キャンセル時の一時ファイル）の回帰テスト。"""

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nhk_radio.gui.download_manager import DownloadManager
from nhk_radio.types import Episode, Program

PROGRAM = Program(site_id="S1", corner_id="01", title="Prog", display_title="Prog", display_date="----", url="U")
EPISODE = Episode(
    id="E1", title="Ep", display_title="Ep", date="20240415", display_date="2024-04-15",
    broadcast_time="", duration_str="", url="https://example.com/e1",
)


def _run_worker(tmp_path: Path, *, cancelled: bool) -> tuple[MagicMock, list[str]]:
    """yt-dlp が失敗した (または中断された) ときのワーカーを動かし、片付けの呼び出しと結果の種類を返す。"""
    events: list[str] = []
    manager = DownloadManager(tmp_path, True, lambda kind, *_args: events.append(kind))
    cancel_event = threading.Event()
    if cancelled:
        cancel_event.set()
    with (
        patch("nhk_radio.gui.download_manager.download_episode_command", return_value=["yt-dlp"]),
        patch("nhk_radio.gui.download_manager.program_output_dir", return_value=tmp_path),
        patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", return_value=False),
        patch("nhk_radio.gui.download_manager.cleanup_partial_episode_files") as cleanup_mock,
    ):
        manager._download_worker(PROGRAM, EPISODE, "E1", cancel_event)
    return cleanup_mock, events


@pytest.mark.parametrize(("cancelled", "expected_event"), [(True, "cancelled_one"), (False, "failed_one")])
def test_download_worker_cleans_partial_files(tmp_path: Path, cancelled: bool, expected_event: str) -> None:
    """キャンセルしても失敗しても、一時ファイル (.part など) を片付ける。

    GUI は --force-overwrites で yt-dlp を動かし、これは --no-continue を含む。
    残した .part から再開されることは無いため、キャンセル時も残さない。
    """
    cleanup_mock, events = _run_worker(tmp_path, cancelled=cancelled)

    cleanup_mock.assert_called_once_with(tmp_path, PROGRAM, EPISODE)
    assert expected_event in events

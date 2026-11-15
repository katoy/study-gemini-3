"""レビュー L7（core.py のエピソード取得）の回帰テスト。"""

from unittest.mock import patch

import pytest

from nhk_radio import core
from nhk_radio.types import Episode, Program

PROGRAM = Program(
    title="番組A", display_title="番組A", display_date="----",
    site_id="SITE", corner_id="01", url="https://example.com/program",
)

NO_INFO_MESSAGE = "番組情報の取得に失敗しました。番組が終了しているか、一時的にアクセスできない可能性があります。"


def test_fetch_episodes_no_info_raises_once_without_rewrap() -> None:
    """extract_info が None のとき、メッセージを包み直さず、エラーログも 1 回だけ出す。"""
    with patch("yt_dlp.YoutubeDL") as ydl_mock, patch.object(core, "logger") as logger_mock:
        ydl_mock.return_value.__enter__.return_value.extract_info.return_value = None
        with pytest.raises(RuntimeError) as exc_info:
            core.fetch_episodes(PROGRAM, verbose=False)

    assert str(exc_info.value) == NO_INFO_MESSAGE
    assert exc_info.value.__cause__ is None
    logger_mock.error.assert_called_once()


def test_fetch_episodes_unexpected_error_is_wrapped_once() -> None:
    """予期しない例外は従来どおり 1 回だけ包み、エラーログも 1 回だけ出す。"""
    with patch("yt_dlp.YoutubeDL") as ydl_mock, patch.object(core, "logger") as logger_mock:
        ydl_mock.return_value.__enter__.return_value.extract_info.side_effect = ValueError("boom")
        with pytest.raises(RuntimeError, match=r"^エピソード取得失敗: boom$"):
            core.fetch_episodes(PROGRAM, verbose=False)

    logger_mock.error.assert_called_once()


def test_fetch_episodes_does_not_pass_ineffective_retries_option() -> None:
    """一覧取得では効かない yt-dlp の retries オプションを渡さない。"""
    with patch("yt_dlp.YoutubeDL") as ydl_mock:
        ydl_mock.return_value.__enter__.return_value.extract_info.return_value = {"entries": []}
        core.fetch_episodes(PROGRAM, verbose=False)

    ydl_opts = ydl_mock.call_args.args[0]
    assert "retries" not in ydl_opts


def test_refresh_episode_list_returns_empty_stale_cache() -> None:
    """取得に失敗しても、空の stale キャッシュがあれば「キャッシュ無し」とみなさずに返す。"""
    with (
        patch.object(core, "fetch_episodes", side_effect=RuntimeError("network-fail")),
        patch.object(core, "load_episode_cache", return_value=[]),
        patch.object(core.time, "sleep"),
    ):
        assert core.refresh_episode_list(PROGRAM) == ([], "stale-cache")


def test_refresh_episode_list_raises_without_stale_cache() -> None:
    """stale キャッシュが無ければ、最後のエラーで失敗する。"""
    with (
        patch.object(core, "fetch_episodes", side_effect=RuntimeError("network-fail")),
        patch.object(core, "load_episode_cache", return_value=None),
        patch.object(core.time, "sleep"),
        pytest.raises(RuntimeError, match="network-fail"),
    ):
        core.refresh_episode_list(PROGRAM)


def test_refresh_episode_list_returns_nonempty_stale_cache() -> None:
    """中身のある stale キャッシュは従来どおり返す。"""
    stale = [Episode(id="s", title="s", display_title="s", date="20240415", display_date="2024-04-15",
                     broadcast_time="", duration_str="", url="")]
    with (
        patch.object(core, "fetch_episodes", side_effect=RuntimeError("network-fail")),
        patch.object(core, "load_episode_cache", return_value=stale),
        patch.object(core.time, "sleep"),
    ):
        assert core.refresh_episode_list(PROGRAM) == (stale, "stale-cache")

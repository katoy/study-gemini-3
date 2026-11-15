"""ファイル名全体が上限バイト数に収まることの回帰テスト (レビュー L5 の残り)。"""

from pathlib import Path
from unittest.mock import patch

import yt_dlp

from nhk_radio import cli, downloads
from nhk_radio.downloads import filesystem
from nhk_radio.types import Episode, Program


def _program(title: str) -> Program:
    """テスト用の Program を作る。"""
    return Program(title=title, display_title=title, display_date="", site_id="S", corner_id="01", url="U")


def _render(template: str, title: str) -> str:
    """yt-dlp にファイル名テンプレートを展開させ、ファイル名 (ディレクトリを除く) を返す。"""
    with yt_dlp.YoutubeDL({"outtmpl": f"/tmp/dir/{template}", "quiet": True}) as ydl:
        path = ydl.prepare_filename(
            {"title": title, "ext": "mp3", "id": "x", "upload_date": "20240415", "playlist_index": 1}
        )
    return Path(path).name


def test_long_episode_title_fits_in_filename_limit() -> None:
    """エピソード名が長くても、退避や一時ファイルの接尾辞を付けた名前が上限に収まる。"""
    template = downloads.program_filename_template(_program("番組A"))
    name = _render(template, "あ" * 300)

    longest = name + ".part-Frag9999"
    assert len(longest.encode("utf-8")) <= filesystem.FILENAME_MAX_BYTES
    assert len((name + downloads.BACKUP_SUFFIX).encode("utf-8")) <= filesystem.FILENAME_MAX_BYTES
    assert name.startswith("20240415_番組A_ああ")


def test_long_episode_title_fits_with_playlist_index() -> None:
    """件数指定 (playlist_index 付き) のテンプレートでも上限に収まる。"""
    template = downloads.program_filename_template(_program("番組A"), max_items=True)
    name = _render(template, "あ" * 300)

    assert len((name + ".part-Frag9999").encode("utf-8")) <= filesystem.FILENAME_MAX_BYTES


def test_ordinary_title_is_not_truncated() -> None:
    """普通の長さの名前は従来と同じファイル名になる (既存ファイルとの照合を保つ)。"""
    template = downloads.program_filename_template(_program("番組A"))
    assert _render(template, "第1回 はじめに") == "20240415_番組A_第1回 はじめに.mp3"


def test_episode_title_budget_has_minimum() -> None:
    """番組名が極端に長くても、エピソード名には最低限のバイト数を残す。"""
    assert filesystem._episode_title_max_bytes("あ" * 85) == filesystem.EPISODE_TITLE_MIN_BYTES


# ── CLI: 実際の保存先をマニフェストに記録する ─────────────────


PROGRAM = _program("番組A")
EPISODE = Episode(id="ep1", title="t", display_title="t", date="20240415", display_date="",
                  broadcast_time="", duration_str="", url="https://example.com/ep1")


def test_download_episode_reports_output_path() -> None:
    """CLI の download_episode は、yt-dlp が出力した保存先を on_output_path に渡す。"""
    reported: list[Path] = []

    def fake_run(cmd, *, on_progress=None, on_output_path=None, **_kwargs):
        if on_output_path:
            on_output_path(Path("/tmp/out/20240415_番組A_t.mp3"))
        return True

    with patch.object(cli, "run_yt_dlp_subprocess", side_effect=fake_run):
        assert cli.download_episode("u", Path("/tmp/out"), "tmpl", on_output_path=reported.append)

    assert reported == [Path("/tmp/out/20240415_番組A_t.mp3")]


def test_download_selected_episodes_marks_reported_path(tmp_path: Path) -> None:
    """保存先が分かれば、名前のパターン照合に頼らずマニフェストに記録する (名前を詰めた回でも保存済みと分かる)。"""
    saved = tmp_path / "S_01" / "20240415_番組A_とても長い名前を詰めたもの.mp3"
    saved.parent.mkdir(parents=True)
    saved.write_text("x", encoding="utf-8")

    def fake_download(_url, _target, _tmpl, *, audio_only, on_output_path=None):
        if on_output_path:
            on_output_path(saved)
        return True

    with (
        patch.object(cli, "is_episode_downloaded", return_value=False),
        patch.object(cli, "download_episode", side_effect=fake_download),
        patch.object(cli, "mark_episode_downloaded") as mark_mock,
        patch.object(cli, "sync_episode_download_history") as sync_mock,
    ):
        assert cli._download_selected_episodes(PROGRAM, [EPISODE], tmp_path, audio_only=True) == (1, 0)

    mark_mock.assert_called_once_with(tmp_path, PROGRAM, EPISODE, saved)
    sync_mock.assert_not_called()

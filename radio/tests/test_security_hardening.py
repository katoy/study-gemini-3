"""レビュー L4（セキュリティ）および 2026-11-17 セキュリティレビューの回帰テスト。"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from nhk_radio import cli, core, downloads
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401

PROGRAM = Program(
    title="番組A",
    display_title="番組A",
    genre="language",
    genre_label="語学",
    site_id="SITE",
    corner_id="01",
    url="https://example.com/SITE_01",
    display_date="2024-04-15(月)",
)

EPISODE = Episode(
    id="ep-1",
    date="20240415",
    title="第1回",
    display_title="第1回",
    display_date="2024-04-15",
    broadcast_time="",
    duration_str="",
    url="https://example.com/ep1",
)


def _program(title: str = "番組A", site_id: str = "SITE", corner_id: str = "01") -> Program:
    """テスト用の Program を作る。"""
    return Program(
        title=title,
        display_title=title,
        display_date="",
        site_id=site_id,
        corner_id=corner_id,
        url="https://example.com/x",
    )


def _write_manifest(output_dir: Path, saved_path: str) -> None:
    """番組ディレクトリに、ep-1 の保存先を saved_path とするマニフェストを書く。"""
    program_dir = downloads.program_output_dir(output_dir, PROGRAM)
    program_dir.mkdir(parents=True, exist_ok=True)
    (program_dir / ".downloaded.json").write_text(
        json.dumps({"paths": {downloads._episode_key(EPISODE): saved_path}}), encoding="utf-8"
    )


def _render(template: str) -> str:
    """yt-dlp に出力テンプレートを展開させた結果を返す。"""
    with yt_dlp.YoutubeDL({"outtmpl": template, "quiet": True}) as ydl:
        return ydl.prepare_filename({"title": "T", "ext": "mp3", "id": "x", "upload_date": "20240415"})


# ── マニフェストのパス検証 ─────────────────────────────


def test_find_episode_downloaded_path_rejects_parent_traversal(tmp_path: Path) -> None:
    """マニフェストの `../` で保存先の外を指すパスは返さない。"""
    output_dir = tmp_path / "out"
    outside = tmp_path / "victim.mp3"
    outside.write_text("x", encoding="utf-8")
    _write_manifest(output_dir, "../../victim.mp3")

    assert downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE) is None


def test_find_episode_downloaded_path_rejects_absolute_outside(tmp_path: Path) -> None:
    """マニフェストの絶対パスが保存先の外なら返さない。"""
    output_dir = tmp_path / "out"
    outside = tmp_path / "victim.mp3"
    outside.write_text("x", encoding="utf-8")
    _write_manifest(output_dir, str(outside))

    assert downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE) is None


def test_find_episode_downloaded_path_accepts_absolute_inside(tmp_path: Path) -> None:
    """保存先の下にある絶対パス（旧ディレクトリの記録）は従来どおり返す。"""
    output_dir = tmp_path / "out"
    legacy = output_dir / "語学" / "別名" / "saved.mp3"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("x", encoding="utf-8")
    _write_manifest(output_dir, str(legacy))

    assert downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE) == legacy


def test_check_downloaded_episodes_ignores_outside_path(tmp_path: Path) -> None:
    """保存済み判定でも、保存先の外を指すマニフェストの記録は数えない。"""
    output_dir = tmp_path / "out"
    (tmp_path / "victim.mp3").write_text("x", encoding="utf-8")
    _write_manifest(output_dir, "../../victim.mp3")

    assert downloads.get_downloaded_episode_keys(output_dir, PROGRAM, [EPISODE]) == set()


# ── yt-dlp コマンドの `--` ─────────────────────────────


def test_yt_dlp_command_puts_double_dash_before_url() -> None:
    """URL の直前に `--` を置き、`-` で始まる URL をオプションと解釈させない。"""
    cmd = downloads._yt_dlp_command("--exec=evil", "x", audio_only=True, no_playlist=True)

    assert cmd[-2:] == ["--", "--exec=evil"]


def test_download_episode_command_puts_double_dash_before_url() -> None:
    """エピソード用のコマンドでも URL の直前に `--` を置く。"""
    cmd = downloads.download_episode_command("https://e", Path("/tmp"), "%(title)s.%(ext)s")

    assert cmd[-2:] == ["--", "https://e"]


# ── 出力テンプレートの `%` エスケープ ─────────────────────


def test_program_filename_template_escapes_percent() -> None:
    """番組名の `%` は `%%` にエスケープし、yt-dlp が番組名をそのまま出力する。"""
    template = downloads.program_filename_template(_program(title="100%(新)"))

    title_bytes = downloads.filesystem._episode_title_max_bytes("100%(新)")
    date_field = downloads.filesystem.FILENAME_DATE_FIELD
    assert template == f"{date_field}_100%%(新)_%(title).{title_bytes}B.%(ext)s"
    assert _render(template) == "20240415_100%(新)_T.mp3"


def test_download_episode_command_escapes_percent_in_output_dir() -> None:
    """保存先ディレクトリ名の `%` もエスケープする。"""
    cmd = downloads.download_episode_command("https://e", Path("/tmp/50%(dir)"), "%(title)s.%(ext)s")
    template = cmd[cmd.index("-o") + 1]

    assert template == str(Path("/tmp/50%%(dir)") / "%(title)s.%(ext)s")
    assert _render(template) == str(Path("/tmp/50%(dir)") / "T.mp3")


def test_output_template_without_percent_is_unchanged() -> None:
    """`%` を含まない保存先はそのまま連結する。"""
    assert downloads.output_template(Path("/tmp/out"), "a.mp3") == str(Path("/tmp/out") / "a.mp3")


# ── site_id / corner_id の無害化 ─────────────────────────


def test_program_storage_id_sanitizes_ids() -> None:
    """site_id / corner_id のパス区切りを置き換え、保存先の外へ出ないようにする。"""
    storage_id = downloads._program_storage_id(_program(site_id="../../etc", corner_id="a/b"))

    assert "/" not in storage_id
    assert "\\" not in storage_id
    assert storage_id == ".._.._etc_a_b"


def test_program_storage_id_keeps_normal_ids() -> None:
    """通常の英数字の ID は変わらない（既存の保存先を保つ）。"""
    assert downloads._program_storage_id(_program(site_id="SITE", corner_id="01")) == "SITE_01"


# ── S1: _play_episode_file のメディア拡張子と境界検証 ────────────────


def test_play_episode_file_rejects_non_media_extension(tmp_path: Path) -> None:
    """--keep-video 時でもメディア拡張子以外のファイル（スクリプト等）は再生・起動しない。"""
    pytest.importorskip("tkinter")
    from nhk_radio.gui.listing.operations import GuiOperationsMixin

    output_dir = tmp_path / "out"
    program_dir = downloads.program_output_dir(output_dir, PROGRAM)
    program_dir.mkdir(parents=True)
    payload = program_dir / "payload.sh"
    payload.write_text("#!/bin/sh\necho evil\n", encoding="utf-8")
    _write_manifest(output_dir, "payload.sh")

    status = MagicMock()
    fake_self = SimpleNamespace(
        displayed_episode_map={"item": EPISODE},
        displayed_program=PROGRAM,
        output_dir=output_dir,
        audio_only=False,
        status_var=status,
    )
    with patch("subprocess.Popen") as popen_mock:
        GuiOperationsMixin._play_episode_file(fake_self, "item")  # type: ignore[arg-type]

    popen_mock.assert_not_called()
    assert "再生できないファイル形式" in status.set.call_args.args[0]


def test_play_episode_file_rejects_outside_symlink_parent(tmp_path: Path) -> None:
    """親ディレクトリのシンボリックリンクが保存先の外を指していれば再生しない。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("シンボリックリンクの作成に権限が要る")
    pytest.importorskip("tkinter")
    from nhk_radio.gui.listing.operations import GuiOperationsMixin

    output_dir = tmp_path / "out"
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.mp3"
    victim.write_text("x", encoding="utf-8")
    program_dir = downloads.program_output_dir(output_dir, PROGRAM)
    program_dir.mkdir(parents=True)
    os.symlink(outside, program_dir / "sub")
    _write_manifest(output_dir, "sub/victim.mp3")

    status = MagicMock()
    fake_self = SimpleNamespace(
        displayed_episode_map={"item": EPISODE},
        displayed_program=PROGRAM,
        output_dir=output_dir,
        audio_only=True,
        status_var=status,
    )
    with patch("subprocess.Popen") as popen_mock:
        GuiOperationsMixin._play_episode_file(fake_self, "item")  # type: ignore[arg-type]

    popen_mock.assert_not_called()
    assert "保存先の外" in status.set.call_args.args[0]


def test_play_episode_file_rejects_file_symlink_pointing_outside(tmp_path: Path) -> None:
    """ファイル自体のシンボリックリンクが保存先の外を指している場合も再生しない。"""
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("シンボリックリンクの作成に権限が要る")
    pytest.importorskip("tkinter")
    from nhk_radio.gui.listing.operations import GuiOperationsMixin

    output_dir = tmp_path / "out"
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.mp3"
    victim.write_text("x", encoding="utf-8")
    program_dir = downloads.program_output_dir(output_dir, PROGRAM)
    program_dir.mkdir(parents=True)
    os.symlink(victim, program_dir / "link.mp3")
    _write_manifest(output_dir, "link.mp3")

    status = MagicMock()
    fake_self = SimpleNamespace(
        displayed_episode_map={"item": EPISODE},
        displayed_program=PROGRAM,
        output_dir=output_dir,
        audio_only=True,
        status_var=status,
    )
    with patch("subprocess.Popen") as popen_mock:
        GuiOperationsMixin._play_episode_file(fake_self, "item")  # type: ignore[arg-type]

    popen_mock.assert_not_called()
    assert "保存先の外" in status.set.call_args.args[0]


def test_play_episode_file_allows_valid_media_inside_output_dir(tmp_path: Path) -> None:
    """保存先内の許可されたメディアファイル（.mp4 等）は絶対パスで再生できる。"""
    pytest.importorskip("tkinter")
    from nhk_radio.gui.listing.operations import GuiOperationsMixin

    output_dir = tmp_path / "out"
    program_dir = downloads.program_output_dir(output_dir, PROGRAM)
    program_dir.mkdir(parents=True)
    media = program_dir / "valid.mp4"
    media.write_text("x", encoding="utf-8")
    _write_manifest(output_dir, "valid.mp4")

    status = MagicMock()
    fake_self = SimpleNamespace(
        displayed_episode_map={"item": EPISODE},
        displayed_program=PROGRAM,
        output_dir=output_dir,
        audio_only=False,
        status_var=status,
    )
    with patch("sys.platform", "darwin"), patch("subprocess.Popen") as popen_mock:
        GuiOperationsMixin._play_episode_file(fake_self, "item")  # type: ignore[arg-type]

    popen_mock.assert_called_once_with(["open", os.path.abspath(media)])
    assert "再生中: valid.mp4" in status.set.call_args.args[0]


# ── S2: open_downloaded_folder のディレクトリ検証と絶対パス化 ──────────


def test_open_downloaded_folder_rejects_regular_file(tmp_path: Path) -> None:
    """ディレクトリではない通常ファイルを渡された場合は開かずに False を返す。"""
    regular_file = tmp_path / "payload.sh"
    regular_file.write_text("#!/bin/sh\n", encoding="utf-8")

    with patch("subprocess.run") as run_mock:
        assert downloads.open_downloaded_folder(regular_file) is False

    run_mock.assert_not_called()


def test_open_downloaded_folder_resolves_dash_prefixed_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-` で始まる相対パスでも絶対パスに解決し、コマンドオプションと誤認させない。"""
    dash_dir = tmp_path / "-a"
    dash_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    with patch("sys.platform", "darwin"), patch("subprocess.run") as run_mock:
        assert downloads.open_downloaded_folder(Path("-a")) is True

    expected = os.path.abspath(dash_dir)
    assert not expected.startswith("-")
    run_mock.assert_called_once_with(["open", expected], check=True)


# ── S3: URL のスキーム/ホスト検証と正規化 URL 引き渡し ────────────────


def test_url_to_program_rejects_untrusted_scheme_and_host() -> None:
    """www.nhk.or.jp 以外のホストや http/https 以外のスキームを拒否する。"""
    assert core.url_to_program("https://evil.example.com/detail.html?p=SITE_01") is None
    assert core.url_to_program("file:///etc/passwd?p=SITE_01") is None
    assert core.url_to_program("https://www.nhk.or.jp/radio/ondemand/") is None
    parsed = core.url_to_program("https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01")
    assert parsed is not None
    assert parsed.url == "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01"


def test_download_url_direct_passes_canonical_program_url(tmp_path: Path) -> None:
    """download_url_direct は生入力 URL ではなく正規化済みの program.url を yt-dlp へ渡す。"""
    raw_url = "https://www.nhk.or.jp/radio/player/ondemand.html?p=SITE_01&extra=1"
    canonical_program = Program(
        title="SITE_01",
        display_title="SITE_01",
        display_date="----",
        site_id="SITE",
        corner_id="01",
        url="https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01",
    )
    with (
        patch.object(cli, "resolve_program_from_url", return_value=canonical_program),
        patch.object(cli, "_yt_dlp_command", wraps=cli._yt_dlp_command) as cmd_spy,
        patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess(args=[], returncode=0)),
    ):
        cli.download_url_direct(raw_url, tmp_path, None, True)

    assert cmd_spy.call_args.args[0] == canonical_program.url


# ── S4: _open_nhk_program_page の URL スキーム/ホスト検証 ─────────────


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://evil.example.com/radio/ondemand/detail.html?p=SITE_01",
    ],
)
def test_open_nhk_program_page_rejects_unsafe_url(unsafe_url: str) -> None:
    """www.nhk.or.jp 以外や http/https 以外の URL は webbrowser.open に渡さない。"""
    pytest.importorskip("tkinter")
    from nhk_radio.gui.listing.programs import GuiProgramsMixin

    prog = Program(
        title="番組A",
        display_title="番組A",
        display_date="----",
        site_id="SITE",
        corner_id="01",
        url=unsafe_url,
    )
    status = MagicMock()
    fake_self = SimpleNamespace(displayed_program=prog, status_var=status)
    with patch("nhk_radio.gui.listing.programs.webbrowser.open") as open_mock:
        GuiProgramsMixin._open_nhk_program_page(fake_self)  # type: ignore[arg-type]

    open_mock.assert_not_called()
    assert "無効な番組 URL" in status.set.call_args.args[0]


def test_open_nhk_program_page_allows_valid_nhk_url() -> None:
    """正規の NHK 番組 URL は webbrowser.open で開く。"""
    pytest.importorskip("tkinter")
    from nhk_radio.gui.listing.programs import GuiProgramsMixin

    valid_url = "https://www.nhk.or.jp/radio/ondemand/detail.html?p=SITE_01"
    prog = Program(
        title="番組A",
        display_title="番組A",
        display_date="----",
        site_id="SITE",
        corner_id="01",
        url=valid_url,
    )
    status = MagicMock()
    fake_self = SimpleNamespace(displayed_program=prog, status_var=status)
    with patch("nhk_radio.gui.listing.programs.webbrowser.open") as open_mock:
        GuiProgramsMixin._open_nhk_program_page(fake_self)  # type: ignore[arg-type]

    open_mock.assert_called_once_with(valid_url)

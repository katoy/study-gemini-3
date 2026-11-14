"""レビュー L4（セキュリティ）の回帰テスト。"""

import json
from pathlib import Path

import yt_dlp

from nhk_radio import downloads
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

    assert template == "%(upload_date)s_100%%(新)_%(title)s.%(ext)s"
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

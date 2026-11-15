"""ファイル名の日付を JST にすることの回帰テスト (レビュー L1 の残り)。

yt-dlp の upload_date は UTC の日付で、JST 0〜9 時の放送は前日になる。
新しく保存するファイル名は JST の日付にし、UTC の日付で保存済みの既存ファイルも引き続き見つける。
"""

from pathlib import Path

import pytest
import yt_dlp

from nhk_radio import downloads
from nhk_radio.downloads import filesystem
from nhk_radio.types import Episode, Program

PROGRAM = Program(title="番組A", display_title="番組A", display_date="", site_id="S", corner_id="01", url="U")

# JST 2025-07-07 06:25 の放送。yt-dlp の upload_date は UTC の 20250706
EARLY = Episode(id="ep1", title="t", display_title="t", date="20250706", display_date="2025-07-07(月)",
                broadcast_time="06:25", duration_str="", url="")
# JST 2025-07-07 20:00 の放送。UTC でも同じ日
EVENING = Episode(id="ep2", title="t", display_title="t", date="20250707", display_date="2025-07-07(月)",
                  broadcast_time="20:00", duration_str="", url="")


def _render(template: str, info: dict) -> str:
    """yt-dlp にファイル名テンプレートを展開させ、ファイル名 (ディレクトリを除く) を返す。"""
    with yt_dlp.YoutubeDL({"outtmpl": f"/tmp/dir/{template}", "quiet": True}) as ydl:
        return Path(ydl.prepare_filename({"title": "t", "ext": "mp3", "id": "x", "playlist_index": 1, **info})).name


@pytest.mark.parametrize("max_items", [False, True])
def test_filename_uses_jst_date_for_early_broadcast(max_items: bool) -> None:
    """放送時刻があれば、ファイル名の日付は JST にする。"""
    template = downloads.program_filename_template(PROGRAM, max_items=max_items)
    name = _render(template, {"release_timestamp": 1751837100, "upload_date": "20250706"})

    assert "20250707_番組A_t.mp3" in name


def test_filename_falls_back_to_timestamp_then_upload_date() -> None:
    """release_timestamp が無ければ timestamp、どちらも無ければ upload_date を使う。"""
    template = downloads.program_filename_template(PROGRAM)

    assert _render(template, {"timestamp": 1751837100, "upload_date": "20250706"}) == "20250707_番組A_t.mp3"
    assert _render(template, {"upload_date": "20250706"}) == "20250706_番組A_t.mp3"


def test_episode_dates_include_utc_and_jst() -> None:
    """照合に使う日付は、yt-dlp の date (UTC) と表示日付 (JST) の 2 つ。同じなら 1 つ。"""
    assert filesystem._episode_dates(EARLY) == ["20250706", "20250707"]
    assert filesystem._episode_dates(EVENING) == ["20250707"]


@pytest.mark.parametrize("name", ["20250706_番組A_t.mp3", "20250707_番組A_t.mp3"])
def test_early_episode_matches_both_utc_and_jst_named_files(tmp_path: Path, name: str) -> None:
    """早朝の回は、UTC の日付で保存済みの既存ファイルも、JST の日付の新しいファイルも見つける。"""
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")

    assert filesystem._episode_output_matches(path, PROGRAM, EARLY)


@pytest.mark.parametrize("name", ["20250705_番組A_t.mp3", "20250708_番組A_t.mp3"])
def test_early_episode_does_not_match_adjacent_days(tmp_path: Path, name: str) -> None:
    """隣の日の回 (同じタイトルの毎日の番組など) とは取り違えない。"""
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")

    assert not filesystem._episode_output_matches(path, PROGRAM, EARLY)


def test_evening_episode_does_not_match_previous_day(tmp_path: Path) -> None:
    """UTC と JST が同じ日の回は、その日だけを受け付ける。"""
    path = tmp_path / "20250706_番組A_t.mp3"
    path.write_text("x", encoding="utf-8")

    assert not filesystem._episode_output_matches(path, PROGRAM, EVENING)


def test_output_patterns_cover_both_dates() -> None:
    """一時ファイルの片付けなどで使うパターンにも、両方の日付が入る。"""
    patterns = filesystem._episode_output_patterns(PROGRAM, EARLY)

    assert "20250706_番組A_t.*" in patterns
    assert "20250707_番組A_t.*" in patterns

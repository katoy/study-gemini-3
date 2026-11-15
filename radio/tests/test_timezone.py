"""レビュー L1（タイムゾーン）の回帰テスト。

実行環境のタイムゾーンに依存しないことを確かめるため、TZ を UTC にしたテストも含める。
"""

import os
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from nhk_radio import cache, core, text
from nhk_radio.types import Episode, Program

# yt-dlp のテストデータにある実例: JST 2025-07-07 06:25 の放送で upload_date が UTC の 20250706 になる
EARLY_MORNING_TS = 1751837100
EARLY_MORNING_UTC_DATE = "20250706"


@pytest.fixture
def utc_local_time() -> Iterator[None]:
    """実行環境のローカルタイムゾーンを一時的に UTC にする。"""
    original = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    yield
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


# ── text.py ────────────────────────────────────────


def test_format_broadcast_time_uses_jst(utc_local_time: None) -> None:
    """放送時刻は実行環境のタイムゾーンではなく JST で表示する。"""
    assert text._format_broadcast_time(EARLY_MORNING_TS) == "06:25"


def test_format_broadcast_time_invalid_values() -> None:
    """None・不正な値・範囲外の値は空文字にする。"""
    assert text._format_broadcast_time(None) == ""
    assert text._format_broadcast_time("bad") == ""
    assert text._format_broadcast_time(1e20) == ""


def test_jst_date_from_timestamp(utc_local_time: None) -> None:
    """timestamp を JST の YYYYMMDD にする。"""
    assert text._jst_date_from_timestamp(EARLY_MORNING_TS) == "20250707"


def test_jst_date_from_timestamp_invalid_values() -> None:
    """None・不正な値・範囲外の値は空文字にする。"""
    assert text._jst_date_from_timestamp(None) == ""
    assert text._jst_date_from_timestamp("bad") == ""
    assert text._jst_date_from_timestamp(1e20) == ""


def test_format_onair_date_converts_utc_started_at_to_jst() -> None:
    """started_at が UTC (Z) でも、JST の日付で表示する。"""
    # 2024-04-14T22:00Z は JST 2024-04-15(月) 07:00
    assert text._format_onair_date("", "2024-04-14T22:00:00Z") == "2024-04-15(月)"


def test_format_onair_date_keeps_jst_started_at() -> None:
    """started_at が +09:00 の場合は、そのままの日付で表示する（現在の API の形式）。"""
    assert text._format_onair_date("", "2024-04-15T07:00:00+09:00") == "2024-04-15(月)"


def test_format_onair_date_keeps_naive_started_at() -> None:
    """タイムゾーンの無い started_at は、変換せずにそのままの日付で表示する。"""
    assert text._format_onair_date("", "2024-04-15T07:00:00") == "2024-04-15(月)"


# ── core.py ────────────────────────────────────────


def test_parse_episode_info_display_date_uses_jst(utc_local_time: None) -> None:
    """表示用の日付は放送時刻の JST から作る。保存・照合に使う date は yt-dlp の値のまま。"""
    info = {
        "id": "ep1",
        "title": "マイあさ！",
        "upload_date": EARLY_MORNING_UTC_DATE,
        "release_timestamp": EARLY_MORNING_TS,
    }
    episode = core._parse_episode_info(info)

    assert episode.date == EARLY_MORNING_UTC_DATE
    assert episode.display_date == "2025-07-07(月)"
    assert episode.broadcast_time == "06:25"


def test_parse_episode_info_without_timestamp_uses_upload_date() -> None:
    """timestamp が無ければ、従来どおり upload_date で表示する。"""
    episode = core._parse_episode_info({"id": "ep1", "title": "t", "upload_date": "20250706"})

    assert episode.date == "20250706"
    assert episode.display_date == "2025-07-06(日)"


def test_parse_episode_info_timestamp_only_uses_jst_date(utc_local_time: None) -> None:
    """upload_date が無ければ、date も JST の日付にする（従来と同じ）。"""
    episode = core._parse_episode_info({"id": "ep1", "title": "t", "timestamp": EARLY_MORNING_TS})

    assert episode.date == "20250707"
    assert episode.display_date == "2025-07-07(月)"


def test_parse_episode_info_out_of_range_timestamp_falls_back() -> None:
    """日付に変換できない timestamp は、従来どおり文字列のまま date にする。"""
    episode = core._parse_episode_info({"id": "ep1", "title": "t", "timestamp": 1e20})

    assert episode.date == str(int(1e20))


# ── cache.py ───────────────────────────────────────


def test_save_episode_cache_keeps_display_date(tmp_path: Path) -> None:
    """キャッシュに保存して読み戻しても、JST の表示日付を UTC の date で上書きしない。"""
    program = Program(title="P", display_title="P", display_date="", site_id="S", corner_id="01", url="U")
    episode = Episode(
        id="ep1", title="t", display_title="t", date=EARLY_MORNING_UTC_DATE,
        display_date="2025-07-07(月)", broadcast_time="06:25", duration_str="", url="",
    )
    with patch.object(cache, "_episode_cache_dir", return_value=tmp_path):
        cache.save_episode_cache(program, [episode])
        loaded = cache.load_episode_cache(program)

    assert loaded is not None
    assert loaded[0].display_date == "2025-07-07(月)"


def test_save_episode_cache_fills_missing_display_date(tmp_path: Path) -> None:
    """表示日付が空のエピソードは、従来どおり date から作る。"""
    program = Program(title="P", display_title="P", display_date="", site_id="S", corner_id="01", url="U")
    episode = Episode(
        id="ep1", title="t", display_title="t", date="20250706",
        display_date="", broadcast_time="", duration_str="", url="",
    )
    with patch.object(cache, "_episode_cache_dir", return_value=tmp_path):
        cache.save_episode_cache(program, [episode])
        loaded = cache.load_episode_cache(program)

    assert loaded is not None
    assert loaded[0].display_date == "2025-07-06(日)"

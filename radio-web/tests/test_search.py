"""検索・フィルタリング機能テスト。"""

import pytest

from nhk_radio_web.search import filter_episodes, filter_programs, sort_episodes
from nhk_radio_web.types import Episode, Program


@pytest.fixture
def sample_programs():
    """テスト用番組リスト。"""
    return [
        Program(
            title="NHK World Easy Japanese",
            display_title="NHK World Easy Japanese",
            display_date="2026-05-16",
            site_id="site1",
            corner_id="c1",
            url="https://example.com/1",
            genre="language",
            genre_label="語学",
        ),
        Program(
            title="Let's Speak Japanese",
            display_title="Let's Speak Japanese",
            display_date="2026-05-16",
            site_id="site2",
            corner_id="c2",
            url="https://example.com/2",
            genre="language",
            genre_label="語学",
        ),
        Program(
            title="NHK News",
            display_title="NHK News",
            display_date="2026-05-16",
            site_id="site3",
            corner_id="c3",
            url="https://example.com/3",
            genre="news",
            genre_label="ニュース",
        ),
    ]


@pytest.fixture
def sample_episodes():
    """テスト用エピソードリスト。"""
    return [
        Episode(
            id="ep1",
            title="第1回",
            display_title="第1回",
            date="20260516",
            display_date="2026-05-16(金)",
            broadcast_time="10:00",
            duration_str="15分",
            url="https://example.com/ep1",
        ),
        Episode(
            id="ep2",
            title="第2回",
            display_title="第2回",
            date="20260517",
            display_date="2026-05-17(土)",
            broadcast_time="14:30",
            duration_str="30分",
            url="https://example.com/ep2",
        ),
    ]


def test_filter_programs_no_filter(sample_programs):
    """フィルタなしで全番組を返す。"""
    result = filter_programs(sample_programs)
    assert len(result) == 3


def test_filter_programs_by_keyword(sample_programs):
    """キーワード検索で番組をフィルタ。"""
    result = filter_programs(sample_programs, needle="Japanese")
    assert len(result) == 2
    assert all("Japanese" in p.title for p in result)


def test_filter_programs_by_genre(sample_programs):
    """ジャンルフィルタで番組をフィルタ。"""
    result = filter_programs(sample_programs, genre_filter="語学")
    assert len(result) == 2
    assert all(p.genre_label == "語学" for p in result)


def test_filter_programs_by_keyword_and_genre(sample_programs):
    """キーワード + ジャンルでフィルタ。"""
    result = filter_programs(sample_programs, needle="NHK", genre_filter="語学")
    assert len(result) == 1
    assert result[0].title == "NHK World Easy Japanese"


def test_filter_programs_keyword_case_sensitive(sample_programs):
    """キーワード検索は大文字小文字を区別する。"""
    result = filter_programs(sample_programs, needle="Japanese")
    assert len(result) == 2

    # 小文字では マッチしない
    result_lower = filter_programs(sample_programs, needle="japanese")
    assert len(result_lower) == 0


def test_filter_episodes_no_filter(sample_episodes):
    """フィルタなしで全エピソードを返す。"""
    result = filter_episodes(sample_episodes)
    assert len(result) == 2


def test_filter_episodes_by_keyword(sample_episodes):
    """キーワードでエピソードをフィルタ。"""
    result = filter_episodes(sample_episodes, needle="第1回")
    assert len(result) == 1
    assert result[0].title == "第1回"


def test_filter_episodes_by_date(sample_episodes):
    """日付を含むキーワード検索。"""
    result = filter_episodes(sample_episodes, needle="2026-05-17")
    assert len(result) == 1
    assert result[0].date == "20260517"


def test_sort_episodes_no_column(sample_episodes):
    """ソート列なしで元の順序を保持。"""
    result = sort_episodes(sample_episodes)
    assert result[0].id == "ep1"
    assert result[1].id == "ep2"


def test_sort_episodes_by_title(sample_episodes):
    """タイトルでソート。"""
    result = sort_episodes(sample_episodes, column="title")
    assert result[0].title == "第1回"
    assert result[1].title == "第2回"


def test_sort_episodes_by_title_reverse(sample_episodes):
    """タイトルで降順ソート。"""
    result = sort_episodes(sample_episodes, column="title", reverse=True)
    assert result[0].title == "第2回"
    assert result[1].title == "第1回"


def test_sort_episodes_by_date(sample_episodes):
    """日付でソート。"""
    result = sort_episodes(sample_episodes, column="date")
    assert result[0].date == "20260516"
    assert result[1].date == "20260517"


def test_sort_episodes_by_duration(sample_episodes):
    """尺でソート。"""
    result = sort_episodes(sample_episodes, column="duration")
    assert result[0].duration_str == "15分"
    assert result[1].duration_str == "30分"


def test_sort_episodes_by_saved(sample_episodes):
    """保存状況でソート（is_downloaded_func 使用）。"""
    def is_downloaded(ep):
        return ep.id == "ep1"

    result = sort_episodes(sample_episodes, column="saved", is_downloaded_func=is_downloaded)
    # デフォルト (reverse=False) では未保存 (ep2) が先に来る (False < True)
    assert result[0].id == "ep2"
    assert result[1].id == "ep1"

    # reverse=True では保存済み (ep1) が先に来る
    result_rev = sort_episodes(sample_episodes, column="saved", reverse=True, is_downloaded_func=is_downloaded)
    assert result_rev[0].id == "ep1"
    assert result_rev[1].id == "ep2"

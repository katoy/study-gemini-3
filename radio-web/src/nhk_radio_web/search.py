"""プログラム・エピソード検索フィルタリング。"""

from collections.abc import Iterable

from nhk_radio_web.text import (
    _genre_label,
    _normalize_text,
    _sortable_day_value,
    _sortable_duration_value,
    _sortable_timestamp_value,
)
from nhk_radio_web.types import Episode, Program


def filter_programs(
    programs: Iterable[Program],
    needle: str | None = None,
    genre_filter: str | None = None,
) -> list[Program]:
    """番組をキーワード・ジャンルでフィルタリングする。

    Args:
        programs: フィルタ対象の番組リスト
        needle: フリーワード検索テキスト
        genre_filter: ジャンルラベル (例: "語学")

    Returns:
        フィルタ済み番組リスト
    """
    filtered = list(programs)

    # ジャンルフィルタ
    if genre_filter and genre_filter != "すべて":
        filtered = [
            p for p in filtered
            if (p.genre_label or _genre_label(p.genre)) == genre_filter
        ]

    # キーワード検索
    if needle:
        needle_norm = _normalize_text(needle)
        filtered = [
            p for p in filtered
            if needle_norm in _normalize_text(f"{p.title} {p.display_title} {p.corner_name or ''}")
        ]

    return filtered


def filter_episodes(
    episodes: Iterable[Episode],
    needle: str | None = None,
) -> list[Episode]:
    """エピソードをキーワード検索でフィルタリングする。

    Args:
        episodes: フィルタ対象のエピソードリスト
        needle: フリーワード検索テキスト

    Returns:
        フィルタ済みエピソードリスト
    """
    if not needle:
        return list(episodes)

    needle_norm = _normalize_text(needle)
    return [
        e for e in episodes
        if needle_norm in _normalize_text(f"{e.display_title} {e.title} {e.display_date} {e.broadcast_time}")
    ]


def sort_episodes(
    episodes: Iterable[Episode],
    column: str | None = None,
    reverse: bool = False,
    is_downloaded_func=None,
) -> list[Episode]:
    """エピソード一覧をソートする。

    Args:
        episodes: ソート対象のエピソードリスト
        column: ソート列 (None/"title"/"date"/"duration")
        reverse: 降順フラグ
        is_downloaded_func: (Episode) -> bool の関数 (saved 列ソート用)

    Returns:
        ソート済みエピソードリスト
    """
    if column is None:
        return list(episodes)

    original_episodes = list(episodes)
    episode_to_idx = {id(e): i for i, e in enumerate(original_episodes)}

    def sort_key(e: Episode):
        original_index = episode_to_idx.get(id(e), 10**9)
        title = _normalize_text(e.display_title or e.title)

        if column == "saved" and is_downloaded_func:
            saved = is_downloaded_func(e)
            return (saved, title, original_index)  # False (未保存) を先に (reverse=False の場合)
        if column == "date":
            timestamp = _sortable_timestamp_value(e.date)
            day = _sortable_day_value(str(e.date or e.display_date or ""))
            time_text = _normalize_text(e.broadcast_time)
            return (timestamp, day, time_text, title, original_index)
        if column == "duration":
            duration = _sortable_duration_value(str(e.duration_str or ""))
            return (duration, title, original_index)
        return (title, original_index)

    return sorted(episodes, key=sort_key, reverse=reverse)

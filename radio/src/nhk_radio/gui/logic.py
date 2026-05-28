"""Pure logic for filtering and sorting programs and episodes, decoupled from UI."""

from collections.abc import Iterable

from ..text import (
    _normalize_text,
    _program_genre_labels,
    _sortable_day_value,
    _sortable_duration_value,
    _sortable_timestamp_value,
)
from ..types import Episode, Program


def filter_programs(
    programs: Iterable[Program],
    needle: str,
    genre_filter: str | None = None,
) -> list[Program]:
    """Filter programs by search text and genre."""
    filtered = list(programs)
    if genre_filter and genre_filter != "すべて":
        filtered = [
            p for p in filtered
            if genre_filter in _program_genre_labels(p)
        ]

    if needle:
        needle_norm = _normalize_text(needle)
        filtered = [
            p for p in filtered
            if needle_norm in _normalize_text(
                f"{p.title} {p.display_title} {p.corner_name or ''} {' '.join(_program_genre_labels(p))}"
            )
        ]
    return filtered


def sort_programs(
    programs: Iterable[Program],
    column: str | None,
    reverse: bool,
    order_map: dict[tuple[str, str], int],
) -> list[Program]:
    """Sort programs by given column and order."""
    if column is None:
        return list(programs)

    def sort_key(p: Program):
        key = (p.site_id, p.corner_id)
        original_index = order_map.get(key, 10**9)
        title = _normalize_text(p.display_title or p.title)

        if column == "order":
            return (original_index, title)
        if column == "date":
            # 曜日を除去して比較
            date_val = _sortable_day_value(p.display_date or "")
            return (date_val, title, original_index)
        if column == "title":
            return (title, original_index)
        return (title, original_index)

    return sorted(programs, key=sort_key, reverse=reverse)


def filter_episodes(
    episodes: Iterable[Episode],
    needle: str,
) -> list[Episode]:
    """Filter episodes by search text."""
    if not needle:
        return list(episodes)

    needle_norm = _normalize_text(needle)
    return [
        e for e in episodes
        if needle_norm in _normalize_text(f"{e.display_title} {e.title} {e.display_date} {e.broadcast_time}")
    ]


def sort_episodes(
    episodes: Iterable[Episode],
    column: str | None,
    reverse: bool,
    is_downloaded_func,  # (Episode) -> bool
) -> list[Episode]:
    """Sort episodes by given column and order."""
    if column is None:
        return list(episodes)

    # 安定ソートのため元の順序を保持
    original_episodes = list(episodes)
    episode_to_idx = {id(e): i for i, e in enumerate(original_episodes)}

    def sort_key(e: Episode):
        original_index = episode_to_idx.get(id(e), 10**9)
        title = _normalize_text(e.display_title or e.title)

        if column == "saved":
            saved = is_downloaded_func(e)
            return (saved, title, original_index)
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

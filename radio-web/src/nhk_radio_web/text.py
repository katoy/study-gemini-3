"""Text and display formatting helpers."""

import re
import unicodedata
from datetime import datetime

from .constants import GENRE_LABELS, JP_WEEKDAYS


def _normalize_text(text: str) -> str:
    return (text or "").replace("\u3000", " ").strip()


def _fixed_display_date(day: datetime) -> str:
    return day.strftime("%Y-%m-%d") + f"({JP_WEEKDAYS[day.weekday()]})"


def _format_onair_date(onair_date: str, started_at: str | None = None) -> str:
    # 1) started_at (ISO形式等) を優先して試行
    if started_at:
        try:
            # 2024-04-15T10:00:00+09:00 のような形式を想定
            # Python 3.11+ なら fromisoformat が強力
            day = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            return _fixed_display_date(day)
        except (ValueError, TypeError):
            pass

    normalized = _normalize_text(onair_date).replace("放送", "")
    if not normalized:
        return "----------(-)"

    patterns = (
        "%Y年%m月%d日",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d",
    )
    normalized_no_weekday = re.sub(r"\([月火水木金土日]\)", "", normalized)

    for pattern in patterns:
        try:
            day = datetime.strptime(normalized_no_weekday, pattern)
            return _fixed_display_date(day)
        except ValueError:
            continue

    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", normalized)
    if match:
        try:
            day = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return _fixed_display_date(day)
        except ValueError:
            pass

    return normalized or "----------(-)"


def _format_episode_date(date_text: str) -> str:
    if len(date_text) >= 8 and date_text[:8].isdigit():
        try:
            day = datetime.strptime(date_text[:8], "%Y%m%d")
            return _fixed_display_date(day)
        except ValueError:
            pass
    return _format_onair_date(date_text)


def _format_broadcast_time(timestamp) -> str:
    """Unix timestamp を HH:MM:SS 形式 (ローカル時刻) に変換する"""
    if timestamp is None:
        return ""
    try:
        dt = datetime.fromtimestamp(float(timestamp))
        return dt.strftime("%H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return ""


def _format_duration(seconds) -> str:
    """秒数を HH:MM:SS 形式に変換する。時間がない場合は --:MM:SS、分もない場合は --:--:SS"""
    if seconds is None:
        return ""
    try:
        total = int(float(seconds))
        if total <= 0:
            return ""
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        if m:
            return f"--:{m:02d}:{s:02d}"
        return f"--:--:{s:02d}"
    except (ValueError, TypeError):
        return ""


def _sortable_day_value(date_text: str) -> tuple[int, int]:
    normalized = _normalize_text(date_text).replace("放送", "")
    if not normalized:
        return (0, 0)

    if len(normalized) >= 8 and normalized[:8].isdigit():
        try:
            return (1, datetime.strptime(normalized[:8], "%Y%m%d").toordinal())
        except ValueError:
            pass

    normalized_no_weekday = re.sub(r"\([月火水木金土日]\)", "", normalized)
    for pattern in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return (1, datetime.strptime(normalized_no_weekday, pattern).toordinal())
        except ValueError:
            continue

    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", normalized)
    if match:
        try:
            return (1, datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).toordinal())
        except ValueError:
            pass

    return (0, 0)


def _sortable_timestamp_value(value) -> tuple[int, float]:
    if value is None:
        return (0, 0.0)

    text = _normalize_text(str(value))
    if not text:
        return (0, 0.0)

    try:
        return (1, datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        pass

    if text.isdigit() and len(text) >= 9:
        try:
            return (1, float(text))
        except ValueError:
            pass

    return (0, 0.0)


def _sortable_duration_value(duration_text: str) -> tuple[int, int]:
    normalized = _normalize_text(duration_text)
    if not normalized:
        return (0, 0)

    match = re.fullmatch(r"(?:(\d+)時間)?(?:(\d+)分)?(?:(\d+)秒)?", normalized)
    if not match:
        return (0, 0)

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return (1, total) if total > 0 else (0, 0)


def _program_display_title(series_title: str, corner_name: str) -> str:
    title = _normalize_text(series_title)
    corner = _normalize_text(corner_name)
    if title and corner and corner != title:
        return f"[{title}] {corner}"
    return title or corner or "(無題)"


def _safe_name(text: str, fallback: str = "unknown") -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "_", _normalize_text(text))
    # Windows は末尾のドット/空白を持つ名前を扱えないため除去する
    safe = safe.rstrip(" .")
    return safe or fallback


def _genre_label(genre: str | None) -> str:
    return GENRE_LABELS.get(genre or "", "未分類")


def _char_width(ch: str) -> int:
    if unicodedata.east_asian_width(ch) in "WF":
        return 2
    return 1


def _display_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)

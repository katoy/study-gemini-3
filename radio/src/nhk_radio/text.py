"""Text and display formatting helpers."""

import re
import unicodedata
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from .constants import GENRE_LABELS, JP_WEEKDAYS
from .types import Program

# ファイル名 1 要素の上限 (多くのファイルシステムで 255 バイト)
SAFE_NAME_MAX_BYTES = 255

# Windows でファイル名に使えない予約名 (拡張子が付いていても使えない)
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

# 日本標準時。日本には夏時間が無いため固定オフセットで足り、tzdata の無い Windows でも動く (L1)
JST = timezone(timedelta(hours=9), "JST")


def _normalize_text(text: str) -> str:
    return (text or "").replace("\u3000", " ").strip()


def _fixed_display_date(day: datetime) -> str:
    return day.strftime("%Y-%m-%d") + f"({JP_WEEKDAYS[day.weekday()]})"


def _format_onair_date(onair_date: str, started_at: str | None = None) -> str:
    if started_at:
        try:
            day = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            # UTC などで来ても JST の日付で表示する (L1)
            if day.tzinfo is not None:
                day = day.astimezone(JST)
            return _fixed_display_date(day)
        except (ValueError, TypeError):
            pass

    parsed_day = _parse_date_str(onair_date)
    if parsed_day:
        return _fixed_display_date(parsed_day)

    normalized = _normalize_text(onair_date).replace("放送", "")
    return normalized or "----------(-)"


def _format_episode_date(date_text: str) -> str:
    # 8桁の YYYYMMDD のみ日付としてパース（10桁の timestamp などが誤解釈されるのを防ぐ）
    if len(date_text) == 8 and date_text.isdigit():
        try:
            day = datetime.strptime(date_text, "%Y%m%d")
            return _fixed_display_date(day)
        except ValueError:
            pass
    elif len(date_text) > 8 and date_text[:8].isdigit() and not date_text[8:].isdigit():
        try:
            day = datetime.strptime(date_text[:8], "%Y%m%d")
            return _fixed_display_date(day)
        except ValueError:
            pass
    return _format_onair_date(date_text)


def _parse_date_str(date_text: str) -> datetime | None:
    """日付文字列を datetime に変換する。失敗時は None を返す。"""
    normalized = _normalize_text(date_text).replace("放送", "")
    if not normalized:
        return None

    if len(normalized) >= 8 and normalized[:8].isdigit():
        with suppress(ValueError):
            return datetime.strptime(normalized[:8], "%Y%m%d")

    normalized_no_weekday = re.sub(r"\([月火水木金土日]\)", "", normalized)
    for pattern in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        with suppress(ValueError):
            return datetime.strptime(normalized_no_weekday, pattern)

    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", normalized)
    if match:
        with suppress(ValueError):
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    return None


def _format_broadcast_time(timestamp) -> str:
    """Unix timestamp を HH:MM 形式 (JST) に変換する"""
    if timestamp is None:
        return ""
    try:
        # 実行環境のタイムゾーンに依らず、放送地の JST で表示する (L1)
        dt = datetime.fromtimestamp(float(timestamp), JST)
        return dt.strftime("%H:%M")
    except (ValueError, OSError, OverflowError):
        return ""


def _jst_date_from_timestamp(timestamp) -> str:
    """Unix timestamp を JST の YYYYMMDD 形式に変換する。

    Args:
        timestamp: Unix timestamp (秒)。None や変換できない値も受け付ける。

    Returns:
        JST の日付 (YYYYMMDD)。変換できなければ空文字。
    """
    if timestamp is None:
        return ""
    try:
        return datetime.fromtimestamp(float(timestamp), JST).strftime("%Y%m%d")
    except (ValueError, OSError, OverflowError):
        return ""


def _format_duration(seconds) -> str:
    """秒数を「15分3秒」「1時間5分3秒」形式に変換する"""
    if seconds is None:
        return ""
    try:
        total = int(float(seconds))
        if total <= 0:
            return ""
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        if h:
            return f"{h}時間{m}分{s}秒"
        if m:
            return f"{m}分{s}秒"
        return f"{s}秒"
    except (ValueError, TypeError):
        return ""


def _sortable_day_value(date_text: str) -> tuple[int, int]:
    day = _parse_date_str(date_text)
    if day:
        return (1, day.toordinal())
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
    """テキストを、ファイル名やディレクトリ名の 1 要素として使える形にする。

    Args:
        text: 元のテキスト。
        fallback: 結果が空になったときに返す名前。

    Returns:
        パス区切り・禁止文字・制御文字を `_` に置き換え、Windows の予約名を避け、
        UTF-8 で SAFE_NAME_MAX_BYTES バイト以内に詰めた名前。
    """
    # 制御文字 (改行・タブ・NUL など) も置き換える (L5)
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "_", _normalize_text(text))
    # Windows は末尾のドット/空白を持つ名前を扱えないため除去する
    safe = safe.rstrip(" .")
    # Windows の予約名 (CON, NUL.txt など) は末尾に `_` を付けて避ける (L5)
    stem, dot, rest = safe.partition(".")
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        safe = f"{stem}_{dot}{rest}"
    # UTF-8 で上限バイト数を超えたら、文字の途中で切らないように詰める (L5)
    encoded = safe.encode("utf-8")
    if len(encoded) > SAFE_NAME_MAX_BYTES:
        safe = encoded[:SAFE_NAME_MAX_BYTES].decode("utf-8", errors="ignore").rstrip(" .")
    return safe or fallback


def _genre_label(genre: str | None) -> str:
    return GENRE_LABELS.get(genre or "", "未分類")


def _program_genres(program: Program) -> tuple[str, ...]:
    return tuple(str(genre).strip() for genre in program.genres if str(genre).strip())


def _program_genre_labels(program: Program) -> tuple[str, ...]:
    labels = tuple(str(label).strip() for label in program.genre_labels if str(label).strip())
    if labels:
        return labels

    genres = _program_genres(program)
    if genres:
        return tuple(_genre_label(genre) for genre in genres)

    return (_genre_label(None),)


def _program_genre_text(program: Program) -> str:
    return " / ".join(_program_genre_labels(program))


def _char_width(ch: str) -> int:
    if unicodedata.east_asian_width(ch) in "WF":
        return 2
    return 1


def _display_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)

#!/usr/bin/env python3
"""
NHK ラジオ 聞き逃し番組ダウンローダー
個人学習目的専用 (著作権法第30条 私的使用のための複製)

使い方:
  python nhk_radio_dl.py          # 番組一覧から選択 (GUI 専用モード)
  python nhk_radio_dl.py <URL>    # URL を直接指定してダウンロード
  python nhk_radio_dl.py <URL> -n 5   # 直近5件のみダウンロード
"""

import argparse
import curses
import json
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
import webbrowser
from collections.abc import Callable
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
except ImportError:
    tk = None
    tkfont = None
    ttk = None

from pathlib import Path

from .config import (
    CACHE_ROOT_DIR,
    CACHE_TTL_SECONDS,
    DEFAULT_UI_FONT_SIZE_PT,
    DEFAULT_UI_THEME,
    EPISODE_CACHE_DIR,
    PROGRAM_CACHE_DIR,
    SEARCH_HISTORY_LIMIT,
    UI_SETTINGS_PATH,
    _load_ui_settings,
    _normalize_search_history,
    _save_ui_settings,
)
from .constants import (
    GENRE_LABELS,
    JP_WEEKDAYS,
    NHK_API_GENRE,
    NHK_API_NEW_CORNERS,
    NHK_API_SERIES,
    NHK_DETAIL_TMPL,
    NHK_EPISODE_TMPL,
    NHK_GENRES,
    NHK_ONDEMAND_URL,
    _HEADERS,
)


# ──────────────────────────────────────────────────────
# HTTP ユーティリティ
# ──────────────────────────────────────────────────────

def http_get_json(url: str, timeout: int = 15) -> dict | list:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


# ──────────────────────────────────────────────────────
# 番組一覧の取得
# ──────────────────────────────────────────────────────

def fetch_program_list(genre: str | None = None) -> list[dict]:
    """
    NHK ラジオ聞き逃し番組一覧を API から取得する。

    genre=None  → 全番組 (corners/new_arrivals + 全ジャンル合算)
    genre=str   → 指定ジャンルのみ (例: "language", "music")

    Returns:
        [{"title": str, "site_id": str, "corner_id": str, "url": str}, ...]
    """
    cached = _load_program_cache(genre)
    if cached is not None:
        return cached

    programs = _fetch_by_genre(genre) if genre else _fetch_all()
    if programs:
        _save_program_cache(genre, programs)
        return programs

    stale = _load_program_cache(genre, ttl_seconds=10**12)
    return stale or programs




# ──────────────────────────────────────────────────────
# テキスト・表示フォーマット
# ──────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    return (text or "").replace("\u3000", " ").strip()


def _fixed_display_date(day: datetime) -> str:
    return day.strftime("%Y-%m-%d") + f"({JP_WEEKDAYS[day.weekday()]})"


def _format_onair_date(onair_date: str) -> str:
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
    """Unix timestamp を HH:MM 形式 (ローカル時刻) に変換する"""
    if timestamp is None:
        return ""
    try:
        dt = datetime.fromtimestamp(float(timestamp))
        return dt.strftime("%H:%M")
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
    if corner and corner != title:
        return f"[{title}] {corner}"
    return title or corner or "(無題)"


def _safe_name(text: str, fallback: str = "unknown") -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "_", _normalize_text(text))
    return safe or fallback


def _genre_label(genre: str | None) -> str:
    return GENRE_LABELS.get(genre or "", "未分類")


def _char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def _display_width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


def _fit_text(text: str, width: int) -> str:
    if width <= 0:
        return ""

    normalized = _normalize_text(text)
    current = []
    used = 0
    for ch in normalized:
        w = _char_width(ch)
        if used + w > width:
            if width >= 3:
                while current and used + 3 > width:
                    used -= _char_width(current.pop())
                current.extend("...")
                used += 3
            break
        current.append(ch)
        used += w

    result = "".join(current)
    return result + (" " * max(width - _display_width(result), 0))


def _safe_addnstr(win, y: int, x: int, text: str, max_width: int, attr: int = 0):
    height, width = win.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= width:
        return

    available = width - x
    if y == height - 1:
        available -= 1
    available = min(max_width, available)
    if available <= 0:
        return

    try:
        win.addnstr(y, x, text, available, attr)
    except curses.error:
        pass




# ──────────────────────────────────────────────────────
# キャッシュ管理
# ──────────────────────────────────────────────────────

def _program_cache_path(genre: str | None) -> Path:
    return PROGRAM_CACHE_DIR / f"{genre or 'all'}.json"


def _normalize_cached_program(program: dict) -> dict:
    normalized = dict(program)
    normalized["display_date"] = _format_onair_date(str(program.get("onair_date", "")))
    return normalized


def _load_json_ttl_cache(cache_path: Path, data_key: str, ttl_seconds: int) -> list[dict] | None:
    """JSON キャッシュを読み込む共通ヘルパー。TTL 切れ・破損時は None を返す。"""
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    fetched_at = payload.get("fetched_at")
    items = payload.get(data_key)
    if not isinstance(fetched_at, (int, float)) or not isinstance(items, list):
        return None
    if time.time() - float(fetched_at) > ttl_seconds:
        return None
    return [item for item in items if isinstance(item, dict)]


def _load_normalized_json_ttl_cache(
    cache_path: Path,
    data_key: str,
    ttl_seconds: int,
    normalizer: Callable[[dict], dict],
) -> list[dict] | None:
    items = _load_json_ttl_cache(cache_path, data_key, ttl_seconds)
    if items is None:
        return None
    return [normalizer(item) for item in items]


def _save_json_cache(cache_path: Path, payload: dict):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _load_program_cache(genre: str | None, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[dict] | None:
    return _load_normalized_json_ttl_cache(
        _program_cache_path(genre),
        "programs",
        ttl_seconds,
        _normalize_cached_program,
    )


def _save_program_cache(genre: str | None, programs: list[dict]):
    _save_json_cache(
        _program_cache_path(genre),
        {"fetched_at": time.time(), "genre": genre, "programs": programs},
    )


def _clear_cache_dir(cache_dir: Path) -> int:
    if not cache_dir.exists():
        return 0
    removed = 0
    for path in cache_dir.glob("*.json"):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def clear_program_cache() -> int:
    return _clear_cache_dir(PROGRAM_CACHE_DIR)


def _episode_cache_path(program: dict) -> Path:
    return EPISODE_CACHE_DIR / f"{program['site_id']}_{program['corner_id']}.json"


def _normalize_cached_episode(episode: dict) -> dict:
    normalized = dict(episode)
    normalized["display_date"] = _format_episode_date(str(episode.get("date", "")))
    return normalized


def _load_episode_cache(program: dict, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[dict] | None:
    return _load_normalized_json_ttl_cache(
        _episode_cache_path(program),
        "episodes",
        ttl_seconds,
        _normalize_cached_episode,
    )


def _save_episode_cache(program: dict, episodes: list[dict]):
    _save_json_cache(
        _episode_cache_path(program),
        {
            "fetched_at": time.time(),
            "site_id": program["site_id"],
            "corner_id": program["corner_id"],
            "episodes": episodes,
        },
    )


def clear_episode_cache() -> int:
    return _clear_cache_dir(EPISODE_CACHE_DIR)


def clear_all_cache() -> int:
    return clear_program_cache() + clear_episode_cache()




# ──────────────────────────────────────────────────────
# ファイル・ダウンロード管理
# ──────────────────────────────────────────────────────

def _program_output_dir(output_dir: Path, program: dict) -> Path:
    genre_dir = _safe_name(program.get("genre_label") or _genre_label(program.get("genre")))
    title_dir = _safe_name(_program_storage_title(program))
    return output_dir / genre_dir / title_dir


def _program_storage_title(program: dict) -> str:
    return str(program.get("title") or program.get("display_title") or "unknown")


def _episode_storage_title(episode: dict) -> str:
    return str(episode.get("title") or episode.get("display_title") or "unknown")


def _episode_output_identity(program: dict, episode: dict) -> tuple[str, str, str]:
    program_title = _safe_name(_program_storage_title(program))
    episode_title = _safe_name(_episode_storage_title(episode))
    episode_date = str(episode.get("date") or "").strip()
    return program_title, episode_title, episode_date


def _program_filename_template(program: dict, max_items: bool = False) -> str:
    title = _safe_name(_program_storage_title(program))
    if max_items:
        return f"%(playlist_index)s_%(upload_date)s_{title}_%(title)s.%(ext)s"
    return f"%(upload_date)s_{title}_%(title)s.%(ext)s"


def _episode_key(episode: dict) -> str:
    episode_id = str(episode.get("id") or "").strip()
    if episode_id:
        return episode_id
    return f"{episode.get('date', '')}:{episode.get('title', '')}"


def _download_manifest_path(program: dict, output_dir: Path) -> Path:
    return _program_output_dir(output_dir, program) / ".downloaded.json"


def _load_download_manifest(program: dict, output_dir: Path) -> tuple[set[str], dict[str, str]]:
    manifest_path = _download_manifest_path(program, output_dir)
    if not manifest_path.exists():
        return set(), {}

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), {}

    downloaded = payload.get("downloaded")
    if not isinstance(downloaded, list):
        downloaded_items = set()
    else:
        downloaded_items = {str(item) for item in downloaded}

    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return downloaded_items, {}
    return downloaded_items, {str(key): str(value) for key, value in paths.items()}


def _save_download_manifest(program: dict, output_dir: Path, downloaded: set[str], paths: dict[str, str]):
    manifest_path = _download_manifest_path(program, output_dir)
    payload = {"downloaded": sorted(downloaded), "paths": paths}
    _save_json_cache(manifest_path, payload)


def _episode_output_patterns(program: dict, episode: dict) -> list[str]:
    program_title, episode_title, episode_date = _episode_output_identity(program, episode)
    patterns: list[str] = []
    if episode_date:
        patterns.append(f"{episode_date}_{program_title}_{episode_title}.*")
        patterns.append(f"*_{episode_date}_{program_title}_{episode_title}.*")
    else:
        patterns.append(f"{program_title}_{episode_title}.*")
        patterns.append(f"*_{program_title}_{episode_title}.*")
    return patterns


def _episode_output_matches(path: Path, program: dict, episode: dict) -> bool:
    if not path.is_file() or path.name == ".downloaded.json" or path.suffix in {".part", ".ytdl"}:
        return False

    program_title, episode_title, episode_date = _episode_output_identity(program, episode)
    stem = path.stem

    if episode_date:
        expected = f"{episode_date}_{program_title}_{episode_title}"
        return stem == expected or stem.endswith(f"_{expected}")

    expected = f"{program_title}_{episode_title}"
    return stem == expected or stem.endswith(f"_{expected}")


def _episode_output_candidates(program_dir: Path, program: dict, episode: dict) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    program_title, episode_title, episode_date = _episode_output_identity(program, episode)
    for pattern in _episode_output_patterns(program, episode):
        for path in program_dir.glob(pattern):
            if not _episode_output_matches(path, program, episode):
                continue
            if path in seen:
                continue
            seen.add(path)
            candidates.append(path)
    suffix_priority = {
        ".mp3": 0,
        ".m4a": 1,
        ".aac": 2,
        ".wav": 3,
        ".mp4": 4,
    }
    candidates.sort(
        key=lambda path: (
            0 if episode_date and path.name.startswith(f"{episode_date}_{program_title}_") else 1,
            0 if episode_title and f"_{episode_title}." in path.name else 1,
            suffix_priority.get(path.suffix.lower(), 99),
            -path.stat().st_mtime,
        )
    )
    return candidates


def mark_episode_downloaded(output_dir: Path, program: dict, episode: dict, path: Path | None = None):
    downloaded, saved_paths = _load_download_manifest(program, output_dir)
    episode_key = _episode_key(episode)
    downloaded.add(episode_key)
    if path is not None and path.exists():
        program_dir = _program_output_dir(output_dir, program)
        try:
            saved_paths[episode_key] = str(path.relative_to(program_dir))
        except ValueError:
            saved_paths[episode_key] = str(path)
    _save_download_manifest(program, output_dir, downloaded, saved_paths)


def is_episode_downloaded(output_dir: Path, program: dict, episode: dict) -> bool:
    downloaded, _ = _load_download_manifest(program, output_dir)
    if _episode_key(episode) in downloaded:
        return True
    program_dir = _program_output_dir(output_dir, program)
    if not program_dir.exists():
        return False
    return bool(_episode_output_candidates(program_dir, program, episode))


def resolve_episode_downloaded_path(output_dir: Path, program: dict, episode: dict) -> Path | None:
    program_dir = _program_output_dir(output_dir, program)
    if not program_dir.exists():
        return None

    downloaded, saved_paths = _load_download_manifest(program, output_dir)
    episode_key = _episode_key(episode)
    candidates = _episode_output_candidates(program_dir, program, episode)
    if candidates:
        if saved_paths.get(episode_key) != str(candidates[0].relative_to(program_dir)):
            mark_episode_downloaded(output_dir, program, episode, candidates[0])
        return candidates[0]

    saved_path = saved_paths.get(episode_key)
    if saved_path:
        resolved = Path(saved_path)
        if not resolved.is_absolute():
            resolved = program_dir / resolved
        if resolved.exists():
            return resolved

    if episode_key in downloaded:
        return None
    return None


def cleanup_partial_episode_files(output_dir: Path, program: dict, episode: dict):
    program_dir = _program_output_dir(output_dir, program)
    if not program_dir.exists():
        return
    for pattern in _episode_output_patterns(program, episode):
        for path in program_dir.glob(pattern):
            if path.is_file() and path.suffix in {".part", ".ytdl"}:
                path.unlink()


def _format_download_percent(percent: float | None) -> str:
    if percent is None:
        return "--%"
    percent = min(max(percent, 0.0), 100.0)
    rounded = round(percent)
    if abs(percent - rounded) < 0.05:
        return f"{int(rounded)}%"
    return f"{percent:.1f}%"


def _format_download_eta(eta: str | None) -> str:
    return f"残り {eta}" if eta else "残り --:--"


def _parse_yt_dlp_progress(line: str) -> tuple[float | None, str | None, str | None]:
    text = line.strip()
    if not text:
        return None, None, None

    if "[ExtractAudio]" in text or "Post-process" in text:
        return 100.0, None, "変換中..."

    percent_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", text)
    if percent_match:
        percent = float(percent_match.group(1))
        eta_match = re.search(r"\bETA\s+([0-9:]+)", text)
        eta = eta_match.group(1) if eta_match else None
        status = "変換中..." if percent >= 100 else "ダウンロード中..."
        return percent, eta, status

    return None, None, None


def _download_episode_command(url: str, output_dir: Path, filename_template: str, audio_only: bool = True) -> list[str]:
    return _yt_dlp_command(
        url,
        str(output_dir / filename_template),
        audio_only=audio_only,
        no_playlist=True,
        newline=True,
    )


def _yt_dlp_command(
    url: str,
    output_template: str,
    *,
    audio_only: bool,
    no_playlist: bool,
    newline: bool = False,
    max_items: int | None = None,
) -> list[str]:
    cmd = ["yt-dlp"]
    if newline:
        cmd.append("--newline")
    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    cmd += ["-o", output_template]
    if max_items:
        cmd += ["--playlist-end", str(max_items)]
    elif no_playlist:
        cmd.append("--no-playlist")
    cmd.append(url)
    return cmd




# ──────────────────────────────────────────────────────
# API 番組取得ロジック
# ──────────────────────────────────────────────────────

def _resolve_program_from_url(url: str, genre: str | None = None) -> dict | None:
    program = _url_to_program(url)
    if program is None:
        return None

    for candidate in fetch_program_list(genre):
        if (
            candidate["site_id"] == program["site_id"]
            and candidate["corner_id"] == program["corner_id"]
        ):
            return candidate
    return program


def _make_entry(s: dict, genre: str | None = None) -> dict:
    site_id   = s.get("series_site_id") or s.get("site_id", "")
    corner_id = s.get("corner_site_id") or s.get("corner_id", "01")
    title     = s.get("title") or s.get("corner_name") or f"{site_id}_{corner_id}"
    corner_name = s.get("corner_name", "")
    onair_date = s.get("onair_date", "")
    return {
        "title":     title,
        "corner_name": corner_name,
        "genre": genre,
        "genre_label": _genre_label(genre),
        "site_id":   site_id,
        "corner_id": corner_id,
        "onair_date": onair_date,
        "display_date": _format_onair_date(onair_date),
        "display_title": _program_display_title(title, corner_name),
        "started_at": s.get("started_at", ""),
        "url":       NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
    }


def _fetch_all() -> list[dict]:
    """全ジャンルの番組を取得してまとめる"""
    print("番組一覧を取得中...", end="", flush=True)
    seen: set[str] = set()
    programs: list[dict] = []
    program_map: dict[tuple[str, str], dict] = {}

    # 1) corners/new_arrivals (最新追加・最多)
    try:
        data = http_get_json(NHK_API_NEW_CORNERS)
        for s in data.get("corners", []):
            key = (s.get("series_site_id"), s.get("corner_site_id"))
            if key not in seen:
                seen.add(key)
                entry = _make_entry(s)
                programs.append(entry)
                program_map[key] = entry
    except Exception:
        pass

    # 2) 各ジャンルを追加 (new_arrivals に含まれない番組を補完)
    for g in NHK_GENRES:
        try:
            data = http_get_json(NHK_API_GENRE.format(genre=g))
            for s in data.get("series", []):
                key = (s.get("series_site_id"), s.get("corner_site_id"))
                if key not in seen:
                    seen.add(key)
                    entry = _make_entry(s, genre=g)
                    programs.append(entry)
                    program_map[key] = entry
                else:
                    existing = program_map.get(key)
                    if existing is not None and not existing.get("genre"):
                        existing["genre"] = g
                        existing["genre_label"] = _genre_label(g)
        except Exception:
            pass

    if programs:
        print(f" {len(programs)} 件")
        return programs

    print(" 失敗 (フォールバック)")
    return _fallback_program_list()


def _fetch_by_genre(genre: str) -> list[dict]:
    """指定ジャンルの番組一覧を取得する"""
    label = {"language": "語学講座", "music": "音楽", "news": "ニュース",
             "drama": "ドラマ", "sports": "スポーツ", "documentary": "ドキュメンタリー",
             "variety": "バラエティ"}.get(genre, genre)
    print(f"{label}一覧を取得中...", end="", flush=True)
    try:
        data = http_get_json(NHK_API_GENRE.format(genre=genre))
        programs = [_make_entry(s, genre=genre) for s in data.get("series", [])]
        print(f" {len(programs)} 件")
        return programs
    except Exception as e:
        print(f" 失敗: {e}")
        return _fallback_program_list() if genre == "language" else []


def _fallback_program_list() -> list[dict]:
    """
    API 取得失敗時のフォールバック。
    2026年4月時点の正確な ID。
    """
    entries = [
        ("ラジオ英会話",                    "PMMJ59J6N2", "01"),
        ("基礎英語 レベル2",                "83RW6PK3GG",  "01"),
        ("基礎英語 レベル1",                "148W8XX226",  "01"),
        ("小学生の基礎英語",                "GGQY3M1929",  "01"),
        ("エンジョイ・シンプル・イングリッシュ", "BR8Z3NX7XM", "01"),
        ("まいにちロシア語",                "YRLK72JZ7Q",  "01"),
        ("まいにちイタリア語",              "LJWZP7XVMX",  "01"),
        ("まいにちフランス語",              "XQ487ZM61K",  "01"),
        ("まいにちスペイン語",              "NRZWXVGQ19",  "01"),
        ("まいにちドイツ語",                "N8PZRZ9WQY",  "01"),
        ("まいにち中国語",                  "983PKQPYN7",  "01"),
        ("まいにちハングル講座",            "LR47WW9K14",  "01"),
        ("ポルトガル語講座",                "N13V9K157Y",  "01"),
        ("英会話タイムトライアル",          "8Z6XJ6J415",  "01"),
        ("ニュースで学ぶ「現代英語」",      "77RQWQX1L6",  "01"),
        ("ラジオビジネス英語",              "368315KKP8",  "01"),
    ]
    return [
        {
            "title":     title,
            "display_title": title,
            "display_date": "----",
            "genre": "language",
            "genre_label": _genre_label("language"),
            "site_id":   site_id,
            "corner_id": corner_id,
            "url":       NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
        }
        for title, site_id, corner_id in entries
    ]


# ──────────────────────────────────────────────────────
# エピソード取得 (yt-dlp 経由)
# ──────────────────────────────────────────────────────

def _parse_episode_info(info: dict, program: dict) -> dict:
    """yt-dlp の JSON 行 1 件をエピソード辞書に変換する。"""
    ep_id = str(info.get("id", ""))
    title = info.get("title") or ep_id
    upload_date = info.get("upload_date") or ""
    timestamp = info.get("release_timestamp") or info.get("timestamp")
    duration = info.get("duration")
    date = upload_date or (str(int(timestamp)) if timestamp else "")
    ep_url = info.get("url") or info.get("webpage_url") or ""
    if ep_id and not ep_url.startswith("http"):
        ep_url = NHK_EPISODE_TMPL.format(
            site_id=program["site_id"],
            corner_id=program["corner_id"],
            episode_id=ep_id,
        )
    return {
        "id": ep_id,
        "title": title,
        "display_title": _normalize_text(title),
        "date": date,
        "display_date": _format_episode_date(upload_date or date),
        "broadcast_time": _format_broadcast_time(timestamp),
        "duration_str": _format_duration(duration),
        "url": ep_url,
    }


def _report_fetch_result(episodes: list[dict], stderr: str, verbose: bool) -> None:
    if not verbose:
        return
    if episodes:
        print(f" {len(episodes)} 件")
    else:
        detail = stderr.strip()
        if detail:
            print(f" 失敗: {detail.splitlines()[-1]}")
        else:
            print(" 0件 (エピソードが見つからないか期限切れの可能性があります)")


def fetch_episodes(program: dict, verbose: bool = True) -> list[dict]:
    """yt-dlp --flat-playlist を使って番組のエピソード一覧を取得する。"""
    if verbose:
        print(f"\n「{program['title']}」のエピソードを取得中...", end="", flush=True)
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--dump-json", program["url"]],
        capture_output=True, text=True, timeout=30,
    )
    episodes = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            info = json.loads(line)
        except json.JSONDecodeError:
            continue
        episodes.append(_parse_episode_info(info, program))
    _report_fetch_result(episodes, result.stderr, verbose)
    return episodes


def get_episode_list(
    program: dict,
    retry_delay: float = 1.0,
    use_cache: bool = True,
) -> tuple[list[dict], str]:
    if use_cache:
        cached = _load_episode_cache(program)
        if cached is not None:
            return cached, "cache"

    return refresh_episode_list(program, retry_delay=retry_delay)


def refresh_episode_list(
    program: dict,
    retry_delay: float = 1.0,
) -> tuple[list[dict], str]:
    last_error = ""
    for attempt in range(2):
        try:
            episodes = fetch_episodes(program, verbose=False)
            if episodes:
                _save_episode_cache(program, episodes)
                return episodes, "network"
            last_error = "0件"
        except Exception as e:
            last_error = str(e)

        if attempt == 0:
            time.sleep(retry_delay)

    stale = _load_episode_cache(program, ttl_seconds=10**12)
    if stale is not None:
        return stale, "stale-cache"

    raise RuntimeError(last_error or "エピソード一覧を取得できませんでした")


__all__ = [name for name in globals() if not name.startswith("__")]

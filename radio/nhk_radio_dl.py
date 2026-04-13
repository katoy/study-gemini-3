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
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
except ImportError:
    tk = None
    tkfont = None
    ttk = None

# ──────────────────────────────────────────────────────
# NHK API / URL 定数
# ──────────────────────────────────────────────────────

NHK_ONDEMAND_URL    = "https://www.nhk.or.jp/radio/ondemand/"
NHK_API_SERIES      = "https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/series"
NHK_API_NEW_CORNERS = "https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/corners/new_arrivals"
NHK_API_GENRE       = "https://www.nhk.or.jp/radio-api/app/v1/web/ondemand/series?genre={genre}"
NHK_DETAIL_TMPL     = "https://www.nhk.or.jp/radio/ondemand/detail.html?p={site_id}_{corner_id}"

# 有効なジャンル一覧 (API 確認済み)
NHK_GENRES = ["language", "music", "news", "drama", "sports", "documentary", "variety"]
NHK_EPISODE_TMPL  = (
    "https://www.nhk.or.jp/radio/player/ondemand.html"
    "?p={site_id}_{corner_id}_{episode_id}"
)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ja,en;q=0.9"}
JP_WEEKDAYS = "月火水木金土日"
CACHE_TTL_SECONDS = 3600
CACHE_ROOT_DIR = Path(__file__).resolve().parent / ".cache"
PROGRAM_CACHE_DIR = CACHE_ROOT_DIR / "programs"
EPISODE_CACHE_DIR = CACHE_ROOT_DIR / "episodes"
UI_SETTINGS_PATH = CACHE_ROOT_DIR / "ui_settings.json"
DEFAULT_UI_THEME = "light"
DEFAULT_UI_FONT_SIZE_PT = "11"
SEARCH_HISTORY_LIMIT = 30
GENRE_LABELS = {
    "language": "語学",
    "music": "音楽",
    "news": "ニュース",
    "drama": "ドラマ",
    "sports": "スポーツ",
    "documentary": "ドキュメンタリー",
    "variety": "バラエティ",
}


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


def _program_cache_path(genre: str | None) -> Path:
    return PROGRAM_CACHE_DIR / f"{genre or 'all'}.json"


def _normalize_cached_program(program: dict) -> dict:
    normalized = dict(program)
    normalized["display_date"] = _format_onair_date(str(program.get("onair_date", "")))
    return normalized


def _load_program_cache(genre: str | None, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[dict] | None:
    cache_path = _program_cache_path(genre)
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    fetched_at = payload.get("fetched_at")
    programs = payload.get("programs")
    if not isinstance(fetched_at, (int, float)) or not isinstance(programs, list):
        return None
    if time.time() - float(fetched_at) > ttl_seconds:
        return None
    return [_normalize_cached_program(program) for program in programs if isinstance(program, dict)]


def _save_program_cache(genre: str | None, programs: list[dict]):
    cache_path = _program_cache_path(genre)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": time.time(), "genre": genre, "programs": programs}
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def clear_program_cache() -> int:
    if not PROGRAM_CACHE_DIR.exists():
        return 0

    removed = 0
    for path in PROGRAM_CACHE_DIR.glob("*.json"):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def _episode_cache_path(program: dict) -> Path:
    return EPISODE_CACHE_DIR / f"{program['site_id']}_{program['corner_id']}.json"


def _normalize_cached_episode(episode: dict) -> dict:
    normalized = dict(episode)
    normalized["display_date"] = _format_episode_date(str(episode.get("date", "")))
    return normalized


def _load_episode_cache(program: dict, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[dict] | None:
    cache_path = _episode_cache_path(program)
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    fetched_at = payload.get("fetched_at")
    episodes = payload.get("episodes")
    if not isinstance(fetched_at, (int, float)) or not isinstance(episodes, list):
        return None
    if time.time() - float(fetched_at) > ttl_seconds:
        return None
    return [_normalize_cached_episode(episode) for episode in episodes if isinstance(episode, dict)]


def _save_episode_cache(program: dict, episodes: list[dict]):
    cache_path = _episode_cache_path(program)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.time(),
        "site_id": program["site_id"],
        "corner_id": program["corner_id"],
        "episodes": episodes,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def clear_episode_cache() -> int:
    if not EPISODE_CACHE_DIR.exists():
        return 0

    removed = 0
    for path in EPISODE_CACHE_DIR.glob("*.json"):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def clear_all_cache() -> int:
    return clear_program_cache() + clear_episode_cache()


def _load_ui_settings() -> dict[str, str | list[str]]:
    if not UI_SETTINGS_PATH.exists():
        return {}

    try:
        payload = json.loads(UI_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    settings: dict[str, str | list[str]] = {}

    theme = payload.get("theme")
    if theme in {"light", "dark"}:
        settings["theme"] = theme

    font_size = payload.get("font_size_pt")
    try:
        font_size_pt = int(font_size)
    except (TypeError, ValueError):
        font_size_pt = None
    if font_size_pt is not None:
        font_size_pt = min(max(font_size_pt, 9), 18)
        settings["font_size_pt"] = str(font_size_pt)

    search_history = payload.get("program_search_history")
    if isinstance(search_history, list):
        normalized_history: list[str] = []
        seen: set[str] = set()
        for item in search_history:
            if not isinstance(item, str):
                continue
            term = _normalize_text(item)
            if not term:
                continue
            key = unicodedata.normalize("NFKC", term).casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized_history.append(term)
            if len(normalized_history) >= SEARCH_HISTORY_LIMIT:
                break
        if normalized_history:
            settings["program_search_history"] = normalized_history

    return settings


def _save_ui_settings(theme: str, font_size_pt: str, program_search_history: list[str] | None = None):
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "theme": theme,
        "font_size_pt": int(font_size_pt),
        "program_search_history": program_search_history or [],
    }
    UI_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _program_output_dir(output_dir: Path, program: dict) -> Path:
    genre_dir = _safe_name(program.get("genre_label") or _genre_label(program.get("genre")))
    title_dir = _safe_name(program.get("title") or program.get("display_title") or "unknown")
    return output_dir / genre_dir / title_dir


def _program_filename_template(program: dict, max_items: bool = False) -> str:
    title = _safe_name(program.get("title") or program.get("display_title") or "unknown")
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
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"downloaded": sorted(downloaded), "paths": paths}
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _episode_output_patterns(program: dict, episode: dict) -> list[str]:
    program_title = _safe_name(program.get("title") or program.get("display_title") or "unknown")
    episode_title = _safe_name(episode.get("title") or episode.get("display_title") or "unknown")
    episode_date = str(episode.get("date") or "").strip()
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

    program_title = _safe_name(program.get("title") or program.get("display_title") or "unknown")
    episode_title = _safe_name(episode.get("title") or episode.get("display_title") or "unknown")
    episode_date = str(episode.get("date") or "").strip()
    stem = path.stem

    if episode_date:
        expected = f"{episode_date}_{program_title}_{episode_title}"
        return stem == expected or stem.endswith(f"_{expected}")

    expected = f"{program_title}_{episode_title}"
    return stem == expected or stem.endswith(f"_{expected}")


def _episode_output_candidates(program_dir: Path, program: dict, episode: dict) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    program_title = _safe_name(program.get("title") or program.get("display_title") or "unknown")
    episode_title = _safe_name(episode.get("title") or episode.get("display_title") or "unknown")
    episode_date = str(episode.get("date") or "").strip()
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
    cmd = ["yt-dlp", "--newline"]
    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    cmd += ["--no-playlist", "-o", str(output_dir / filename_template), url]
    return cmd


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
# エピソード一覧の取得 (yt-dlp 経由)
# ──────────────────────────────────────────────────────

def fetch_episodes(program: dict, verbose: bool = True) -> list[dict]:
    """
    yt-dlp --flat-playlist を使って番組のエピソード一覧を取得する。

    Returns:
        [{"id": str, "title": str, "upload_date": str, "url": str}, ...]
    """
    url = program["url"]
    if verbose:
        print(f"\n「{program['title']}」のエピソードを取得中...", end="", flush=True)

    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--dump-json", url],
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

        ep_id = str(info.get("id", ""))
        title = info.get("title") or ep_id
        upload_date = info.get("upload_date") or ""
        timestamp = info.get("release_timestamp") or info.get("timestamp")
        duration = info.get("duration")
        date = upload_date or (str(int(timestamp)) if timestamp else "")
        ep_url = info.get("url") or info.get("webpage_url") or ""

        # URL が相対パスや ID だけの場合はエピソード URL を構築
        if ep_id and not ep_url.startswith("http"):
            ep_url = NHK_EPISODE_TMPL.format(
                site_id=program["site_id"],
                corner_id=program["corner_id"],
                episode_id=ep_id,
            )

        episodes.append({
            "id": ep_id,
            "title": title,
            "display_title": _normalize_text(title),
            "date": date,
            "display_date": _format_episode_date(upload_date or date),
            "broadcast_time": _format_broadcast_time(timestamp),
            "duration_str": _format_duration(duration),
            "url": ep_url,
        })

    if episodes:
        if verbose:
            print(f" {len(episodes)} 件")
    else:
        if verbose:
            detail = result.stderr.strip()
            if detail:
                print(f" 失敗: {detail.splitlines()[-1]}")
            else:
                print(" 0件 (エピソードが見つからないか期限切れの可能性があります)")

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


class EpisodeGuiBrowser:
    def __init__(self, programs: list[dict], output_dir: Path):
        if tk is None or ttk is None:
            raise RuntimeError("tkinter が利用できません")

        self.programs = programs
        self.output_dir = output_dir
        self.result: tuple[dict, list[dict]] | tuple[None, None] = (None, None)
        self.loading = False
        self.fetch_result_queue: queue.Queue | None = None
        self.download_result_queue: queue.Queue = queue.Queue()
        self.download_polling = False
        self.download_cancel_events: dict[str, threading.Event] = {}
        self.download_processes: dict[str, subprocess.Popen] = {}
        self.download_process_lock = threading.Lock()
        self.active_download_rows: dict[str, dict] = {}
        self.active_download_meta: dict[str, tuple[dict, dict]] = {}
        self.download_started_count = 0
        self.download_finished_count = 0
        self.episodes_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
        self.filtered_programs = list(programs)
        self.program_tree_programs: dict[str, dict] = {}
        self.displayed_program: dict | None = None
        self.displayed_episodes: list[dict] = []
        self.displayed_episode_map: dict[str, dict] = {}
        self.saved_episode_buttons: dict[str, ttk.Button] = {}
        self.saved_button_refresh_pending = False
        self.saved_episode_popup: tk.Toplevel | None = None

        self.root = tk.Tk()
        self.root.title("NHK ラジオ 聞き逃しブラウザ")
        self.root.geometry("1360x840")
        self.root.minsize(1040, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self.current_theme = DEFAULT_UI_THEME
        self.current_font_size = DEFAULT_UI_FONT_SIZE_PT
        self.current_screen = "browser"
        saved_ui_settings = _load_ui_settings()
        self.current_theme = saved_ui_settings.get("theme", self.current_theme)
        self.current_font_size = saved_ui_settings.get("font_size_pt", self.current_font_size)
        self.program_search_history = list(saved_ui_settings.get("program_search_history", []))
        self.font_family = self._resolve_mono_font_family()

        self.status_var = tk.StringVar(value="番組を選択してください。")
        self.selected_cell_meta_var = tk.StringVar(value="セルをクリックすると、ここで値を選択・コピーできます。")
        self.selected_cell_value_var = tk.StringVar(value="")
        self.program_list_summary_var = tk.StringVar(value=f"{len(programs)} 番組")
        self.program_search_var = tk.StringVar()
        self.selected_program_title_var = tk.StringVar(value="番組を選択してください")
        self.selected_program_meta_var = tk.StringVar(value="左の番組一覧から選択すると、ここに番組の概要が表示されます。")
        self.selected_program_stats_var = tk.StringVar(value="エピソード一覧は未取得です。")
        self.episode_message_var = tk.StringVar(value="一覧は未取得です。")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="")
        self.settings_button_var = tk.StringVar()
        self.settings_summary_var = tk.StringVar()
        self.font_size_display_var = tk.StringVar()
        self.theme_var = tk.StringVar(value=self.current_theme)
        self.font_size_var = tk.IntVar(value=int(self.current_font_size))
        self.program_search_var.trace_add("write", self._on_program_search_change)

        self._build_widgets()
        self._populate_programs()

    def _resolve_mono_font_family(self) -> str:
        candidates = (
            "Osaka-Mono",
            "Bizin Gothic",
            "Migu 1M",
            "Noto Sans Mono CJK JP",
            "UDEV Gothic",
            "SF Mono",
            "Menlo",
            "Monaco",
            "MS Gothic",
            "Courier New",
            "Courier",
        )
        if tkfont is None:
            return "Menlo"

        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:
            return "Menlo"

        for family in candidates:
            if family in available:
                return family
        return "TkFixedFont"

    def _theme_palette(self, theme_name: str) -> dict[str, str]:
        if theme_name == "dark":
            return {
                "bg": "#0F1723",
                "surface": "#162130",
                "surface_alt": "#1C293B",
                "accent": "#66A3FF",
                "accent_dark": "#3D7CE0",
                "accent_soft": "#233753",
                "on_accent": "#F8FBFF",
                "selected_fg": "#F3F7FF",
                "text": "#E8EEF8",
                "text_sub": "#A6B4CB",
                "border": "#314257",
                "border_strong": "#40546D",
                "head_bg": "#223247",
                "row_odd": "#1A2636",
                "dl_even": "#183126",
                "dl_odd": "#1C3B2E",
                "input_bg": "#111C2A",
            }
        return {
            "bg": "#EEF3F8",
            "surface": "#FFFFFF",
            "surface_alt": "#F7FAFD",
            "accent": "#2563D6",
            "accent_dark": "#18489C",
            "accent_soft": "#E8F0FF",
            "on_accent": "#FFFFFF",
            "selected_fg": "#12315F",
            "text": "#172033",
            "text_sub": "#61738D",
            "border": "#D5DFEA",
            "border_strong": "#C4D0DE",
            "head_bg": "#EDF2F7",
            "row_odd": "#F8FAFD",
            "dl_even": "#EEF8F2",
            "dl_odd": "#E5F4EC",
            "input_bg": "#FFFFFF",
        }

    def _font_profile(self, size_name: str) -> dict[str, tuple | int]:
        try:
            base = int(size_name)
        except ValueError:
            base = 11
        return {
            "mono_sm": (self.font_family, base),
            "mono": (self.font_family, base + 1),
            "mono_bold": (self.font_family, base + 1, "bold"),
            "app_title": (self.font_family, base + 7, "bold"),
            "heading": (self.font_family, base + 3, "bold"),
            "card_title": (self.font_family, base + 2, "bold"),
            "hero_title": (self.font_family, base + 5, "bold"),
            "popup_title": (self.font_family, base + 2, "bold"),
            "rowheight": base + 17,
        }

    def _load_font_profile(self):
        profile = self._font_profile(self.current_font_size)
        self._mono_sm = profile["mono_sm"]
        self._mono = profile["mono"]
        self._mono_bold = profile["mono_bold"]
        self._app_title_font = profile["app_title"]
        self._heading_font = profile["heading"]
        self._card_title_font = profile["card_title"]
        self._hero_title_font = profile["hero_title"]
        self._popup_title_font = profile["popup_title"]
        self._tree_rowheight = profile["rowheight"]

    def _configure_theme_styles(self):
        p = self._palette
        self.root.configure(background=p["bg"])

        # 基本要素
        self.style.configure(".", background=p["bg"], foreground=p["text"], font=self._mono_sm)
        self.style.configure("TFrame", background=p["bg"])
        self.style.configure("TLabel", background=p["bg"], foreground=p["text"], font=self._mono_sm)
        self.style.configure("Card.TFrame", background=p["surface"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("CardInner.TFrame", background=p["surface"])
        self.style.configure("Sidebar.TFrame", background=p["surface_alt"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("SidebarInner.TFrame", background=p["surface_alt"])
        self.style.configure("Hero.TFrame", background=p["accent_soft"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("HeroInner.TFrame", background=p["accent_soft"])
        self.style.configure("TLabelframe", background=p["surface"], bordercolor=p["border"], relief="solid", borderwidth=1)
        self.style.configure("TLabelframe.Label", background=p["surface"], foreground=p["text_sub"], font=self._mono_sm)
        self.style.configure("TSeparator", background=p["border"])
        self.style.configure(
            "TScrollbar",
            background=p["head_bg"],
            troughcolor=p["bg"],
            bordercolor=p["border"],
            arrowcolor=p["text_sub"],
        )

        # Treeview
        self.style.configure(
            "Treeview",
            font=self._mono,
            rowheight=self._tree_rowheight,
            background=p["surface"],
            foreground=p["text"],
            fieldbackground=p["surface"],
            bordercolor=p["border_strong"],
            lightcolor=p["border_strong"],
            darkcolor=p["border_strong"],
        )
        self.style.configure(
            "Treeview.Heading",
            font=self._mono_bold,
            background=p["head_bg"],
            foreground=p["text"],
            relief="flat",
            padding=(10, 7),
            bordercolor=p["border_strong"],
        )
        self.style.map(
            "Treeview",
            background=[("selected", p["accent_soft"])],
            foreground=[("selected", p["selected_fg"])],
        )
        self.style.map("Treeview.Heading", background=[("active", p["border"])])

        # ボタン / 入力
        self.style.configure("TButton", font=self._mono_sm, padding=(10, 6))
        self.style.configure(
            "Accent.TButton",
            font=self._mono_bold,
            padding=(12, 7),
            background=p["accent"],
            foreground=p["on_accent"],
            bordercolor=p["accent_dark"],
        )
        self.style.map(
            "Accent.TButton",
            background=[("active", p["accent_dark"]), ("disabled", p["head_bg"])],
            foreground=[("active", p["on_accent"]), ("disabled", p["text_sub"])],
        )
        self.style.configure(
            "Quiet.TButton",
            background=p["surface_alt"],
            foreground=p["text"],
            bordercolor=p["border_strong"],
        )
        self.style.map(
            "Quiet.TButton",
            background=[("active", p["head_bg"]), ("disabled", p["surface_alt"])],
            foreground=[("disabled", p["text_sub"])],
        )
        self.style.configure(
            "SavedCell.TButton",
            font=self._mono_bold,
            padding=(0, 0),
            background=p["accent"],
            foreground=p["on_accent"],
            bordercolor=p["accent_dark"],
        )
        self.style.map(
            "SavedCell.TButton",
            background=[("active", p["accent_dark"]), ("pressed", p["accent_dark"])],
            foreground=[("active", p["on_accent"]), ("pressed", p["on_accent"])],
        )
        self.style.configure(
            "Toggle.TButton",
            font=self._mono_sm,
            padding=(12, 5),
            background=p["head_bg"],
            foreground=p["text"],
            bordercolor=p["border_strong"],
        )
        self.style.map(
            "Toggle.TButton",
            background=[("active", p["accent_soft"]), ("disabled", p["head_bg"])],
            foreground=[("disabled", p["text_sub"])],
        )
        self.style.configure(
            "Settings.TRadiobutton",
            background=p["surface"],
            foreground=p["text"],
            font=self._mono_sm,
        )
        self.style.map(
            "Settings.TRadiobutton",
            background=[("active", p["surface"])],
            foreground=[("disabled", p["text_sub"])],
        )
        self.style.configure(
            "Settings.Horizontal.TScale",
            background=p["surface"],
            troughcolor=p["head_bg"],
            bordercolor=p["border_strong"],
        )
        self.style.configure(
            "TEntry",
            fieldbackground=p["input_bg"],
            foreground=p["text"],
            insertcolor=p["text"],
            bordercolor=p["border_strong"],
            lightcolor=p["border_strong"],
            darkcolor=p["border_strong"],
        )
        self.style.map(
            "TEntry",
            fieldbackground=[("readonly", p["input_bg"])],
            foreground=[("readonly", p["text"])],
        )
        self.style.configure(
            "Search.TCombobox",
            fieldbackground=p["input_bg"],
            background=p["input_bg"],
            foreground=p["text"],
            insertcolor=p["text"],
            arrowcolor=p["text_sub"],
            bordercolor=p["border_strong"],
            lightcolor=p["border_strong"],
            darkcolor=p["border_strong"],
            padding=(4, 2),
        )
        self.style.map(
            "Search.TCombobox",
            fieldbackground=[("readonly", p["input_bg"]), ("disabled", p["head_bg"])],
            foreground=[("disabled", p["text_sub"])],
            arrowcolor=[("disabled", p["text_sub"]), ("active", p["text"])],
        )
        self.root.option_add("*TCombobox*Listbox.background", p["input_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["on_accent"])

        # Progressbar
        self.style.configure("TProgressbar", background=p["accent"], troughcolor=p["head_bg"], bordercolor=p["border"])

        # カスタムラベル
        self.style.configure("AppTitle.TLabel", font=self._app_title_font, foreground=p["text"], background=p["surface"])
        self.style.configure("AppSub.TLabel", font=self._mono_sm, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("SettingLabel.TLabel", font=self._mono_sm, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("Heading.TLabel", font=self._heading_font, foreground=p["accent"], background=p["bg"])
        self.style.configure("CardTitle.TLabel", font=self._card_title_font, foreground=p["text"], background=p["surface"])
        self.style.configure("CardTitleAlt.TLabel", font=self._card_title_font, foreground=p["text"], background=p["surface_alt"])
        self.style.configure("CardMeta.TLabel", font=self._mono_sm, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("CardMetaAlt.TLabel", font=self._mono_sm, foreground=p["text_sub"], background=p["surface_alt"])
        self.style.configure("HeroTitle.TLabel", font=self._hero_title_font, foreground=p["text"], background=p["accent_soft"])
        self.style.configure("HeroMeta.TLabel", font=self._mono_sm, foreground=p["text_sub"], background=p["accent_soft"])
        self.style.configure("HeroStats.TLabel", font=self._mono_bold, foreground=p["accent"], background=p["accent_soft"])
        self.style.configure("Status.TLabel", font=self._mono_sm, foreground=p["text_sub"], background=p["bg"])
        self.style.configure("PopupTitle.TLabel", font=self._popup_title_font, foreground=p["text"], background=p["surface"])
        self.style.configure("PopupLabel.TLabel", font=self._mono_bold, foreground=p["text"], background=p["surface"])
        self.style.configure("PopupValue.TLabel", font=self._mono_sm, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("SettingsValue.TLabel", font=self._mono_bold, foreground=p["accent"], background=p["surface"])
        self.style.configure("SettingsPreview.TLabel", font=self._mono_sm, foreground=p["text"], background=p["surface"])
        self.style.configure(
            "FontScaleMin.TLabel",
            font=(self.font_family, max(int(self.current_font_size) - 1, 9), "bold"),
            foreground=p["text_sub"],
            background=p["surface"],
        )
        self.style.configure(
            "FontScaleMax.TLabel",
            font=(self.font_family, int(self.current_font_size) + 5, "bold"),
            foreground=p["text"],
            background=p["surface"],
        )
        self.style.configure("FontPreview.TFrame", background=p["surface_alt"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("FontPreviewTitle.TLabel", font=self._mono_bold, foreground=p["text"], background=p["surface_alt"])
        self.style.configure("FontPreviewBody.TLabel", font=self._mono_sm, foreground=p["text"], background=p["surface_alt"])
        self.style.configure("ScaleTick.TLabel", font=(self.font_family, 9), foreground=p["text_sub"], background=p["surface"])
        self.style.configure("ScaleMark.TLabel", font=(self.font_family, 9), foreground=p["border_strong"], background=p["surface"])
        if hasattr(self, "download_jobs_canvas"):
            self.download_jobs_canvas.configure(
                background=p["surface"],
                highlightbackground=p["border"],
                highlightcolor=p["border"],
            )

    def _refresh_treeview_theme(self):
        p = self._palette
        self.program_tree.tag_configure("even", background=p["surface"], foreground=p["text"])
        self.program_tree.tag_configure("odd", background=p["row_odd"], foreground=p["text"])
        self.episode_tree.tag_configure("even", background=p["surface"], foreground=p["text"])
        self.episode_tree.tag_configure("odd", background=p["row_odd"], foreground=p["text"])
        self.episode_tree.tag_configure("dl_even", background=p["dl_even"], foreground=p["text"])
        self.episode_tree.tag_configure("dl_odd", background=p["dl_odd"], foreground=p["text"])
        self._schedule_saved_button_refresh()

    def _update_settings_ui(self):
        theme_label = "ダーク" if self.current_theme == "dark" else "ライト"
        self.settings_summary_var.set(f"{theme_label} / 文字 {self.current_font_size}pt")
        self.font_size_display_var.set(f"{self.current_font_size} pt")
        self.settings_button_var.set("ブラウザに戻る" if self.current_screen == "settings" else "表示設定")
        self.theme_var.set(self.current_theme)
        self.font_size_var.set(int(self.current_font_size))

    def _show_screen(self, screen_name: str, announce: bool = True):
        self.current_screen = screen_name
        if screen_name == "settings":
            self.browser_screen.grid_remove()
            self.settings_screen.grid()
            if announce:
                self.status_var.set("表示設定画面を開きました。")
        else:
            self.settings_screen.grid_remove()
            self.browser_screen.grid()
            if announce:
                self.status_var.set("ブラウザ画面に戻りました。")
        self._update_settings_ui()

    def _toggle_settings_screen(self):
        next_screen = "browser" if self.current_screen == "settings" else "settings"
        self._show_screen(next_screen)

    def _persist_ui_settings(self):
        _save_ui_settings(self.current_theme, self.current_font_size, self.program_search_history)

    def _apply_theme(self, theme_name: str, announce: bool = True):
        self.current_theme = theme_name
        self._palette = self._theme_palette(theme_name)
        self._configure_theme_styles()
        self._refresh_treeview_theme()
        self._update_settings_ui()
        self._persist_ui_settings()
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.configure(background=self._palette["surface"])
        if announce:
            theme_label = "ダーク" if theme_name == "dark" else "ライト"
            self.status_var.set(f"{theme_label}テーマに切り替えました。")

    def _apply_font_size(self, size_name: str, announce: bool = True):
        self.current_font_size = size_name
        self._load_font_profile()
        self._configure_theme_styles()
        self._refresh_treeview_theme()
        self._update_settings_ui()
        self._persist_ui_settings()
        if announce:
            self.status_var.set(f"文字サイズを {size_name}pt に変更しました。")

    def _on_font_size_scale(self, value):
        size_pt = str(int(round(float(value))))
        if size_pt == self.current_font_size:
            self.font_size_display_var.set(f"{size_pt} pt")
            return
        self._apply_font_size(size_pt, announce=False)

    def _adjust_font_size_scale(self, delta: int):
        current = int(round(float(self.font_size_var.get())))
        next_value = min(max(current + delta, 9), 18)
        self.font_size_var.set(next_value)
        self._on_font_size_scale(str(next_value))

    def _on_font_size_scale_left(self, _event=None):
        self._adjust_font_size_scale(-1)
        return "break"

    def _on_font_size_scale_right(self, _event=None):
        self._adjust_font_size_scale(1)
        return "break"

    def _on_font_size_scale_home(self, _event=None):
        self.font_size_var.set(9)
        self._on_font_size_scale("9")
        return "break"

    def _on_font_size_scale_end(self, _event=None):
        self.font_size_var.set(18)
        self._on_font_size_scale("18")
        return "break"

    def _reset_ui_settings(self):
        self._apply_theme(DEFAULT_UI_THEME, announce=False)
        self._apply_font_size(DEFAULT_UI_FONT_SIZE_PT, announce=False)
        self.status_var.set("表示設定を規定値にリセットしました。")

    def _build_widgets(self):
        # ── フォント ────────────────────────────────────────────
        self._load_font_profile()
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self._palette = self._theme_palette(self.current_theme)
        self._configure_theme_styles()

        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        header = ttk.Frame(main, style="Card.TFrame", padding=18)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)
        ttk.Label(header, text="NHK ラジオ 聞き逃し", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")

        header_right = ttk.Frame(header, style="CardInner.TFrame")
        header_right.grid(row=0, column=1, sticky="ne")
        header_right.columnconfigure(0, weight=1)

        header_actions = ttk.Frame(header_right, style="CardInner.TFrame")
        header_actions.grid(row=0, column=0, sticky="e")
        self.settings_button = ttk.Button(
            header_actions,
            textvariable=self.settings_button_var,
            command=self._toggle_settings_screen,
            style="Toggle.TButton",
        )
        self.settings_button.grid(row=0, column=0, padx=(0, 8))
        self.clear_button = ttk.Button(header_actions, text="キャッシュを全削除", command=self._clear_cache, style="Quiet.TButton")
        self.clear_button.grid(row=0, column=1, padx=(0, 8))
        self.cancel_button = ttk.Button(header_actions, text="閉じる", command=self._cancel)
        self.cancel_button.grid(row=0, column=2)

        self.screen_container = ttk.Frame(main)
        self.screen_container.grid(row=1, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        self.browser_screen = ttk.Frame(self.screen_container)
        self.browser_screen.grid(row=0, column=0, sticky="nsew")
        self.browser_screen.columnconfigure(0, weight=1)
        self.browser_screen.rowconfigure(0, weight=1)

        self.browser_panes = ttk.Panedwindow(self.browser_screen, orient="horizontal")
        self.browser_panes.grid(row=0, column=0, sticky="nsew")

        sidebar = ttk.Frame(self.browser_panes, style="Sidebar.TFrame", padding=16, width=430)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)
        ttk.Label(sidebar, text="番組一覧", style="CardTitleAlt.TLabel").grid(row=0, column=0, sticky="w")
        sidebar_actions = ttk.Frame(sidebar, style="SidebarInner.TFrame")
        sidebar_actions.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        sidebar_actions.columnconfigure(0, weight=1)
        ttk.Label(
            sidebar_actions,
            text="Enter またはダブルクリックで選択番組のエピソード一覧を取得",
            style="CardMetaAlt.TLabel",
        ).grid(row=0, column=0, sticky="w")
        search_row = ttk.Frame(sidebar_actions, style="SidebarInner.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="検索", style="CardMetaAlt.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.program_search_entry = ttk.Combobox(
            search_row,
            textvariable=self.program_search_var,
            values=self.program_search_history,
            style="Search.TCombobox",
        )
        self.program_search_entry.grid(row=0, column=1, sticky="ew")
        self.program_search_entry.bind("<Escape>", self._clear_program_search)
        self.program_search_entry.bind("<Down>", self._focus_program_tree_from_search)
        self.program_search_entry.bind("<Return>", self._commit_program_search)
        self.program_search_entry.bind("<<ComboboxSelected>>", self._on_program_search_history_selected)
        self.program_search_entry.bind("<FocusIn>", self._on_program_search_focus_in)
        self.program_search_entry.bind("<FocusOut>", self._on_program_search_focus_out)
        ttk.Button(search_row, text="クリア", command=self._clear_program_search, style="Quiet.TButton").grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Label(sidebar_actions, textvariable=self.program_list_summary_var, style="CardMetaAlt.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )

        self.program_tree = ttk.Treeview(
            sidebar,
            columns=("no", "date", "title"),
            show="headings",
            selectmode="browse",
        )
        self.program_tree.heading("no", text="No.")
        self.program_tree.heading("date", text="更新日")
        self.program_tree.heading("title", text="番組")
        self.program_tree.column("no", width=50, anchor="e", stretch=False)
        self.program_tree.column("date", width=140, anchor="w", stretch=False)
        self.program_tree.column("title", width=360, anchor="w")
        program_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.program_tree.yview)
        self.program_tree.configure(yscrollcommand=program_scroll.set)
        self.program_tree.grid(row=2, column=0, sticky="nsew")
        program_scroll.grid(row=2, column=1, sticky="ns")
        self.browser_panes.add(sidebar, weight=11)

        right_panes = ttk.Panedwindow(self.browser_panes, orient="vertical")
        self.browser_panes.add(right_panes, weight=23)

        detail = ttk.Frame(right_panes, style="Card.TFrame", padding=18, width=860, height=520)
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(2, weight=1)

        hero = ttk.Frame(detail, style="Hero.TFrame", padding=16)
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)
        ttk.Label(hero, textvariable=self.selected_program_title_var, style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hero, textvariable=self.selected_program_stats_var, style="HeroStats.TLabel").grid(
            row=1, column=0, sticky="w", pady=(10, 0)
        )
        hero_actions = ttk.Frame(hero, style="HeroInner.TFrame")
        hero_actions.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(18, 0))
        self.download_button = ttk.Button(
            hero_actions,
            text="選択エピソードをダウンロード",
            command=self._start_download_selected,
            style="Accent.TButton",
        )
        self.download_button.grid(row=0, column=0)

        self.episode_title_var = tk.StringVar(value="エピソード一覧")
        section = ttk.Frame(detail, style="CardInner.TFrame")
        section.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        section.columnconfigure(0, weight=1)
        ttk.Label(section, textvariable=self.episode_title_var, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")

        self.episode_tree = ttk.Treeview(
            detail,
            columns=("saved", "date", "duration", "title"),
            show="headings",
            selectmode="extended",
        )
        self.episode_tree.heading("saved", text="DL")
        self.episode_tree.heading("date", text="放送日時")
        self.episode_tree.heading("duration", text="長さ")
        self.episode_tree.heading("title", text="タイトル")
        self.episode_tree.column("saved", width=82, anchor="center", stretch=False)
        self.episode_tree.column("date", width=190, anchor="w", stretch=False)
        self.episode_tree.column("duration", width=100, anchor="e", stretch=False)
        self.episode_tree.column("title", width=560, anchor="w")
        self.episode_scroll = ttk.Scrollbar(detail, orient="vertical", command=self._on_episode_tree_scroll)
        self.episode_tree.configure(yscrollcommand=self._on_episode_tree_yscroll)
        self.episode_tree.grid(row=2, column=0, sticky="nsew")
        self.episode_scroll.grid(row=2, column=1, sticky="ns")
        right_panes.add(detail, weight=5)

        activity = ttk.Frame(right_panes, style="Card.TFrame", padding=16, height=220)
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(3, weight=1)
        ttk.Label(activity, text="ダウンロード状況", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(activity, orient="horizontal", mode="determinate", variable=self.progress_var, maximum=1)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.progress_label = ttk.Label(activity, textvariable=self.progress_text_var, anchor="w", style="CardMeta.TLabel")
        self.progress_label.grid(row=2, column=0, sticky="ew", pady=(6, 10))
        self.download_jobs_frame = ttk.LabelFrame(activity, text="ジョブ一覧", padding=10)
        self.download_jobs_frame.grid(row=3, column=0, sticky="nsew")
        self.download_jobs_frame.columnconfigure(0, weight=1)
        self.download_jobs_frame.rowconfigure(0, weight=1)
        self.download_jobs_canvas = tk.Canvas(
            self.download_jobs_frame,
            background=self._palette["surface"],
            highlightthickness=1,
            bd=0,
            relief="flat",
        )
        self.download_jobs_canvas.grid(row=0, column=0, sticky="nsew")
        self.download_jobs_scrollbar = ttk.Scrollbar(
            self.download_jobs_frame,
            orient="vertical",
            command=self.download_jobs_canvas.yview,
        )
        self.download_jobs_scrollbar.grid(row=0, column=1, sticky="ns")
        self.download_jobs_canvas.configure(yscrollcommand=self.download_jobs_scrollbar.set)
        self.download_jobs_inner = ttk.Frame(self.download_jobs_canvas, style="CardInner.TFrame")
        self.download_jobs_window = self.download_jobs_canvas.create_window((0, 0), window=self.download_jobs_inner, anchor="nw")
        self.download_jobs_inner.columnconfigure(0, weight=1)
        self.download_jobs_inner.bind("<Configure>", self._on_download_jobs_inner_configure)
        self.download_jobs_canvas.bind("<Configure>", self._on_download_jobs_canvas_configure)
        self.download_jobs_canvas.bind("<MouseWheel>", self._on_download_jobs_mousewheel)
        self.download_jobs_canvas.bind("<Button-4>", self._on_download_jobs_mousewheel)
        self.download_jobs_canvas.bind("<Button-5>", self._on_download_jobs_mousewheel)
        self.download_jobs_inner.bind("<MouseWheel>", self._on_download_jobs_mousewheel)
        self.download_jobs_inner.bind("<Button-4>", self._on_download_jobs_mousewheel)
        self.download_jobs_inner.bind("<Button-5>", self._on_download_jobs_mousewheel)
        self.download_jobs_empty = ttk.Label(self.download_jobs_inner, text="実行中のダウンロードはありません。", style="CardMeta.TLabel")
        self.download_jobs_empty.grid(row=0, column=0, sticky="w")
        right_panes.add(activity, weight=2)

        self.settings_screen = ttk.Frame(self.screen_container, style="Card.TFrame", padding=24)
        self.settings_screen.grid(row=0, column=0, sticky="nsew")
        self.settings_screen.columnconfigure(0, weight=1)

        ttk.Label(self.settings_screen, text="表示設定", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self.settings_screen,
            text="テーマと文字サイズはこの画面でまとめて変更できます。選択内容はその場でブラウザ画面に反映されます。",
            style="AppSub.TLabel",
            wraplength=880,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 18))

        settings_body = ttk.Frame(self.settings_screen, style="CardInner.TFrame")
        settings_body.grid(row=2, column=0, sticky="nsew")
        settings_body.columnconfigure(0, weight=1)
        settings_body.columnconfigure(1, weight=1)

        theme_group = ttk.LabelFrame(settings_body, text="テーマ", padding=16)
        theme_group.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        theme_group.columnconfigure(0, weight=1)
        ttk.Label(theme_group, text="画面全体の配色を切り替えます。", style="CardMeta.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        ttk.Radiobutton(
            theme_group,
            text="ライト",
            value="light",
            variable=self.theme_var,
            command=lambda: self._apply_theme(self.theme_var.get()),
            style="Settings.TRadiobutton",
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Radiobutton(
            theme_group,
            text="ダーク",
            value="dark",
            variable=self.theme_var,
            command=lambda: self._apply_theme(self.theme_var.get()),
            style="Settings.TRadiobutton",
        ).grid(row=2, column=0, sticky="w")

        font_group = ttk.LabelFrame(settings_body, text="文字サイズ", padding=16)
        font_group.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        font_group.columnconfigure(0, weight=1)
        ttk.Label(font_group, text="一覧、カード、設定ラベルの文字サイズを変更します。", style="CardMeta.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        font_control = ttk.Frame(font_group, style="CardInner.TFrame")
        font_control.grid(row=1, column=0, sticky="ew")
        font_control.columnconfigure(1, weight=1)
        ttk.Label(font_control, text="A", style="FontScaleMin.TLabel").grid(row=0, column=0, sticky="sw", padx=(0, 12))
        self.font_size_scale = ttk.Scale(
            font_control,
            from_=9,
            to=18,
            variable=self.font_size_var,
            command=self._on_font_size_scale,
            style="Settings.Horizontal.TScale",
            takefocus=True,
        )
        self.font_size_scale.grid(row=0, column=1, sticky="ew")
        self.font_size_scale.bind("<Left>", self._on_font_size_scale_left)
        self.font_size_scale.bind("<Right>", self._on_font_size_scale_right)
        self.font_size_scale.bind("<Home>", self._on_font_size_scale_home)
        self.font_size_scale.bind("<End>", self._on_font_size_scale_end)
        ttk.Label(font_control, text="A", style="FontScaleMax.TLabel").grid(row=0, column=2, sticky="se", padx=(12, 0))

        scale_meta = ttk.Frame(font_group, style="CardInner.TFrame")
        scale_meta.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        scale_meta.columnconfigure(1, weight=1)
        ttk.Label(scale_meta, text="9 pt", style="CardMeta.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(scale_meta, textvariable=self.font_size_display_var, style="SettingsValue.TLabel").grid(row=0, column=1)
        ttk.Label(scale_meta, text="18 pt", style="CardMeta.TLabel").grid(row=0, column=2, sticky="e")

        scale_ticks = ttk.Frame(font_group, style="CardInner.TFrame")
        scale_ticks.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        for column in range(10):
            scale_ticks.columnconfigure(column, weight=1)
        for value in range(9, 19):
            col = value - 9
            ttk.Label(scale_ticks, text="|", style="ScaleMark.TLabel").grid(row=0, column=col)
            ttk.Label(scale_ticks, text=str(value), style="ScaleTick.TLabel").grid(row=1, column=col)

        font_preview = ttk.Frame(font_group, style="FontPreview.TFrame", padding=14)
        font_preview.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        font_preview.columnconfigure(0, weight=1)
        ttk.Label(font_preview, text="プレビュー", style="FontPreviewTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            font_preview,
            text="ラジオ英会話を、いま選んだ文字サイズで読むイメージです。",
            style="FontPreviewBody.TLabel",
            wraplength=380,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        preview_group = ttk.LabelFrame(self.settings_screen, text="プレビュー", padding=16)
        preview_group.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        preview_group.columnconfigure(0, weight=1)
        ttk.Label(preview_group, textvariable=self.settings_summary_var, style="SettingsValue.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            preview_group,
            text="ラジオ英会話 / 4月13日(月) 06:45 / エピソード 12 件 / 保存済み 3 件",
            style="SettingsPreview.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))

        settings_actions = ttk.Frame(self.settings_screen, style="CardInner.TFrame")
        settings_actions.grid(row=4, column=0, sticky="e", pady=(18, 0))
        ttk.Button(settings_actions, text="規定値にリセット", command=self._reset_ui_settings, style="Quiet.TButton").grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(settings_actions, text="ブラウザに戻る", command=lambda: self._show_screen("browser"), style="Accent.TButton").grid(
            row=0, column=1
        )

        status_area = ttk.Frame(main)
        status_area.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        status_area.columnconfigure(1, weight=1)

        ttk.Label(status_area, textvariable=self.status_var, anchor="w", style="Status.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="ew"
        )
        ttk.Label(status_area, textvariable=self.selected_cell_meta_var, style="Status.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 12)
        )
        self.selected_cell_entry = ttk.Entry(status_area, textvariable=self.selected_cell_value_var)
        self.selected_cell_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.selected_cell_entry.state(["readonly"])
        self.copy_cell_button = ttk.Button(
            status_area,
            text="セル値をコピー",
            command=self._copy_selected_cell_to_clipboard,
            style="Quiet.TButton",
        )
        self.copy_cell_button.grid(row=1, column=2, sticky="e", pady=(8, 0), padx=(8, 0))
        self.copy_cell_button.state(["disabled"])

        self.program_tree.bind("<<TreeviewSelect>>", self._on_program_select)
        self.program_tree.bind("<ButtonRelease-1>", self._on_program_tree_click)
        self.program_tree.bind("<Double-1>", self._on_program_double_click)
        self.program_tree.bind("<Return>", self._start_fetch_selected)
        self.program_tree.bind("<Control-c>", self._copy_selected_cell_to_clipboard)
        self.program_tree.bind("<Command-c>", self._copy_selected_cell_to_clipboard)
        self.episode_tree.bind("<ButtonRelease-1>", self._on_episode_tree_click)
        self.episode_tree.bind("<Motion>", self._on_episode_tree_motion)
        self.episode_tree.bind("<Leave>", self._on_episode_tree_leave)
        self.episode_tree.bind("<Configure>", self._on_episode_tree_configure)
        self.episode_tree.bind("<Double-1>", self._start_download_selected)
        self.episode_tree.bind("<Return>", self._start_download_selected)
        self.episode_tree.bind("<Control-c>", self._copy_selected_cell_to_clipboard)
        self.episode_tree.bind("<Command-c>", self._copy_selected_cell_to_clipboard)

        self.download_button.state(["disabled"])
        self._refresh_treeview_theme()
        self._update_settings_ui()
        self._show_screen("browser", announce=False)

    def _populate_programs(self):
        p = self._palette
        self.program_tree.tag_configure("even", background=p["surface"])
        self.program_tree.tag_configure("odd",  background=p["row_odd"])
        current_program = self._selected_program() or self.displayed_program
        current_key = self._program_key(current_program) if current_program is not None else None
        self.program_tree_programs.clear()
        for item_id in self.program_tree.get_children():
            self.program_tree.delete(item_id)
        selected_item_id = ""
        for index, program in enumerate(self.filtered_programs, 1):
            item_id = f"program-{index - 1}"
            tag = "odd" if index % 2 == 1 else "even"
            self.program_tree.insert(
                "",
                "end",
                iid=item_id,
                tags=(tag,),
                values=(index, program.get("display_date", "----"), program.get("display_title", program["title"])),
            )
            self.program_tree_programs[item_id] = program
            if current_key is not None and self._program_key(program) == current_key:
                selected_item_id = item_id
        if self.filtered_programs:
            self._select_program_item(selected_item_id or "program-0")
            self._on_program_select()
        else:
            self._clear_program_selection()
        self._update_fetch_button_state()

    def run(self) -> tuple[dict, list[dict]] | tuple[None, None]:
        self.root.mainloop()
        return self.result

    def _selected_program(self) -> dict | None:
        selection = self.program_tree.selection()
        if not selection:
            return None
        return self.program_tree_programs.get(selection[0])

    def _select_program_item(self, item_id: str):
        if item_id not in self.program_tree_programs:
            return
        self.program_tree.selection_set(item_id)
        self.program_tree.focus(item_id)
        self.program_tree.see(item_id)

    def _program_key(self, program: dict | None) -> tuple[str, str] | None:
        if program is None:
            return None
        return program["site_id"], program["corner_id"]

    def _normalized_search_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", _normalize_text(text))
        return re.sub(r"\s+", " ", normalized).casefold()

    def _program_search_target(self, program: dict) -> str:
        return self._normalized_search_text(
            " ".join(
                part
                for part in (
                    program.get("display_title", ""),
                    program.get("title", ""),
                    program.get("corner_name", ""),
                    program.get("genre_label", ""),
                    program.get("genre", ""),
                )
                if part
            )
        )

    def _program_list_summary_text(self) -> str:
        total = len(self.programs)
        visible = len(self.filtered_programs)
        if self._normalized_search_text(self.program_search_var.get()):
            return f"{visible} / {total} 番組"
        return f"{total} 番組"

    def _program_search_history_values(self) -> list[str]:
        needle = self._normalized_search_text(self.program_search_var.get())
        if not needle:
            return list(self.program_search_history)
        return [term for term in self.program_search_history if needle in self._normalized_search_text(term)]

    def _update_program_search_history_values(self):
        if hasattr(self, "program_search_entry"):
            self.program_search_entry.configure(values=self._program_search_history_values())

    def _remember_program_search(self, raw_term: str) -> bool:
        term = _normalize_text(raw_term)
        if not term:
            return False

        key = self._normalized_search_text(term)
        history = [item for item in self.program_search_history if self._normalized_search_text(item) != key]
        history.insert(0, term)
        self.program_search_history = history[:SEARCH_HISTORY_LIMIT]
        self._update_program_search_history_values()
        self._persist_ui_settings()
        return True

    def _update_download_row_progress(
        self,
        episode_key: str,
        percent: float | None = None,
        eta: str | None = None,
        status_text: str | None = None,
    ):
        row = self.active_download_rows.get(episode_key)
        if row is None or row["state"] != "running":
            return

        if percent is not None:
            row["percent_var"].set(_format_download_percent(percent))
            row["progress"].stop()
            row["progress"].configure(mode="determinate", maximum=100, value=min(max(percent, 0.0), 100.0))
            row["progress_meta_var"].set(f"{row['percent_var'].get()} / {_format_download_eta(eta)}")
        elif eta is not None:
            row["progress_meta_var"].set(f"{row['percent_var'].get()} / {_format_download_eta(eta)}")

        if status_text is not None:
            row["status_var"].set(status_text)

    def _update_fetch_button_state(self):
        return

    def _clear_program_selection(self):
        self.program_tree.selection_remove(self.program_tree.selection())
        self.program_tree.focus("")
        self.displayed_program = None
        self.displayed_episodes = []
        self.displayed_episode_map.clear()
        for item_id in self.episode_tree.get_children():
            self.episode_tree.delete(item_id)
        self.episode_title_var.set("エピソード一覧")
        self.episode_message_var.set("一覧は未取得です。")
        self.download_button.state(["disabled"])
        self._schedule_saved_button_refresh()

        search_text = _normalize_text(self.program_search_var.get())
        self.program_list_summary_var.set(self._program_list_summary_text())
        if search_text:
            self.selected_program_title_var.set("一致する番組がありません")
            self.selected_program_meta_var.set(f"検索: {search_text}")
            self.selected_program_stats_var.set("検索条件を変更してください。")
        else:
            self.selected_program_title_var.set("番組を選択してください")
            self.selected_program_meta_var.set("左の番組一覧から選択すると、ここに番組の概要が表示されます。")
            self.selected_program_stats_var.set("エピソード一覧は未取得です。")

    def _on_program_search_change(self, *_args):
        needle = self._normalized_search_text(self.program_search_var.get())
        if needle:
            self.filtered_programs = [program for program in self.programs if needle in self._program_search_target(program)]
        else:
            self.filtered_programs = list(self.programs)
        self._update_program_search_history_values()
        self._populate_programs()

    def _clear_program_search(self, _event=None):
        self.program_search_var.set("")
        self.program_search_entry.focus_set()
        return "break"

    def _commit_program_search(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        return self._focus_program_tree_from_search()

    def _on_program_search_history_selected(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        return None

    def _on_program_search_focus_in(self, _event=None):
        self._update_program_search_history_values()
        return None

    def _on_program_search_focus_out(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        return None

    def _focus_program_tree_from_search(self, _event=None):
        if self.filtered_programs:
            self._remember_program_search(self.program_search_var.get())
            self.program_tree.focus_set()
            if not self.program_tree.selection():
                self._select_program_item("program-0")
                self._on_program_select()
        return "break"

    def _cached_episodes_for(self, program: dict) -> list[dict]:
        key = (program["site_id"], program["corner_id"])
        cached = self.episodes_cache.get(key)
        if cached is not None:
            cached_at, episodes = cached
            if time.time() - cached_at <= CACHE_TTL_SECONDS:
                return episodes
            self.episodes_cache.pop(key, None)

        disk_cached = _load_episode_cache(program)
        if disk_cached is None:
            return []
        self.episodes_cache[key] = (time.time(), disk_cached)
        return disk_cached

    def _update_program_overview(
        self,
        program: dict | None,
        episodes: list[dict] | None = None,
        message: str | None = None,
    ):
        if program is None:
            self.program_list_summary_var.set(self._program_list_summary_text())
            self.selected_program_title_var.set("番組を選択してください")
            self.selected_program_meta_var.set("左の番組一覧から選択すると、ここに番組の概要が表示されます。")
            self.selected_program_stats_var.set("エピソード一覧は未取得です。")
            return

        title = program.get("display_title", program["title"])
        genre_label = program.get("genre_label") or _genre_label(program.get("genre"))
        meta_parts = [genre_label, f"更新 {program.get('display_date', '----')}", f"ID {program['site_id']}_{program['corner_id']}"]
        corner_name = _normalize_text(program.get("corner_name", ""))
        if corner_name and corner_name != _normalize_text(program.get("title", "")):
            meta_parts.insert(1, corner_name)

        self.program_list_summary_var.set(f"{self._program_list_summary_text()} / 選択中: {genre_label}")
        self.selected_program_title_var.set(title)
        self.selected_program_meta_var.set(" / ".join(part for part in meta_parts if part))

        if episodes is None:
            stats = "エピソード一覧は未取得です。"
        else:
            downloaded_count = sum(1 for episode in episodes if is_episode_downloaded(self.output_dir, program, episode))
            stats = f"エピソード {len(episodes)} 件"
            if downloaded_count:
                stats += f" / 保存済み {downloaded_count} 件"
        if message:
            stats += f" / {message}"
        self.selected_program_stats_var.set(stats)

    def _on_program_select(self, _event=None):
        if self.fetch_result_queue is not None:
            return "break"

        program = self._selected_program()
        if program is None:
            return None

        self.status_var.set("")
        episodes = self._cached_episodes_for(program)
        if episodes:
            self._update_program_overview(program, episodes, "キャッシュ表示")
            self._show_episodes(program, episodes, message=f"キャッシュを表示中 ({len(episodes)} 件)")
        else:
            self._update_program_overview(program, None, "未取得")
            self._show_episodes(program, [], message="一覧は未取得です。ダブルクリックまたは「一覧を取得」で取得します。")
        return None

    def _on_program_double_click(self, event):
        if self.loading:
            return "break"

        item_id = self.program_tree.identify_row(event.y)
        if not item_id:
            return "break"

        self._select_program_item(item_id)
        self._on_program_select()
        self.root.after_idle(self._start_fetch_selected)
        return "break"

    def _tree_label(self, tree: ttk.Treeview) -> str:
        if tree is self.program_tree:
            return "番組一覧"
        if tree is self.episode_tree:
            return "エピソード一覧"
        return "一覧"

    def _tree_cell_from_event(self, tree: ttk.Treeview, event) -> tuple[str, str, str] | None:
        if tree.identify("region", event.x, event.y) != "cell":
            return None

        item_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not item_id or not column_id.startswith("#"):
            return None

        try:
            column_index = int(column_id[1:]) - 1
        except ValueError:
            return None

        values = tree.item(item_id, "values")
        if column_index < 0 or column_index >= len(values):
            return None
        return item_id, column_id, str(values[column_index])

    def _set_selected_tree_cell(self, tree: ttk.Treeview, column_id: str, value: str):
        try:
            column_index = int(column_id[1:]) - 1
        except ValueError:
            return

        columns = tree["columns"]
        if column_index < 0 or column_index >= len(columns):
            return

        heading = tree.heading(columns[column_index], "text") or columns[column_index]
        self.selected_cell_meta_var.set(f"{self._tree_label(tree)} / {heading}")
        self.selected_cell_value_var.set(value)
        self.selected_cell_entry.xview_moveto(0)
        if value:
            self.copy_cell_button.state(["!disabled"])
        else:
            self.copy_cell_button.state(["disabled"])

    def _on_program_tree_click(self, event):
        cell = self._tree_cell_from_event(self.program_tree, event)
        if cell is None:
            return None

        _item_id, column_id, value = cell
        self._set_selected_tree_cell(self.program_tree, column_id, value)
        return None

    def _show_episodes(self, program: dict, episodes: list[dict], message: str):
        self.displayed_program = program
        self.displayed_episodes = list(episodes)
        self.displayed_episode_map.clear()
        self.episode_title_var.set(f"エピソード一覧: {program.get('display_title', program['title'])}")
        self.episode_message_var.set(message)

        for item in self.episode_tree.get_children():
            self.episode_tree.delete(item)

        p = self._palette
        self.episode_tree.tag_configure("even",    background=p["surface"])
        self.episode_tree.tag_configure("odd",     background=p["row_odd"])
        self.episode_tree.tag_configure("dl_even", background=p["dl_even"])
        self.episode_tree.tag_configure("dl_odd",  background=p["dl_odd"])
        for index, episode in enumerate(episodes):
            iid = f"episode-{index}"
            self.displayed_episode_map[iid] = episode
            is_dl = is_episode_downloaded(self.output_dir, program, episode)
            saved = self._downloaded_cell_text(is_dl)
            date_time = episode.get("display_date", "----")
            btime = episode.get("broadcast_time", "")
            if btime:
                date_time = f"{date_time} {btime}"
            dur = episode.get("duration_str", "") or "----"
            if is_dl:
                tag = "dl_odd" if index % 2 == 1 else "dl_even"
            else:
                tag = "odd" if index % 2 == 1 else "even"
            self.episode_tree.insert(
                "",
                "end",
                iid=iid,
                tags=(tag,),
                values=(saved, date_time, dur, episode.get("display_title", episode["title"])),
            )

        if episodes:
            first = next(iter(self.displayed_episode_map))
            self.episode_tree.selection_set(first)
            self.episode_tree.focus(first)
            self.episode_tree.see(first)
            self.download_button.state(["!disabled"])
        else:
            self.download_button.state(["disabled"])
        self._schedule_saved_button_refresh()

    def _refresh_downloaded_column(self, program: dict):
        if self.displayed_program is None:
            return
        if (
            self.displayed_program["site_id"] != program["site_id"]
            or self.displayed_program["corner_id"] != program["corner_id"]
        ):
            return

        for iid, episode in self.displayed_episode_map.items():
            values = list(self.episode_tree.item(iid, "values"))
            if len(values) < 3:
                continue
            values[0] = self._downloaded_cell_text(is_episode_downloaded(self.output_dir, program, episode))
            self.episode_tree.item(iid, values=tuple(values))
        self._schedule_saved_button_refresh()
        self._update_program_overview(self.displayed_program, self.displayed_episodes, "保存状態を更新")

    def _downloaded_cell_text(self, downloaded: bool) -> str:
        return "済" if downloaded else "-"

    def _is_saved_item(self, item_id: str) -> bool:
        values = self.episode_tree.item(item_id, "values")
        return bool(values and values[0] == self._downloaded_cell_text(True))

    def _schedule_saved_button_refresh(self):
        if self.saved_button_refresh_pending:
            return
        self.saved_button_refresh_pending = True
        self.root.after_idle(self._refresh_saved_episode_buttons)

    def _refresh_saved_episode_buttons(self):
        self.saved_button_refresh_pending = False
        if not hasattr(self, "episode_tree") or not self.episode_tree.winfo_exists():
            return

        visible_saved_items: set[str] = set()
        for item_id in self.episode_tree.get_children():
            if item_id not in self.displayed_episode_map or not self._is_saved_item(item_id):
                continue

            bbox = self.episode_tree.bbox(item_id, column="#1")
            if not bbox:
                continue

            x, y, width, height = bbox
            button = self.saved_episode_buttons.get(item_id)
            if button is None or not button.winfo_exists():
                button = ttk.Button(
                    self.episode_tree,
                    text="済",
                    style="SavedCell.TButton",
                    cursor="hand2",
                    takefocus=False,
                    command=lambda iid=item_id: self._open_saved_episode_from_item(iid),
                )
                self.saved_episode_buttons[item_id] = button

            button_width = max(min(width - 12, 46), 34)
            button_height = max(min(height - 8, 24), 18)
            button.place(
                x=x + max((width - button_width) // 2, 0),
                y=y + max((height - button_height) // 2, 0),
                width=button_width,
                height=button_height,
            )
            button.lift()
            visible_saved_items.add(item_id)

        for item_id, button in list(self.saved_episode_buttons.items()):
            if item_id not in self.displayed_episode_map or not self._is_saved_item(item_id):
                button.destroy()
                del self.saved_episode_buttons[item_id]
                continue
            if item_id not in visible_saved_items:
                button.place_forget()

    def _on_episode_tree_scroll(self, *args):
        self.episode_tree.yview(*args)
        self._schedule_saved_button_refresh()

    def _on_episode_tree_yscroll(self, first: str, last: str):
        self.episode_scroll.set(first, last)
        self._schedule_saved_button_refresh()

    def _on_episode_tree_configure(self, _event):
        self._schedule_saved_button_refresh()

    def _is_saved_cell_clickable(self, event) -> bool:
        if self.displayed_program is None:
            return False
        region = self.episode_tree.identify("region", event.x, event.y)
        if region != "cell":
            return False
        if self.episode_tree.identify_column(event.x) != "#1":
            return False

        item_id = self.episode_tree.identify_row(event.y)
        if not item_id or item_id not in self.displayed_episode_map:
            return False

        return self._is_saved_item(item_id)

    def _on_episode_tree_motion(self, event):
        self.episode_tree.configure(cursor="hand2" if self._is_saved_cell_clickable(event) else "")

    def _on_episode_tree_leave(self, _event):
        self.episode_tree.configure(cursor="")

    def _on_episode_tree_click(self, event):
        cell = self._tree_cell_from_event(self.episode_tree, event)
        if cell is not None:
            _item_id, column_id, value = cell
            self._set_selected_tree_cell(self.episode_tree, column_id, value)

        if self.displayed_program is None or not self._is_saved_cell_clickable(event):
            return None
        item_id = self.episode_tree.identify_row(event.y)
        return self._open_saved_episode_from_item(item_id)

    def _open_saved_episode_from_item(self, item_id: str):
        if self.displayed_program is None or item_id not in self.displayed_episode_map:
            return None
        self._set_selected_tree_cell(self.episode_tree, "#1", self._downloaded_cell_text(True))
        episode = self.displayed_episode_map[item_id]
        path = resolve_episode_downloaded_path(self.output_dir, self.displayed_program, episode)
        if path is None:
            self.status_var.set("保存済みファイルの実体が見つかりません。")
            return "break"

        self._show_saved_episode_popup(path, episode)
        return "break"

    def _show_saved_episode_popup(self, path: Path, episode: dict):
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.destroy()

        popup = tk.Toplevel(self.root)
        popup.title("保存済みファイル")
        popup.geometry("760x260")
        popup.minsize(560, 220)
        popup.transient(self.root)
        popup.resizable(True, False)
        popup.configure(background=self._palette["surface"])

        main = ttk.Frame(popup, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="保存済みファイル", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=episode.get("display_title", episode["title"]),
            style="PopupTitle.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        body = ttk.Frame(main, padding=(0, 14, 0, 0))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="ファイル名", style="PopupLabel.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 12))
        ttk.Label(body, text=path.name, style="PopupValue.TLabel", wraplength=560, justify="left").grid(row=0, column=1, sticky="w")

        ttk.Label(body, text="保存先PATH", style="PopupLabel.TLabel").grid(row=1, column=0, sticky="nw", padx=(0, 12), pady=(12, 0))
        path_var = tk.StringVar(value=str(path))
        path_entry = ttk.Entry(body, textvariable=path_var)
        path_entry.grid(row=1, column=1, sticky="ew", pady=(12, 0))
        path_entry.state(["readonly"])

        ttk.Label(body, text="保存先フォルダ", style="PopupLabel.TLabel").grid(row=2, column=0, sticky="nw", padx=(0, 12), pady=(12, 0))
        ttk.Label(body, text=str(path.parent), style="PopupValue.TLabel", wraplength=560, justify="left").grid(
            row=2, column=1, sticky="w", pady=(12, 0)
        )

        ttk.Separator(main, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=(16, 12))
        buttons = ttk.Frame(main)
        buttons.grid(row=3, column=0, sticky="e")
        ttk.Button(buttons, text="PATHのコピー", command=lambda: self._copy_path_to_clipboard(path)).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="フォルダオープン", command=lambda: self._open_saved_folder(path)).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="閉じる", command=popup.destroy).grid(row=0, column=2)

        popup.bind("<Escape>", lambda _event: popup.destroy())
        popup.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        popup_w = popup.winfo_width()
        popup_h = popup.winfo_height()
        popup.geometry(f"+{root_x + max((root_w - popup_w) // 2, 0)}+{root_y + max((root_h - popup_h) // 2, 0)}")
        popup.lift()
        popup.focus_force()
        self.saved_episode_popup = popup

    def _copy_path_to_clipboard(self, path: Path):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(path))
        self.root.update_idletasks()
        self.status_var.set("PATH をクリップボードにコピーしました。")

    def _copy_selected_cell_to_clipboard(self, _event=None):
        value = self.selected_cell_value_var.get()
        if not value:
            self.status_var.set("コピーするセルをクリックしてください。")
            return "break"

        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()
        self.status_var.set("セル値をクリップボードにコピーしました。")
        return "break"

    def _open_saved_folder(self, path: Path):
        target_dir = path.parent
        if not target_dir.exists():
            self.status_var.set("保存先フォルダが見つかりません。")
            return

        if sys.platform == "darwin":
            cmd = ["open", str(target_dir)]
        elif sys.platform.startswith("win"):
            cmd = ["cmd", "/c", "start", "", str(target_dir)]
        else:
            cmd = ["xdg-open", str(target_dir)]

        subprocess.Popen(cmd)
        self.status_var.set(f"フォルダを開きました: {target_dir}")

    def _set_loading(self, loading: bool, allow_cancel: bool = False):
        self.loading = loading
        if loading:
            self.clear_button.state(["disabled"])
            self.program_search_entry.state(["disabled"])
        else:
            self.clear_button.state(["!disabled"])
            self.program_search_entry.state(["!disabled"])
            self._update_fetch_button_state()
        if not self.displayed_episode_map or loading:
            self.download_button.state(["disabled"])
        else:
            self.download_button.state(["!disabled"])
        self.root.configure(cursor="watch" if loading else "")
        self.root.update_idletasks()

    def _set_progress(self, current: int, total: int, text: str = ""):
        total = max(total, 1)
        self.progress.configure(maximum=total)
        self.progress_var.set(current)
        self.progress_text_var.set(text)

    def _show_progress_window(self):
        self.download_jobs_canvas.focus_set()
        self.status_var.set("下部のダウンロード状況を確認してください。")

    def _hide_progress_window(self):
        return

    def _on_download_jobs_inner_configure(self, _event=None):
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))

    def _on_download_jobs_canvas_configure(self, event):
        self.download_jobs_canvas.itemconfigure(self.download_jobs_window, width=event.width)
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))

    def _on_download_jobs_mousewheel(self, event):
        if not self.active_download_rows:
            return "break"

        if hasattr(event, "delta") and event.delta:
            step = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            return None

        self.download_jobs_canvas.yview_scroll(step, "units")
        return "break"

    def _reflow_download_rows(self):
        for row_index, row in enumerate(self.active_download_rows.values()):
            row["frame"].grid_configure(row=row_index)
        if self.active_download_rows:
            self.download_jobs_empty.grid_remove()
        else:
            self.download_jobs_empty.grid(row=0, column=0, sticky="w")
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))

    def _remove_download_row(self, episode_key: str):
        row = self.active_download_rows.get(episode_key)
        if row is None or row["state"] == "running":
            return
        row["frame"].destroy()
        self.active_download_rows.pop(episode_key, None)
        self.active_download_meta.pop(episode_key, None)
        self.download_cancel_events.pop(episode_key, None)
        self._reflow_download_rows()
        self._update_download_summary()

    def _update_download_summary(self):
        active = 0
        for row in self.active_download_rows.values():
            if row["state"] == "running":
                active += 1

        if active:
            total = max(self.download_started_count, 1)
            self._set_progress(
                self.download_finished_count,
                total,
                f"実行中 {active} 件 / 処理済 {self.download_finished_count} 件 / 開始 {self.download_started_count} 件",
            )
        elif self.download_started_count:
            self._set_progress(
                self.download_finished_count,
                max(self.download_started_count, 1),
                f"処理済: {self.download_finished_count} 件 / 開始 {self.download_started_count} 件",
            )
        else:
            self._set_progress(0, 1, "")

        if not self.active_download_rows and not self.loading:
            if self.displayed_episode_map:
                self.download_button.state(["!disabled"])
            else:
                self.download_button.state(["disabled"])

    def _add_download_row(self, program: dict, episode: dict):
        episode_key = _episode_key(episode)
        if episode_key in self.active_download_rows:
            return episode_key

        self._show_progress_window()
        self.download_jobs_empty.grid_remove()
        row_index = len(self.active_download_rows)
        frame = ttk.Frame(self.download_jobs_inner, style="CardInner.TFrame")
        frame.grid(row=row_index, column=0, sticky="ew", pady=2)
        frame.columnconfigure(0, weight=1)

        title = ttk.Label(frame, text=episode.get("display_title", episode["title"]), anchor="w")
        title.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        status_var = tk.StringVar(value="待機中...")
        status_label = ttk.Label(frame, textvariable=status_var, width=12, anchor="w")
        status_label.grid(row=0, column=1, sticky="w", padx=(0, 8))
        action_button = ttk.Button(frame, text="中断", command=lambda key=episode_key: self._cancel_download_job(key))
        action_button.grid(row=0, column=2, rowspan=2, sticky="ne")
        progress = ttk.Progressbar(frame, orient="horizontal", mode="indeterminate")
        progress.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        percent_var = tk.StringVar(value="--%")
        progress_meta_var = tk.StringVar(value=f"{percent_var.get()} / {_format_download_eta(None)}")
        progress_meta_label = ttk.Label(frame, textvariable=progress_meta_var, width=18, anchor="w")
        progress_meta_label.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(4, 0))
        progress.start(12)
        status_var.set("ダウンロード中...")

        self.active_download_rows[episode_key] = {
            "frame": frame,
            "progress": progress,
            "percent_var": percent_var,
            "progress_meta_var": progress_meta_var,
            "status_var": status_var,
            "action_button": action_button,
            "state": "running",
        }
        self.active_download_meta[episode_key] = (program, episode)
        self.download_started_count += 1
        self._update_download_summary()
        self.download_jobs_canvas.update_idletasks()
        self.download_jobs_canvas.yview_moveto(1.0)
        return episode_key

    def _finish_download_row(self, episode_key: str, status_text: str):
        row = self.active_download_rows.get(episode_key)
        if row is None:
            return
        if row["state"] != "running":
            return

        row["state"] = "done"
        row["progress"].stop()
        row["progress"].configure(mode="determinate", maximum=1, value=1)
        if status_text == "完了":
            row["percent_var"].set("100%")
            row["progress_meta_var"].set("100% / 残り 00:00")
        else:
            row["progress_meta_var"].set(f"{row['percent_var'].get()} / {_format_download_eta(None)}")
        row["status_var"].set(status_text)
        row["action_button"].configure(text="削除", command=lambda key=episode_key: self._remove_download_row(key))
        self.download_finished_count += 1
        self._update_download_summary()

    def _cancel_download_job(self, episode_key: str):
        cancel_event = self.download_cancel_events.get(episode_key)
        if cancel_event is None:
            return

        row = self.active_download_rows.get(episode_key)
        if row is not None and row["state"] == "running":
            row["status_var"].set("中断中...")

        cancel_event.set()
        with self.download_process_lock:
            process = self.download_processes.get(episode_key)
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass

    def _start_fetch_selected(self, _event=None):
        if self.loading:
            return "break"

        program = self._selected_program()
        if program is None:
            return "break"

        title = program.get("display_title", program["title"])
        self.status_var.set(f"「{title}」のエピソード一覧を取得中...")
        self.episode_message_var.set("取得中...")
        self._update_program_overview(program, None, "取得中")
        self._set_progress(0, 1, "")
        self._set_loading(True, allow_cancel=False)
        self.fetch_result_queue = queue.Queue()
        worker = threading.Thread(target=self._fetch_worker, args=(program, self.fetch_result_queue), daemon=True)
        worker.start()
        self.root.after(50, self._poll_fetch_result)
        return "break"

    def _fetch_worker(self, program: dict, result_queue: queue.Queue):
        try:
            episodes, source = refresh_episode_list(program)
            error = None
        except Exception as e:
            episodes = []
            source = ""
            error = str(e)
        result_queue.put((program, episodes, source, error))

    def _poll_fetch_result(self):
        if self.fetch_result_queue is None:
            return

        try:
            program, episodes, source, error = self.fetch_result_queue.get_nowait()
        except queue.Empty:
            if self.loading:
                self.root.after(50, self._poll_fetch_result)
            return

        self.fetch_result_queue = None
        self._finish_fetch(program, episodes, source, error)

    def _finish_fetch(self, program: dict, episodes: list[dict], source: str, error: str | None):
        self._set_loading(False)
        self._set_progress(0, 1, "")
        key = (program["site_id"], program["corner_id"])
        if error is not None:
            self.episodes_cache[key] = (time.time(), [])
            self.status_var.set(f"取得失敗: {error}")
            fallback = self._cached_episodes_for(program)
            if fallback:
                self._update_program_overview(program, fallback, "キャッシュ表示")
                self._show_episodes(program, fallback, message=f"最新取得に失敗したためキャッシュを表示中 ({len(fallback)} 件)")
            else:
                self._update_program_overview(program, None, "取得失敗")
                self._show_episodes(program, [], message="一覧は未取得です。取得に失敗しました。")
            return

        self.episodes_cache[key] = (time.time(), episodes)
        source_label = {"stale-cache": "期限切れキャッシュ"}.get(source, "最新取得")
        self.status_var.set("")
        self._update_program_overview(program, episodes, source_label)
        self._show_episodes(program, episodes, message=f"{source_label}で {len(episodes)} 件を表示中")
        if episodes:
            self.episode_tree.focus_set()

    def _clear_cache(self):
        if self.loading:
            return
        removed = clear_episode_cache()
        removed += clear_program_cache()
        self.episodes_cache.clear()
        self.status_var.set(f"キャッシュを削除しました ({removed} 件)")
        self._on_program_select()

    def _start_download_selected(self, _event=None):
        if self.loading:
            return "break"
        if self.displayed_program is None:
            self.status_var.set("番組を選択してください。")
            return "break"

        selected = [
            self.displayed_episode_map[iid]
            for iid in self.episode_tree.selection()
            if iid in self.displayed_episode_map
        ]
        if not selected:
            self.status_var.set("下段でダウンロード対象を選択してください。")
            return "break"

        program = self.displayed_program
        new_jobs = []
        duplicate_count = 0
        for episode in selected:
            episode_key = _episode_key(episode)
            if episode_key in self.active_download_rows and self.active_download_rows[episode_key]["state"] == "running":
                duplicate_count += 1
                continue
            self.download_cancel_events[episode_key] = threading.Event()
            self._add_download_row(program, episode)
            new_jobs.append((episode_key, episode))

        if not new_jobs:
            self.status_var.set("選択したエピソードはすでにダウンロード中です。")
            return "break"

        started = len(new_jobs)
        self.status_var.set(f"「{program.get('display_title', program['title'])}」のダウンロードを開始しました。")
        self.episode_message_var.set(f"開始 {started} 件" + (f" / 既に実行中 {duplicate_count} 件" if duplicate_count else ""))
        for episode_key, episode in new_jobs:
            worker = threading.Thread(
                target=self._download_one_worker,
                args=(program, episode, episode_key, self.download_cancel_events[episode_key]),
                daemon=True,
            )
            worker.start()

        if not self.download_polling:
            self.download_polling = True
            self.root.after(100, self._poll_download_result)
        return "break"

    def _download_one_worker(
        self,
        program: dict,
        episode: dict,
        episode_key: str,
        cancel_event: threading.Event,
    ):
        output_dir = _program_output_dir(self.output_dir, program)
        filename_template = _program_filename_template(program)
        if cancel_event.is_set():
            self.download_result_queue.put(("canceled_one", episode_key, program, episode))
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        process_output_queue: queue.Queue[str | None] = queue.Queue()
        process = subprocess.Popen(
            _download_episode_command(episode["url"], output_dir, filename_template, audio_only=True),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with self.download_process_lock:
            self.download_processes[episode_key] = process

        def _read_download_output():
            if process.stdout is None:
                process_output_queue.put(None)
                return
            try:
                for line in process.stdout:
                    process_output_queue.put(line)
            finally:
                process.stdout.close()
                process_output_queue.put(None)

        threading.Thread(target=_read_download_output, daemon=True).start()
        success = False
        canceled = False
        output_closed = False
        last_progress: tuple[str, str, str] | None = None
        try:
            while True:
                if cancel_event.is_set():
                    canceled = True
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    cleanup_partial_episode_files(self.output_dir, program, episode)
                    break

                try:
                    line = process_output_queue.get(timeout=0.1)
                except queue.Empty:
                    line = None
                else:
                    if line is None:
                        output_closed = True
                    else:
                        percent, eta, status_text = _parse_yt_dlp_progress(line)
                        if percent is not None or eta is not None or status_text is not None:
                            progress_event = (
                                _format_download_percent(percent),
                                _format_download_eta(eta),
                                status_text or "",
                            )
                            if progress_event != last_progress:
                                self.download_result_queue.put(("progress_one", episode_key, percent, eta, status_text))
                                last_progress = progress_event

                returncode = process.poll()
                if returncode is not None and output_closed:
                    success = returncode == 0
                    break
        finally:
            with self.download_process_lock:
                self.download_processes.pop(episode_key, None)

        if canceled:
            self.download_result_queue.put(("canceled_one", episode_key, program, episode))
            return

        if success:
            downloaded_path = resolve_episode_downloaded_path(self.output_dir, program, episode)
            mark_episode_downloaded(self.output_dir, program, episode, downloaded_path)
            self.download_result_queue.put(("done_one", episode_key, program, episode))
        else:
            self.download_result_queue.put(("failed_one", episode_key, program, episode))

    def _poll_download_result(self):
        if not self.download_polling:
            return

        processed = False
        while True:
            try:
                event = self.download_result_queue.get_nowait()
            except queue.Empty:
                break

            processed = True
            kind = event[0]
            if kind == "progress_one":
                _, episode_key, percent, eta, status_text = event
                self._update_download_row_progress(episode_key, percent=percent, eta=eta, status_text=status_text)
                continue
            if kind == "done_one":
                _, episode_key, program, episode = event
                self._finish_download_row(episode_key, "完了")
                self.status_var.set(f"ダウンロード完了: {episode.get('display_title', episode['title'])}")
                self.episode_message_var.set(f"保存先: {_program_output_dir(self.output_dir, program)}")
                if (
                    self.displayed_program is not None
                    and self.displayed_program["site_id"] == program["site_id"]
                    and self.displayed_program["corner_id"] == program["corner_id"]
                ):
                    self._refresh_downloaded_column(program)
            elif kind == "failed_one":
                _, episode_key, program, episode = event
                self._finish_download_row(episode_key, "失敗")
                self.status_var.set(f"ダウンロード失敗: {episode.get('display_title', episode['title'])}")
                self.episode_message_var.set(f"保存先: {_program_output_dir(self.output_dir, program)}")
            elif kind == "canceled_one":
                _, episode_key, program, episode = event
                self._finish_download_row(episode_key, "中断")
                self.status_var.set(f"ダウンロードを中断しました: {episode.get('display_title', episode['title'])}")
                self.episode_message_var.set("中断したエピソードの途中ファイルは削除しました。")

            self.download_cancel_events.pop(event[1], None)
            self.active_download_meta.pop(event[1], None)

        active_running = any(row["state"] == "running" for row in self.active_download_rows.values())
        if active_running:
            self.root.after(100, self._poll_download_result)
        else:
            self.download_polling = False

    def _cancel(self):
        has_running_download = any(row["state"] == "running" for row in self.active_download_rows.values())
        if self.loading or has_running_download:
            return
        self.result = (None, None)
        self.root.destroy()


class EpisodeBrowser:
    def __init__(self, stdscr, programs: list[dict]):
        self.stdscr = stdscr
        self.programs = programs
        self.program_index = 0
        self.program_top = 0
        self.focus = "programs"
        self.status = "上下キーで番組を選択、Enter で下段を取得"
        self.episodes_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
        self.episode_index: dict[tuple[str, str], int] = {}
        self.episode_top: dict[tuple[str, str], int] = {}
        self.selected_episode_ids: dict[tuple[str, str], set[str]] = {}
        self.active_program_key: tuple[str, str] | None = None

    def run(self) -> tuple[dict, list[dict]] | tuple[None, None]:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.keypad(True)

        while True:
            self._draw()
            key = self.stdscr.getch()

            if key in (ord("q"), 27):
                return None, None
            if key == 9:
                if self.focus == "programs":
                    if self.active_program_key is not None:
                        self.focus = "episodes"
                else:
                    self.focus = "programs"
                continue

            if self.focus == "programs":
                if key in (curses.KEY_UP, ord("k")):
                    self._move_program(-1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    self._move_program(1)
                elif key == curses.KEY_PPAGE:
                    self._move_program(-8)
                elif key == curses.KEY_NPAGE:
                    self._move_program(8)
                elif key in (curses.KEY_HOME, ord("g")):
                    self.program_index = 0
                elif key in (curses.KEY_END, ord("G")):
                    self.program_index = len(self.programs) - 1
                elif key in (curses.KEY_ENTER, 10, 13):
                    self._activate_current_program()
                elif key == curses.KEY_RIGHT and self.active_program_key is not None:
                    self.focus = "episodes"
                elif key == ord("C"):
                    self._clear_cache_and_reload()
            else:
                if key in (curses.KEY_LEFT, ord("h")):
                    self.focus = "programs"
                elif key in (curses.KEY_UP, ord("k")):
                    self._move_episode(-1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    self._move_episode(1)
                elif key == curses.KEY_PPAGE:
                    self._move_episode(-8)
                elif key == curses.KEY_NPAGE:
                    self._move_episode(8)
                elif key == ord("a"):
                    self._toggle_all_episodes()
                elif key == ord(" "):
                    self._toggle_current_episode()
                elif key in (ord("d"), curses.KEY_ENTER, 10, 13):
                    selected = self._selected_episodes()
                    if selected:
                        return self.active_program, selected
                    self.status = "下段でダウンロード対象を選んでください"
                elif key == ord("C"):
                    self._clear_cache_and_reload()

    @property
    def current_program(self) -> dict:
        return self.programs[self.program_index]

    @property
    def current_key(self) -> tuple[str, str]:
        program = self.current_program
        return program["site_id"], program["corner_id"]

    @property
    def preview_program(self) -> dict:
        return self.current_program if self.focus == "programs" else (self.active_program or self.current_program)

    @property
    def preview_key(self) -> tuple[str, str]:
        program = self.preview_program
        return program["site_id"], program["corner_id"]

    @property
    def preview_episodes(self) -> list[dict]:
        key = self.preview_key
        cached = self.episodes_cache.get(key)
        if not cached:
            cached_episodes = _load_episode_cache(self.preview_program)
            if cached_episodes is None:
                return []
            self.episodes_cache[key] = (time.time(), cached_episodes)
            return cached_episodes
        cached_at, episodes = cached
        if time.time() - cached_at > CACHE_TTL_SECONDS:
            self.episodes_cache.pop(key, None)
            cached_episodes = _load_episode_cache(self.preview_program)
            if cached_episodes is None:
                return []
            self.episodes_cache[key] = (time.time(), cached_episodes)
            return cached_episodes
        return episodes

    @property
    def current_episodes(self) -> list[dict]:
        if self.active_program_key is None:
            return []
        cached = self.episodes_cache.get(self.active_program_key)
        if not cached:
            return []
        cached_at, episodes = cached
        if time.time() - cached_at > CACHE_TTL_SECONDS:
            self.episodes_cache.pop(self.active_program_key, None)
            return []
        return episodes

    @property
    def active_program(self) -> dict | None:
        if self.active_program_key is None:
            return None
        for program in self.programs:
            if (program["site_id"], program["corner_id"]) == self.active_program_key:
                return program
        return None

    def _load_current_program(self):
        key = self.current_key
        if self.active_program_key == key and self.current_episodes:
            return

        title = self.current_program.get("display_title") or self.current_program["title"]
        self.status = f"「{title}」のエピソードを取得中..."
        try:
            curses.curs_set(2)
        except curses.error:
            pass
        self._draw()
        try:
            episodes, source = get_episode_list(self.current_program)
            self.episodes_cache[key] = (time.time(), episodes)
        except Exception as e:
            self.episodes_cache[key] = (time.time(), [])
            self.status = f"取得失敗: {e}"
            source = ""
        finally:
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        self.episode_index.setdefault(key, 0)
        self.episode_top.setdefault(key, 0)
        self.selected_episode_ids.setdefault(key, set())
        self.active_program_key = key

        episodes = self.current_episodes
        if episodes:
            source_label = {
                "cache": "キャッシュ",
                "stale-cache": "期限切れキャッシュ",
            }.get(source, "最新取得")
            self.status = f"{len(episodes)} 件のエピソードを表示中 ({source_label})"
        elif not self.status.startswith("取得失敗:"):
            self.status = "エピソードが見つかりませんでした"

    def _activate_current_program(self):
        self._load_current_program()
        self.focus = "episodes"

    def _move_program(self, delta: int):
        new_index = min(max(self.program_index + delta, 0), len(self.programs) - 1)
        if new_index == self.program_index:
            return
        self.program_index = new_index
        title = self.current_program.get("display_title") or self.current_program["title"]
        if self.preview_episodes:
            self.status = f"「{title}」のキャッシュを表示中。Enter で最新一覧を取得"
        else:
            self.status = f"「{title}」の一覧は未取得です。Enter で下段を取得"

    def _move_episode(self, delta: int):
        episodes = self.current_episodes
        if not episodes:
            return
        key = self.active_program_key
        if key is None:
            return
        current = self.episode_index.get(key, 0)
        self.episode_index[key] = min(max(current + delta, 0), len(episodes) - 1)

    def _toggle_current_episode(self):
        episodes = self.current_episodes
        if not episodes:
            return
        key = self.active_program_key
        if key is None:
            return
        current = episodes[self.episode_index.get(key, 0)]
        selected = self.selected_episode_ids.setdefault(key, set())
        if current["id"] in selected:
            selected.remove(current["id"])
        else:
            selected.add(current["id"])

    def _toggle_all_episodes(self):
        episodes = self.current_episodes
        if not episodes:
            return
        key = self.active_program_key
        if key is None:
            return
        selected = self.selected_episode_ids.setdefault(key, set())
        episode_ids = {ep["id"] for ep in episodes}
        if selected == episode_ids:
            selected.clear()
        else:
            selected.clear()
            selected.update(episode_ids)

    def _selected_episodes(self) -> list[dict]:
        episodes = self.current_episodes
        if not episodes:
            return []

        key = self.active_program_key
        if key is None:
            return []
        selected_ids = self.selected_episode_ids.get(key, set())
        if selected_ids:
            return [ep for ep in episodes if ep["id"] in selected_ids]

        return [episodes[self.episode_index.get(key, 0)]]

    def _clear_cache_and_reload(self):
        removed = clear_episode_cache()
        self.episodes_cache.clear()
        self.episode_index.clear()
        self.episode_top.clear()
        self.selected_episode_ids.clear()
        self.active_program_key = None
        self.status = f"キャッシュをクリアしました ({removed} 件)"
        self._activate_current_program()

    def _draw(self):
        self.stdscr.erase()
        height, width = self.stdscr.getmaxyx()

        if height < 12 or width < 70:
            _safe_addnstr(self.stdscr, 0, 0, "端末サイズが小さすぎます。70x12 以上に広げてください。", width)
            self.stdscr.refresh()
            return

        top_height = max(8, int(height * 0.58))
        bottom_y = top_height + 1
        bottom_height = height - bottom_y - 2
        if bottom_height < 4:
            bottom_height = 4

        self._draw_programs(0, 0, top_height, width)
        self._draw_episodes(bottom_y, 0, bottom_height, width)

        help_text = "q 終了  Enter 下段取得  Tab/←→ 切替  Space 選択  C キャッシュ削除  d/Enter DL"
        _safe_addnstr(self.stdscr, height - 2, 0, _fit_text(help_text, width), width)
        _safe_addnstr(self.stdscr, height - 1, 0, _fit_text(self.status, width), width, curses.A_DIM)
        self.stdscr.refresh()

    def _draw_programs(self, y: int, x: int, height: int, width: int):
        _safe_addnstr(self.stdscr, y, x, _fit_text("▼ 聞き逃しサービス", width), width, curses.A_BOLD)
        header_attr = curses.A_REVERSE if self.focus == "programs" else curses.A_BOLD
        _safe_addnstr(self.stdscr, y + 1, x, _fit_text("No.", 5), 5, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 6, _fit_text("放送日", 22), 22, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 29, _fit_text("番組", width - 29), width - 29, header_attr)

        visible = max(height - 3, 1)
        self.program_top = min(max(self.program_top, 0), max(len(self.programs) - visible, 0))
        if self.program_index < self.program_top:
            self.program_top = self.program_index
        elif self.program_index >= self.program_top + visible:
            self.program_top = self.program_index - visible + 1

        for row in range(visible):
            idx = self.program_top + row
            screen_y = y + 2 + row
            if idx >= len(self.programs):
                _safe_addnstr(self.stdscr, screen_y, x, " " * width, width)
                continue

            program = self.programs[idx]
            attr = curses.A_REVERSE if idx == self.program_index else curses.A_NORMAL
            number_text = _fit_text(str(idx + 1), 5)
            date_text = _fit_text(program.get("display_date", "----"), 22)
            title_text = _fit_text(program.get("display_title", program["title"]), width - 29)
            _safe_addnstr(self.stdscr, screen_y, x, number_text, 5, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 6, date_text, 22, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 29, title_text, width - 29, attr)

    def _draw_episodes(self, y: int, x: int, height: int, width: int):
        preview_program = self.preview_program
        title = preview_program.get("display_title") or preview_program["title"]
        header = f"▼ エピソード一覧: {title}"
        _safe_addnstr(self.stdscr, y, x, _fit_text(header, width), width, curses.A_BOLD)
        header_attr = curses.A_REVERSE if self.focus == "episodes" else curses.A_BOLD
        _safe_addnstr(self.stdscr, y + 1, x, _fit_text("選択", 6), 6, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 7, _fit_text("放送日時", 18), 18, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 26, _fit_text("長さ", 9), 9, header_attr)
        _safe_addnstr(self.stdscr, y + 1, x + 36, _fit_text("タイトル", width - 36), width - 36, header_attr)

        episodes = self.preview_episodes
        visible = max(height - 2, 1)
        key = self.preview_key
        if self.focus == "programs" and not episodes:
            _safe_addnstr(self.stdscr, y + 2, x, _fit_text("一覧は未取得です。上段で Enter を押すと取得します。", width), width)
            return
        if self.focus == "episodes" and self.active_program_key is None:
            _safe_addnstr(self.stdscr, y + 2, x, _fit_text("一覧は未取得です。上段で Enter を押すと取得します。", width), width)
            return
        self.episode_top[key] = min(max(self.episode_top.get(key, 0), 0), max(len(episodes) - visible, 0))
        current_idx = self.episode_index.get(key, 0)
        if current_idx < self.episode_top[key]:
            self.episode_top[key] = current_idx
        elif current_idx >= self.episode_top[key] + visible:
            self.episode_top[key] = current_idx - visible + 1

        if not episodes:
            _safe_addnstr(self.stdscr, y + 2, x, _fit_text("利用可能なエピソードがありません。", width), width)
            return

        selected_ids = self.selected_episode_ids.get(key, set())
        for row in range(visible):
            idx = self.episode_top[key] + row
            screen_y = y + 2 + row
            if idx >= len(episodes):
                _safe_addnstr(self.stdscr, screen_y, x, " " * width, width)
                continue

            episode = episodes[idx]
            marker = "[x]" if episode["id"] in selected_ids else "[ ]"
            attr = curses.A_REVERSE if idx == current_idx else curses.A_NORMAL
            date_time = episode.get("display_date", "----")
            btime = episode.get("broadcast_time", "")
            if btime:
                date_time = f"{date_time} {btime}"
            dur = episode.get("duration_str", "")
            dur_text = f"[{dur}]" if dur else "---------"
            _safe_addnstr(self.stdscr, screen_y, x, _fit_text(marker, 6), 6, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 7, _fit_text(date_time, 18), 18, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 26, _fit_text(dur_text, 9), 9, attr)
            _safe_addnstr(self.stdscr, screen_y, x + 36, _fit_text(episode.get("display_title", episode["title"]), width - 36), width - 36, attr)


def browse_programs(programs: list[dict], output_dir: Path) -> tuple[dict, list[dict]] | tuple[None, None]:
    try:
        return EpisodeGuiBrowser(programs, output_dir).run()
    except tk.TclError as e:
        raise RuntimeError(str(e)) from e


# ──────────────────────────────────────────────────────
# 対話型選択 UI
# ──────────────────────────────────────────────────────

def select_program(programs: list[dict]) -> dict | None:
    """番組一覧を表示してユーザーに選択させる"""
    print()
    print("=" * 70)
    print(f"  NHK ラジオ 聞き逃し番組一覧  ({len(programs)} 番組)")
    print("=" * 70)
    for i, p in enumerate(programs, 1):
        date = p.get("display_date", "----")
        title = p.get("display_title", p["title"])
        print(f"  {i:3}. [{date}] {title}")
    print("=" * 70)
    print("  0. キャンセル / URL を直接入力: u")
    print()

    while True:
        try:
            raw = input("番号を入力してください: ").strip()
            if raw == "0":
                return None
            if raw.lower() == "u":
                url = input("番組 URL を入力してください: ").strip()
                return _url_to_program(url)
            n = int(raw)
            if 1 <= n <= len(programs):
                return programs[n - 1]
            print(f"  1〜{len(programs)} または 0 / u を入力してください。")
        except (ValueError, EOFError):
            print("  数字を入力してください。")


def _url_to_program(url: str) -> dict | None:
    """URL から番組辞書を生成する"""
    m = re.search(r'[?&]p=([\da-zA-Z]+)_([\da-zA-Z]+)', url)
    if not m:
        print(f"  URL の形式が正しくありません: {url}")
        return None
    site_id, corner_id = m.group(1), m.group(2)
    return {
        "title":     f"{site_id}_{corner_id}",
        "display_title": f"{site_id}_{corner_id}",
        "display_date": "----",
        "genre": None,
        "genre_label": _genre_label(None),
        "site_id":   site_id,
        "corner_id": corner_id,
        "url":       NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
    }


def select_episodes(episodes: list[dict]) -> list[dict] | None:
    """エピソード一覧を表示して選択させる"""
    if not episodes:
        print("  利用可能なエピソードがありません。")
        return None

    print()
    print("-" * 70)
    for i, ep in enumerate(episodes, 1):
        date_text = ep.get("display_date", ep["date"][:10] if ep["date"] else "----")
        btime = ep.get("broadcast_time", "")
        dur = ep.get("duration_str", "")
        meta = date_text
        if btime:
            meta = f"{meta} {btime}"
        if dur:
            meta = f"{meta} [{dur}]"
        print(f"  {i:3}. [{meta}] {ep['title']}")
    print("-" * 70)
    print(f"  a. 全件 ({len(episodes)} 件)")
    print("  0. 戻る")
    print()

    while True:
        try:
            raw = input("番号を入力 (複数はカンマ区切り, 例: 1,3,5): ").strip()
            if raw == "0":
                return None
            if raw.lower() == "a":
                return episodes
            selected = []
            valid = True
            for part in raw.split(","):
                n = int(part.strip())
                if 1 <= n <= len(episodes):
                    selected.append(episodes[n - 1])
                else:
                    print(f"  {n} は範囲外です (1〜{len(episodes)})。")
                    valid = False
                    break
            if valid and selected:
                return selected
        except (ValueError, EOFError):
            print("  数字を入力してください。")


# ──────────────────────────────────────────────────────
# ダウンロード
# ──────────────────────────────────────────────────────

def download_episode(url: str, output_dir: Path, filename_template: str, verbose: bool = True) -> bool:
    """yt-dlp で1エピソードを mp3 でダウンロードする"""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = _download_episode_command(url, output_dir, filename_template, audio_only=True)
    if verbose:
        print(f"  → {url}")
    return subprocess.run(cmd).returncode == 0


def download_url_direct(
    url: str,
    output_dir: Path,
    max_items: int | None,
    audio_only: bool,
    genre: str | None = None,
):
    """URL を直接指定してダウンロードする (非対話モード)"""
    program = _resolve_program_from_url(url, genre=genre)
    if program is None:
        print(f"URL の形式が正しくありません: {url}")
        sys.exit(1)

    target_dir = _program_output_dir(output_dir, program)
    target_dir.mkdir(parents=True, exist_ok=True)

    tmpl = str(target_dir / _program_filename_template(program, max_items=bool(max_items)))

    cmd = ["yt-dlp", "-o", tmpl]
    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    if max_items:
        cmd += ["--playlist-end", str(max_items)]
    else:
        cmd += ["--no-playlist"]
    cmd.append(url)

    print(f"ダウンロード開始: {url}")
    print(f"保存先: {target_dir}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\nダウンロード完了!")
    else:
        print(f"\nエラー (終了コード: {result.returncode})")
        sys.exit(result.returncode)


# ──────────────────────────────────────────────────────
# 対話モード (メインフロー)
# ──────────────────────────────────────────────────────

def interactive_mode(output_dir: Path, genre: str | None = None):
    programs = fetch_program_list(genre)

    if not programs:
        print("番組が見つかりませんでした。")
        sys.exit(1)

    try:
        browse_programs(programs, output_dir)
    except RuntimeError as e:
        print(f"GUI を起動できませんでした: {e}")
        sys.exit(1)
    print("終了します。")


# ──────────────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NHK ラジオ 聞き逃し番組ダウンローダー (個人学習用)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方例:
  # 番組一覧から選択 (GUI 専用モード)
  python nhk_radio_dl.py
  # GUI 操作: 上段をクリックしてキャッシュ表示 / ダブルクリックで一覧取得 / 下段で複数選択してダウンロード

  # URL を直接指定してダウンロード
  python nhk_radio_dl.py "https://www.nhk.or.jp/radio/ondemand/detail.html?p=XXXX_01"

  # 直近5件をダウンロード
  python nhk_radio_dl.py <URL> -n 5

  # エピソード一覧キャッシュを削除
  python nhk_radio_dl.py --clear-cache

  # 保存先ディレクトリを指定
  python nhk_radio_dl.py -o ~/Downloads/nhk

  # 保存先は downloads/<ジャンル>/<番組名>/YYYYMMDD_<番組名>_<回タイトル>.mp3
        """,
    )
    parser.add_argument("url", nargs="?", help="番組 URL (省略すると GUI モード)")
    parser.add_argument("--output-dir", "-o", default="./downloads",
                        help="保存先ディレクトリ (デフォルト: ./downloads)")
    parser.add_argument("--max-items", "-n", type=int, default=None,
                        help="最大ダウンロード件数")
    parser.add_argument("--keep-video", action="store_true",
                        help="音声変換せず元ファイルを保持する")
    parser.add_argument("--clear-cache", action="store_true",
                        help="エピソード一覧キャッシュを削除して終了する")
    parser.add_argument(
        "--genre", "-g",
        choices=NHK_GENRES,
        default=None,
        metavar=f"{{{','.join(NHK_GENRES)}}}",
        help="番組ジャンルで絞り込む (省略すると全番組)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()

    if args.clear_cache:
        removed = clear_all_cache()
        print(f"キャッシュを削除しました: {removed} 件")
        return

    if args.url:
        download_url_direct(args.url, output_dir, args.max_items,
                            audio_only=not args.keep_video, genre=args.genre)
    else:
        interactive_mode(output_dir, genre=args.genre)


if __name__ == "__main__":
    main()

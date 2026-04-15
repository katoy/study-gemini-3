#!/usr/bin/env python3
"""
NHK ラジオ 聞き逃し番組ダウンローダー
個人学習目的専用 (著作権法第30条 私的使用のための複製)

使い方:
  python nhk_radio_dl.py          # 番組一覧から選択 (GUI 専用モード)
  python nhk_radio_dl.py <URL>    # URL を直接指定してダウンロード
  python nhk_radio_dl.py <URL> -n 5   # 直近5件のみダウンロード
"""

import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .cache import load_episode_cache, load_program_cache, save_episode_cache, save_program_cache
from .config import CACHE_TTL_SECONDS
from .constants import NHK_API_GENRE, NHK_API_NEW_CORNERS, NHK_API_SERIES, NHK_DETAIL_TMPL, NHK_EPISODE_TMPL, NHK_GENRES, _HEADERS
from .downloads import _episode_key
from .text import _format_broadcast_time, _format_duration, _format_onair_date, _genre_label, _normalize_text, _program_display_title


def http_get_json(url: str, timeout: int = 15) -> dict | list:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")

def fetch_program_list(genre: str | None = None) -> list[dict]:
    """
    NHK ラジオ聞き逃し番組一覧を API から取得する。

    genre=None  → 全番組 (corners/new_arrivals + 全ジャンル合算)
    genre=str   → 指定ジャンルのみ (例: "language", "music")

    Returns:
        [{"title": str, "site_id": str, "corner_id": str, "url": str}, ...]
    """
    cached = load_program_cache(genre)
    if cached is not None:
        return cached

    programs = _fetch_by_genre(genre) if genre else _fetch_all()
    if programs:
        save_program_cache(genre, programs)
        return programs

    stale = load_program_cache(genre, ttl_seconds=10**12)
    return stale or programs




# ──────────────────────────────────────────────────────
# API 番組取得ロジック
# ──────────────────────────────────────────────────────

def _url_to_program(url: str) -> dict | None:
    match = re.search(r"[?&]p=([\da-zA-Z]+)_([\da-zA-Z]+)", url)
    if not match:
        return None
    site_id, corner_id = match.group(1), match.group(2)
    return {
        "title": f"{site_id}_{corner_id}",
        "display_title": f"{site_id}_{corner_id}",
        "display_date": "----",
        "genre": None,
        "genre_label": _genre_label(None),
        "site_id": site_id,
        "corner_id": corner_id,
        "url": NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
    }


def _resolve_program_from_url(url: str, genre: str | None = None) -> dict | None:
    program = _url_to_program(url)
    if program is None:
        return None

    cached_programs = load_program_cache(genre)
    if cached_programs is None:
        cached_programs = load_program_cache(genre, ttl_seconds=10**12)

    for candidate in cached_programs or []:
        if (
            candidate["site_id"] == program["site_id"]
            and candidate["corner_id"] == program["corner_id"]
        ):
            return candidate
    if genre:
        program["genre"] = genre
        program["genre_label"] = _genre_label(genre)
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
        cached = load_episode_cache(program)
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
            save_episode_cache(program, episodes)
            return episodes, "network"
        except Exception as e:
            last_error = str(e)

        if attempt == 0:
            time.sleep(retry_delay)

    stale = load_episode_cache(program, ttl_seconds=10**12)
    if stale is not None:
        return stale, "stale-cache"

    raise RuntimeError(last_error or "エピソード一覧を取得できませんでした")

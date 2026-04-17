#!/usr/bin/env python3
"""
NHK ラジオ 聞き逃し番組ダウンローダー
個人学習目的専用 (著作権法第30条 私的使用のための複製)

使い方:
  python nhk_radio_dl.py          # 番組一覧から選択 (GUI 専用モード)
  python nhk_radio_dl.py <URL>    # URL を直接指定してダウンロード
  python nhk_radio_dl.py <URL> -n 5   # 直近5件のみダウンロード
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Sequence

import httpx
import yt_dlp

from .cache import load_episode_cache, load_program_cache, save_episode_cache, save_program_cache
from .constants import _HEADERS, NHK_API_GENRE, NHK_API_NEW_CORNERS, NHK_DETAIL_TMPL, NHK_GENRES
from .text import (
    _format_broadcast_time,
    _format_duration,
    _format_episode_date,
    _format_onair_date,
    _genre_label,
    _normalize_text,
    _program_display_title,
)
from .types import Episode, Program

logger = logging.getLogger(__name__)


async def http_get_json_async(client: httpx.AsyncClient, url: str, timeout: int = 15) -> dict | list:
    resp = await client.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def http_get_json(url: str, timeout: int = 15) -> dict | list:
    """Synchronous fallback using httpx"""
    with httpx.Client(headers=_HEADERS) as client:
        resp = client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


def http_get_text(url: str, timeout: int = 20) -> str:
    with httpx.Client(headers=_HEADERS) as client:
        resp = client.get(url, timeout=timeout)
        resp.raise_for_status()
        t = resp.text
        return t


def fetch_program_list(genre: str | None = None) -> list[Program]:
    """
    NHK ラジオ聞き逃し番組一覧を同期的に取得する。
    """
    return asyncio.run(fetch_program_list_async(genre))


async def fetch_program_list_async(genre: str | None = None) -> list[Program]:
    """
    NHK ラジオ聞き逃し番組一覧を非同期に取得する。
    """
    cached = load_program_cache(genre)
    if cached is not None:
        return cached

    programs = await _fetch_by_genre_async(genre) if genre else await _fetch_all_async()

    if programs:
        save_program_cache(genre, programs)
        return programs

    stale = load_program_cache(genre, ttl_seconds=10**12)
    return stale or programs


# ──────────────────────────────────────────────────────
# API 番組取得ロジック
# ──────────────────────────────────────────────────────


def _url_to_program(url: str) -> Program | None:
    match = re.search(r"[?&]p=([\da-zA-Z]+)_([\da-zA-Z]+)", url)
    if not match:
        return None
    site_id, corner_id = match.group(1), match.group(2)
    return Program(
        title=f"{site_id}_{corner_id}",
        display_title=f"{site_id}_{corner_id}",
        display_date="----",
        genre=None,
        genre_label=_genre_label(None),
        site_id=site_id,
        corner_id=corner_id,
        url=NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
    )


def _resolve_program_from_url(url: str, genre: str | None = None) -> Program | None:
    program = _url_to_program(url)
    if program is None:
        return None

    cached_programs = load_program_cache(genre)
    if cached_programs is None:
        cached_programs = load_program_cache(genre, ttl_seconds=10**12)

    for candidate in cached_programs or []:
        if candidate.site_id == program.site_id and candidate.corner_id == program.corner_id:
            return candidate
    if genre:
        from dataclasses import replace

        program = replace(program, genre=genre, genre_label=_genre_label(genre))
    return program


def _make_entry(s: dict, genre: str | None = None) -> Program:
    site_id = s.get("series_site_id") or s.get("site_id", "")
    corner_id = s.get("corner_site_id") or s.get("corner_id", "01")
    title = s.get("title") or s.get("corner_name") or f"{site_id}_{corner_id}"
    corner_name = s.get("corner_name", "")
    onair_date = s.get("onair_date", "")
    return Program(
        title=title,
        corner_name=corner_name,
        genre=genre,
        genre_label=_genre_label(genre),
        site_id=site_id,
        corner_id=corner_id,
        onair_date=onair_date,
        display_date=_format_onair_date(onair_date),
        display_title=_program_display_title(title, corner_name),
        started_at=s.get("started_at", ""),
        url=NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
    )


async def _fetch_all_async() -> list[Program]:
    """全ジャンルの番組を取得してまとめる (非同期・並列版)"""
    logger.info("番組一覧を取得中...")
    seen: set[tuple[str, str]] = set()
    programs: list[Program] = []
    program_map: dict[tuple[str, str], Program] = {}

    async with httpx.AsyncClient(headers=_HEADERS) as client:
        # 1) corners/new_arrivals (最新追加・最多)
        try:
            data = await http_get_json_async(client, NHK_API_NEW_CORNERS)
            if isinstance(data, dict):
                for s in data.get("corners", []):
                    key = (s.get("series_site_id"), s.get("corner_site_id"))
                    if key not in seen:
                        seen.add(key)
                        entry = _make_entry(s)
                        programs.append(entry)
                        program_map[key] = entry
        except Exception as e:
            logger.debug(f"最新追加の取得に失敗: {e}")

        # 2) 各ジャンルを追加 (並列取得して補完)
        async def fetch_genre(g: str) -> tuple[str, dict | list | None]:
            try:
                data = await http_get_json_async(client, NHK_API_GENRE.format(genre=g))
                return g, data
            except Exception as e:
                logger.debug(f"ジャンル {g} の取得に失敗: {e}")
                return g, None

        tasks = [fetch_genre(g) for g in NHK_GENRES]
        results = await asyncio.gather(*tasks)

        for g, data in results:
            if not isinstance(data, dict):
                continue
            for s in data.get("series", []):
                key = (s.get("series_site_id"), s.get("corner_site_id"))
                if key not in seen:
                    seen.add(key)
                    entry = _make_entry(s, genre=g)
                    programs.append(entry)
                    program_map[key] = entry
                else:
                    existing = program_map.get(key)
                    if existing is not None and not existing.genre:
                        from dataclasses import replace

                        new_entry = replace(existing, genre=g, genre_label=_genre_label(g))
                        try:
                            idx = programs.index(existing)
                            programs[idx] = new_entry
                            program_map[key] = new_entry
                        except ValueError:
                            pass

    if programs:
        logger.info(f"{len(programs)} 件の番組を取得しました。")
        return programs

    logger.warning("番組一覧の取得に失敗しました。フォールバックを使用します。")
    return _fallback_program_list()


async def _fetch_by_genre_async(genre: str) -> list[Program]:
    """指定ジャンルの番組一覧を取得する (非同期版)"""
    label = {
        "language": "語学",
        "music": "音楽",
        "news": "ニュース",
        "drama": "ドラマ",
        "sports": "スポーツ",
        "documentary": "ドキュメンタリー",
        "variety": "バラエティ",
    }.get(genre, genre)
    logger.info(f"{label}一覧を取得中...")
    try:
        async with httpx.AsyncClient(headers=_HEADERS) as client:
            data = await http_get_json_async(client, NHK_API_GENRE.format(genre=genre))
        if isinstance(data, dict):
            programs = [_make_entry(s, genre=genre) for s in data.get("series", [])]
            logger.info(f"{len(programs)} 件を取得しました。")
            return programs
        return []
    except Exception as e:
        logger.error(f"{label}一覧の取得に失敗: {e}")
        return _fallback_program_list() if genre == "language" else []


def _fallback_program_list() -> list[Program]:
    """
    API 取得失敗時のフォールバック。
    2026年4月時点の正確な ID。
    """
    entries = [
        ("ラジオ英会話", "PMMJ59J6N2", "01"),
        ("基礎英語 レベル2", "83RW6PK3GG", "01"),
        ("基礎英語 レベル1", "148W8XX226", "01"),
        ("小学生の基礎英語", "GGQY3M1929", "01"),
        ("エンジョイ・シンプル・イングリッシュ", "BR8Z3NX7XM", "01"),
        ("まいにちロシア語", "YRLK72JZ7Q", "01"),
        ("まいにちイタリア語", "LJWZP7XVMX", "01"),
        ("まいにちフランス語", "XQ487ZM61K", "01"),
        ("まいにちスペイン語", "NRZWXVGQ19", "01"),
        ("まいにちドイツ語", "N8PZRZ9WQY", "01"),
        ("まいにち中国語", "983PKQPYN7", "01"),
        ("まいにちハングル講座", "LR47WW9K14", "01"),
        ("ポルトガル語講座", "N13V9K157Y", "01"),
        ("英会話タイムトライアル", "8Z6XJ6J415", "01"),
        ("ニュースで学ぶ「現代英語」", "77RQWQX1L6", "01"),
        ("ラジオビジネス英語", "368315KKP8", "01"),
    ]
    return [
        Program(
            title=title,
            display_title=title,
            display_date="----",
            genre="language",
            genre_label=_genre_label("language"),
            site_id=site_id,
            corner_id=corner_id,
            url=NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
        )
        for title, site_id, corner_id in entries
    ]


# ──────────────────────────────────────────────────────
# エピソード取得 (yt-dlp 経由)
# ──────────────────────────────────────────────────────


def _parse_episode_info(info: dict, program: Program) -> Episode:
    """yt-dlp のエピソード情報を Episode クラスに変換する。"""
    ep_id = str(info.get("id", ""))
    title = info.get("title") or ep_id
    upload_date = info.get("upload_date") or ""
    timestamp = info.get("release_timestamp") or info.get("timestamp")
    duration = info.get("duration")
    date = upload_date or (str(int(timestamp)) if timestamp else "")
    if ep_id:
        ep_url = f"https://www.nhk.or.jp/radio/player/ondemand.html?p={ep_id}"
    else:
        ep_url = info.get("webpage_url") or info.get("url") or ""
    return Episode(
        id=ep_id,
        title=title,
        display_title=_normalize_text(title),
        date=date,
        display_date=_format_episode_date(upload_date or date),
        broadcast_time=_format_broadcast_time(timestamp),
        duration_str=_format_duration(duration),
        url=ep_url,
    )


def fetch_episodes(program: Program, verbose: bool = True) -> list[Episode]:
    """yt-dlp Python API を使って番組のエピソード一覧を取得する。"""
    if verbose:
        logger.info(f"「{program.title}」のエピソードを取得中...")

    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(program.url, download=False)
            if info is None:
                raise RuntimeError("番組情報の取得に失敗しました")

            entries = info.get("entries", [])
            episodes = [_parse_episode_info(entry, program) for entry in entries if entry]

            if verbose:
                logger.info(f"{len(episodes)} 件のエピソードを取得しました。")
            return episodes
    except Exception as e:
        logger.error(f"エピソード取得失敗: {e}")
        raise RuntimeError(str(e)) from e


def get_episode_list(
    program: Program,
    retry_delay: float = 1.0,
    use_cache: bool = True,
) -> tuple[list[Episode], str]:
    if use_cache:
        cached = load_episode_cache(program)
        if cached is not None:
            return cached, "cache"

    return refresh_episode_list(program, retry_delay=retry_delay)


def refresh_episode_list(
    program: Program,
    retry_delay: float = 1.0,
) -> tuple[list[Episode], str]:
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
    if stale:
        return stale, "stale-cache"

    raise RuntimeError(last_error or "エピソード一覧を取得できませんでした")

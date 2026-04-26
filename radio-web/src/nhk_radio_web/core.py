#!/usr/bin/env python3
"""
NHK ラジオ 聞き逃し番組ダウンローダー - コアロジック
個人学習目的専用 (著作権法第30条 私的使用のための複製)
"""

import asyncio
import logging
import re
import time
from typing import cast

import httpx
import yt_dlp

from .cache import load_episode_cache, load_program_cache, save_episode_cache, save_program_cache
from .constants import (
    _HEADERS,
    GENRE_LABELS,
    NHK_API_GENRE,
    NHK_API_NEW_CORNERS,
    NHK_DETAIL_TMPL,
    NHK_GENRES,
)
from .text import (
    _format_broadcast_time,
    _format_duration,
    _format_episode_date,
    _format_onair_date,
    _genre_label,
    _normalize_text,
    _program_display_title,
)
from .types import ApiProgramRaw, Episode, Program

logger = logging.getLogger(__name__)


async def http_get_json_async(client: httpx.AsyncClient, url: str, timeout: int = 60) -> dict | list:
    try:
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPエラー (ステータスコード: {e.response.status_code}): {url}")
        raise
    except httpx.RequestError as e:
        logger.error(f"ネットワークエラー: {e} ({url})")
        raise


def http_get_json(url: str, timeout: int = 60) -> dict | list:
    try:
        with httpx.Client(headers=_HEADERS) as client:
            resp = client.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTPエラー ({e.response.status_code}): {url}")
        raise
    except httpx.RequestError as e:
        logger.error(f"ネットワーク接続エラー: {e}")
        raise


def http_get_text(url: str, timeout: int = 60) -> str:
    try:
        with httpx.Client(headers=_HEADERS) as client:
            resp = client.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPError as e:
        logger.error(f"テキスト取得失敗: {e}")
        raise


def fetch_program_list(genre: str | None = None) -> list[Program]:
    return asyncio.run(fetch_program_list_async(genre))


async def fetch_program_list_async(genre: str | None = None) -> list[Program]:
    cached = load_program_cache(genre)
    if cached is not None:
        return cached

    programs = await _fetch_by_genre_async(genre) if genre else await _fetch_all_async()

    if programs:
        save_program_cache(genre, programs)
        return programs

    stale = load_program_cache(genre, ttl_seconds=10**12)
    return stale or programs


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


def _make_entry(s: ApiProgramRaw, genre: str | None = None) -> Program:
    site_id = str(s.get("series_site_id") or s.get("site_id") or "")
    corner_id = str(s.get("corner_site_id") or s.get("corner_id") or "01")
    title = str(s.get("title") or s.get("corner_name") or f"{site_id}_{corner_id}")
    corner_name = s.get("corner_name")
    onair_date = str(s.get("onair_date") or "")
    started_at = str(s.get("started_at") or "")

    return Program(
        title=title,
        corner_name=corner_name,
        genre=genre,
        genre_label=_genre_label(genre),
        site_id=site_id,
        corner_id=corner_id,
        onair_date=onair_date,
        display_date=_format_onair_date(onair_date, started_at),
        display_title=_program_display_title(title, corner_name),
        started_at=started_at,
        url=NHK_DETAIL_TMPL.format(site_id=site_id, corner_id=corner_id),
    )


async def _fetch_all_async() -> list[Program]:
    logger.info("番組一覧を取得中...")
    seen: set[tuple[str, str]] = set()
    programs: list[Program] = []
    program_map: dict[tuple[str, str], Program] = {}

    async with httpx.AsyncClient(headers=_HEADERS) as client:
        try:
            data = await http_get_json_async(client, NHK_API_NEW_CORNERS)
            if isinstance(data, dict):
                for s_raw in data.get("corners", []):
                    s = cast(ApiProgramRaw, s_raw)
                    key = (str(s.get("series_site_id", "")), str(s.get("corner_site_id", "")))
                    if key not in seen:
                        seen.add(key)
                        entry = _make_entry(s)
                        programs.append(entry)
                        program_map[key] = entry
        except (httpx.HTTPError, ValueError) as e:
            logger.debug(f"最新追加の取得に失敗 (スキップ): {e}")

        async def fetch_genre(g: str) -> tuple[str, dict | list | None]:
            try:
                data = await http_get_json_async(client, NHK_API_GENRE.format(genre=g))
                return g, data
            except (httpx.HTTPError, ValueError) as e:
                logger.debug(f"ジャンル {g} の取得に失敗 (スキップ): {e}")
                return g, None

        tasks = [fetch_genre(g) for g in NHK_GENRES]
        results = await asyncio.gather(*tasks)

        for g, data in results:
            if not isinstance(data, dict):
                continue
            for s_raw in data.get("series", []):
                s = cast(ApiProgramRaw, s_raw)
                key = (str(s.get("series_site_id", "")), str(s.get("corner_site_id", "")))
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
                        except ValueError:  # pragma: no cover
                            pass

    if programs:
        logger.info(f"{len(programs)} 件の番組を取得しました。")
        return programs

    logger.warning("番組一覧を取得できませんでした。ネットワーク状態を確認してください。")
    return []


async def _fetch_by_genre_async(genre: str) -> list[Program]:
    label = GENRE_LABELS.get(genre, genre)
    logger.info(f"{label}一覧を取得中...")
    try:
        async with httpx.AsyncClient(headers=_HEADERS) as client:
            data = await http_get_json_async(client, NHK_API_GENRE.format(genre=genre))
        if isinstance(data, dict):
            programs = [_make_entry(cast(ApiProgramRaw, s), genre=genre) for s in data.get("series", [])]
            logger.info(f"{len(programs)} 件を取得しました。")
            return programs
        return []
    except Exception as e:
        logger.error(f"{label}一覧の取得に失敗: {e}")
        return []


def _parse_episode_info(info: dict, program: Program) -> Episode:
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
    if verbose:
        logger.info(f"「{program.title}」のエピソードを取得中...")

    ydl_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 60,
        "retries": 5,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(program.url, download=False)
            if info is None:
                msg = "番組情報の取得に失敗しました。"
                logger.error(f"エピソード取得失敗: {msg}")
                raise RuntimeError(msg)

            entries = info.get("entries", [])
            episodes = [_parse_episode_info(entry, program) for entry in entries if entry]

            if verbose:
                logger.info(f"{len(episodes)} 件のエピソードを取得しました。")
            return episodes
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "ffmpeg" in msg.lower():
            err_msg = "ffmpeg が見つからないか、エラーが発生しました。"
        elif "connection" in msg.lower() or "timeout" in msg.lower():
            err_msg = "ネットワーク接続に失敗しました。"
        else:
            err_msg = f"番組情報の解析に失敗しました: {msg}"
        logger.error(err_msg)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {e}")
        raise RuntimeError(f"エピソード取得失敗: {e}") from e


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
        except Exception as e:
            last_error = str(e)
            if attempt == 0:
                time.sleep(retry_delay)
            continue

        try:
            save_episode_cache(program, episodes)
        except Exception as e:
            logger.warning(f"エピソードキャッシュの保存に失敗: {e}")
        return episodes, "network"

    stale = load_episode_cache(program, ttl_seconds=10**12)
    if stale:
        return stale, "stale-cache"

    raise RuntimeError(last_error or "エピソード一覧を取得できませんでした")

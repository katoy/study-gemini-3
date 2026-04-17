"""Cache helpers for program and episode data."""

import json
import time
from dataclasses import asdict
from pathlib import Path

from .config import CACHE_TTL_SECONDS, EPISODE_CACHE_DIR, PROGRAM_CACHE_DIR, UI_SETTINGS_PATH
from .text import _format_episode_date, _format_onair_date
from .types import Episode, Program


def _program_cache_path(genre: str | None) -> Path:
    return PROGRAM_CACHE_DIR / f"{genre or 'all'}.json"


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


def _save_json_cache(cache_path: Path, payload: dict):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_program_cache(genre: str | None, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[Program] | None:
    items = _load_json_ttl_cache(_program_cache_path(genre), "programs", ttl_seconds)
    if items is None:
        return None
    return [
        Program(
            **{
                **item,
                "display_date": _format_onair_date(str(item.get("onair_date", ""))),
            }
        )
        for item in items
    ]


def save_program_cache(genre: str | None, programs: list[Program]):
    _save_json_cache(
        _program_cache_path(genre),
        {"fetched_at": time.time(), "genre": genre, "programs": [asdict(p) for p in programs]},
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


def _episode_cache_path(program: Program) -> Path:
    return EPISODE_CACHE_DIR / f"{program.site_id}_{program.corner_id}.json"


def load_episode_cache(program: Program, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[Episode] | None:
    items = _load_json_ttl_cache(_episode_cache_path(program), "episodes", ttl_seconds)
    if items is None:
        return None
    return [
        Episode(
            **{
                **item,
                "display_date": _format_episode_date(str(item.get("date", ""))),
            }
        )
        for item in items
    ]


def save_episode_cache(program: Program, episodes: list[Episode]):
    _save_json_cache(
        _episode_cache_path(program),
        {
            "fetched_at": time.time(),
            "site_id": program.site_id,
            "corner_id": program.corner_id,
            "episodes": [asdict(e) for e in episodes],
        },
    )


def clear_episode_cache() -> int:
    return _clear_cache_dir(EPISODE_CACHE_DIR)


def clear_ui_settings() -> int:
    if not UI_SETTINGS_PATH.exists():
        return 0
    UI_SETTINGS_PATH.unlink()
    return 1


def clear_all_cache() -> int:
    return clear_program_cache() + clear_episode_cache()

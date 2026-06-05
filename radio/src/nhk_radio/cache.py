"""Cache helpers for program and episode data."""

import functools
import json
import logging
import time
from dataclasses import asdict, fields
from pathlib import Path

from . import _io
from .config import (
    _episode_cache_dir,
    _program_cache_dir,
    _ui_settings_path,
)
from .constants import CACHE_TTL_SECONDS
from .text import _format_episode_date, _format_onair_date
from .types import Episode, Program

logger = logging.getLogger(__name__)

# 破壊的変更 (フィールド削除・型変更) 時にインクリメントして旧キャッシュを無効化する。
# フィールド追加は _filter_dataclass_kwargs 側で吸収されるため、バージョンを上げる必要はない。
CACHE_SCHEMA_VERSION = 1


@functools.cache
def _dataclass_field_names(cls) -> frozenset[str]:
    """dataclass フィールド名のセットをキャッシュして返す。"""
    return frozenset(f.name for f in fields(cls))


def _filter_dataclass_kwargs(cls, data: dict) -> dict:
    """dataclass のフィールドに存在するキーだけ残す。旧キャッシュとの互換性維持用。"""
    valid_keys = _dataclass_field_names(cls)
    return {k: v for k, v in data.items() if k in valid_keys}


def _program_cache_path(genre: str | None) -> Path:
    return _program_cache_dir() / f"{genre or 'all'}.json"


def _load_json_ttl_cache(cache_path: Path, data_key: str, ttl_seconds: int) -> list[dict] | None:
    """JSON キャッシュを読み込む共通ヘルパー。

    TTL 切れ・破損・スキーマバージョン不一致の場合は None を返す (= 再取得を促す)。
    """
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    # スキーマバージョン不一致 (旧フォーマット含む) は破棄して再取得
    if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    fetched_at = payload.get("fetched_at")
    items = payload.get(data_key)
    # bool は int の派生なので明示除外 (fetched_at=True が通過しないように)
    if isinstance(fetched_at, bool) or not isinstance(fetched_at, (int, float)):
        return None
    if not isinstance(items, list):
        return None
    if time.time() - float(fetched_at) > ttl_seconds:
        return None
    return [item for item in items if isinstance(item, dict)]


def _save_json_cache(cache_path: Path, payload: dict):
    """スキーマバージョンを付与してアトミックにキャッシュを書き込む。

    一時ファイルへ書き込んだ後に rename するため、書き込み中プロセスが終了しても
    キャッシュが破損しない。
    """
    payload_with_version = {"schema_version": CACHE_SCHEMA_VERSION, **payload}
    _io.atomic_write_json(cache_path, payload_with_version, indent=None)


def load_program_cache(genre: str | None, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[Program] | None:
    items = _load_json_ttl_cache(_program_cache_path(genre), "programs", ttl_seconds)
    if items is None:
        return None
    return [
        Program(
            **_filter_dataclass_kwargs(
                Program,
                {**item, "display_date": _format_onair_date(str(item.get("onair_date", "")))},
            )
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
    for pattern in ("*.json", "*.tmp"):
        for path in cache_dir.glob(pattern):
            if not path.is_file():  # pragma: no cover - defensive: glob yields dirs rarely
                continue
            try:
                path.unlink()
            except OSError as e:
                logger.warning(f"キャッシュ削除に失敗: {path} ({e})")
                continue
            removed += 1
    return removed


def clear_program_cache() -> int:
    return _clear_cache_dir(_program_cache_dir())


def _episode_cache_path(program: Program) -> Path:
    return _episode_cache_dir() / f"{program.site_id}_{program.corner_id}.json"


def load_episode_cache(program: Program, ttl_seconds: int = CACHE_TTL_SECONDS) -> list[Episode] | None:
    items = _load_json_ttl_cache(_episode_cache_path(program), "episodes", ttl_seconds)
    if items is None:
        return None
    return [
        Episode(
            **_filter_dataclass_kwargs(
                Episode,
                {**item, "display_date": _format_episode_date(str(item.get("date", "")))},
            )
        )
        for item in items
    ]


def save_episode_cache(program: Program, episodes: list[Episode]):
    _save_json_cache(
        _episode_cache_path(program),
        {"fetched_at": time.time(), "episodes": [asdict(e) for e in episodes]},
    )


def clear_episode_cache() -> int:
    return _clear_cache_dir(_episode_cache_dir())


def clear_ui_settings() -> int:
    path = _ui_settings_path()
    if not path.exists():
        return 0
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"UI 設定の削除に失敗: {path} ({e})")
        return 0
    return 1


def clear_all_cache() -> int:
    return clear_program_cache() + clear_episode_cache()

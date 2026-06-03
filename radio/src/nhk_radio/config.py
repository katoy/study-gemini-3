"""Configuration and UI settings helpers for the NHK radio downloader."""

import json
import os
import sys
import unicodedata
from pathlib import Path

from . import _io
from .text import _normalize_text

CACHE_TTL_SECONDS = 3600


def _default_user_cache_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "nhk_radio"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "nhk_radio"
        return Path.home() / "AppData" / "Local" / "nhk_radio"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "nhk_radio"


def _default_user_config_root() -> Path:
    """ユーザー設定の保存先 (OS のパージ対象にならない場所)。"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "nhk_radio"
    if os.name == "nt":
        base = os.environ.get("APPDATA")  # Roaming (設定はこちらが適切)
        if base:
            return Path(base) / "nhk_radio"
        return Path.home() / "AppData" / "Roaming" / "nhk_radio"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "nhk_radio"


def _find_project_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def _resolve_cache_root_dir() -> Path:
    configured = os.environ.get("NHK_RADIO_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    project_root = _find_project_root()
    if project_root is not None:
        return project_root / ".cache"
    return _default_user_cache_root()


def _resolve_config_root_dir() -> Path:
    configured = os.environ.get("NHK_RADIO_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser()
    project_root = _find_project_root()
    if project_root is not None:
        return project_root / ".config"
    return _default_user_config_root()


def _program_cache_dir() -> Path:
    return _resolve_cache_root_dir() / "programs"


def _episode_cache_dir() -> Path:
    return _resolve_cache_root_dir() / "episodes"


def _ui_settings_path() -> Path:
    """UI設定ファイルのフルパスを返す。環境変数等の変更を即座に反映する。"""
    return _resolve_config_root_dir() / "ui_settings.json"


def _migrate_legacy_ui_settings():
    """旧バージョンがキャッシュディレクトリに書いていた ui_settings.json を移行する。

    べき等処理のため複数回実行しても安全。既に新パスが存在していたら何もしない。
    """
    legacy_path = _resolve_cache_root_dir() / "ui_settings.json"
    settings_path = _ui_settings_path()
    if legacy_path == settings_path:
        return
    if not legacy_path.exists() or settings_path.exists():
        return
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.replace(settings_path)
    except OSError:
        # 移行失敗は致命的ではない (新規作成として扱う)
        pass


DEFAULT_UI_THEME = "light"
DEFAULT_UI_FONT_SIZE_PT = "11"
SEARCH_HISTORY_LIMIT = 30
HELP_CONTENT_VERSION = 1


def _normalize_search_history(items: list) -> list[str]:
    """検索履歴を正規化・重複除去して返す。"""
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        term = _normalize_text(item)
        if not term:
            continue
        key = unicodedata.normalize("NFKC", term).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(term)
        if len(result) >= SEARCH_HISTORY_LIMIT:
            break
    return result


def _load_ui_settings() -> dict[str, str | list[str] | int]:
    _migrate_legacy_ui_settings()
    path = _ui_settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    settings: dict[str, str | list[str] | int] = {}

    theme = payload.get("theme")
    if theme in {"light", "dark"}:
        settings["theme"] = theme

    font_size = payload.get("font_size_pt") or payload.get("font_size")
    if isinstance(font_size, bool):
        font_size = int(font_size)
    if isinstance(font_size, int | str):
        try:
            font_size_pt = min(max(int(font_size), 9), 18)
            settings["font_size_pt"] = font_size_pt
        except ValueError:
            pass

    search_history = payload.get("program_search_history")
    if isinstance(search_history, list):
        normalized = _normalize_search_history(search_history)
        if normalized:
            settings["program_search_history"] = normalized

    help_ver = payload.get("help_seen_version")
    if isinstance(help_ver, int):
        settings["help_seen_version"] = help_ver

    return settings


def _save_ui_settings(theme: str, font_size: int, program_search_history: list[str] | None = None):
    _migrate_legacy_ui_settings()
    path = _ui_settings_path()
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}

    payload = {
        "theme": theme,
        "font_size_pt": font_size,
        "program_search_history": program_search_history or [],
    }
    if isinstance(existing.get("help_seen_version"), int):
        payload["help_seen_version"] = existing["help_seen_version"]

    _io.atomic_write_json(path, payload)


def _save_help_seen_version(version: int) -> None:
    """ヘルプ表示済みバージョンを設定ファイルに保存（既存キーを保持）。"""
    _migrate_legacy_ui_settings()
    path = _ui_settings_path()
    try:
        payload: dict = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["help_seen_version"] = version
    _io.atomic_write_json(path, payload)

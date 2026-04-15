"""Configuration and UI settings helpers for the NHK radio downloader."""

import json
import unicodedata
from pathlib import Path

CACHE_TTL_SECONDS = 3600
CACHE_ROOT_DIR = Path(__file__).resolve().parent / ".cache"
PROGRAM_CACHE_DIR = CACHE_ROOT_DIR / "programs"
EPISODE_CACHE_DIR = CACHE_ROOT_DIR / "episodes"
UI_SETTINGS_PATH = CACHE_ROOT_DIR / "ui_settings.json"

DEFAULT_UI_THEME = "light"
DEFAULT_UI_FONT_SIZE_PT = "11"
SEARCH_HISTORY_LIMIT = 30


def _normalize_search_term(text: str) -> str:
    return (text or "").replace("\u3000", " ").strip()


def _normalize_search_history(items: list) -> list[str]:
    """検索履歴を正規化・重複除去して返す。"""
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        term = _normalize_search_term(item)
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
        font_size_pt = min(max(int(font_size), 9), 18)
        settings["font_size_pt"] = str(font_size_pt)
    except (TypeError, ValueError):
        pass

    search_history = payload.get("program_search_history")
    if isinstance(search_history, list):
        normalized = _normalize_search_history(search_history)
        if normalized:
            settings["program_search_history"] = normalized

    return settings


def _save_ui_settings(theme: str, font_size_pt: str, program_search_history: list[str] | None = None):
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "theme": theme,
        "font_size_pt": int(font_size_pt),
        "program_search_history": program_search_history or [],
    }
    UI_SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

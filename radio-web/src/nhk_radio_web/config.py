"""Configuration helpers for the NHK radio web downloader."""

import os
import sys
from pathlib import Path

CACHE_TTL_SECONDS = 3600


def _default_user_cache_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "nhk_radio_web"
    if os.name == "nt":  # pragma: no cover
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")  # pragma: no cover
        if base:  # pragma: no cover
            return Path(base) / "nhk_radio_web"  # pragma: no cover
        return Path.home() / "AppData" / "Local" / "nhk_radio_web"  # pragma: no cover
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "nhk_radio_web"


def _find_project_root() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "nhk_radio_web").is_dir():
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


def _program_cache_dir() -> Path:
    return _resolve_cache_root_dir() / "programs"


def _episode_cache_dir() -> Path:
    return _resolve_cache_root_dir() / "episodes"


def _default_download_dir() -> Path:
    configured = os.environ.get("NHK_RADIO_DOWNLOAD_DIR")
    if configured:
        return Path(configured).expanduser()
    project_root = _find_project_root()
    if project_root is not None:
        return project_root / "downloads"
    return Path.home() / "Downloads" / "nhk_radio"

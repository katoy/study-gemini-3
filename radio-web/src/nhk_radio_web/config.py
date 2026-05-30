"""Configuration helpers for the NHK radio web downloader."""

import contextlib
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 3600
DEFAULT_MAX_CONCURRENT_DL = 2
DEFAULT_STORAGE_LIMIT_BYTES = 10 * 1024 * 1024 * 1024


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


def _settings_path() -> Path:
    """設定ファイル (.cache/settings.json) のパスを返す。"""
    return _resolve_cache_root_dir() / "settings.json"


def load_storage_limit() -> int:
    """保存されたストレージ容量上限を読み込む。見つからない場合はデフォルトを返す。"""
    try:
        settings_file = _settings_path()
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(data.get("storage_limit_bytes"), int):
                return data["storage_limit_bytes"]
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"設定ファイルの読み込みに失敗: {e}")
    return DEFAULT_STORAGE_LIMIT_BYTES


def save_storage_limit(limit_bytes: int) -> bool:
    """ストレージ容量上限を保存する。成功時は True を返す。"""
    try:
        settings_path = _settings_path()
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        # 既存設定を読み込み
        data: dict = {}
        if settings_path.exists():
            with contextlib.suppress(json.JSONDecodeError):
                data = json.loads(settings_path.read_text(encoding="utf-8"))
        # 容量上限を更新
        data["storage_limit_bytes"] = limit_bytes
        settings_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError as e:
        logger.warning(f"設定ファイルの保存に失敗: {e}")
        return False


def load_max_concurrent_dl() -> int:
    """並行ダウンロード数の上限を読み込む。見つからない場合はデフォルトを返す。"""
    # 環境変数を優先
    if env_value := os.environ.get("NHK_RADIO_MAX_CONCURRENT_DL"):
        try:
            return int(env_value)
        except ValueError:
            logger.warning(f"NHK_RADIO_MAX_CONCURRENT_DL が無効な値です: {env_value}")
    try:
        settings_file = _settings_path()
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(data.get("max_concurrent_dl"), int) and 1 <= data["max_concurrent_dl"] <= 10:
                return data["max_concurrent_dl"]
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"設定ファイルの読み込みに失敗: {e}")
    return DEFAULT_MAX_CONCURRENT_DL


def save_max_concurrent_dl(max_concurrent: int) -> bool:
    """並行ダウンロード数の上限を保存する。成功時は True を返す。"""
    if not 1 <= max_concurrent <= 10:
        logger.warning(f"max_concurrent_dl は 1-10 の範囲である必要があります: {max_concurrent}")
        return False
    try:
        settings_path = _settings_path()
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        # 既存設定を読み込み
        data: dict = {}
        if settings_path.exists():
            with contextlib.suppress(json.JSONDecodeError):
                data = json.loads(settings_path.read_text(encoding="utf-8"))
        # 並行数を更新
        data["max_concurrent_dl"] = max_concurrent
        settings_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError as e:
        logger.warning(f"設定ファイルの保存に失敗: {e}")
        return False

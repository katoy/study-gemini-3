"""Download tracking and output helpers."""

from .cleanup import cleanup_partial_episode_files, open_downloaded_folder
from .filesystem import (
    _FILE_SCAN_CACHE,
    _FILE_SCAN_CACHE_MAX_SIZE,
    _clear_file_scan_cache,
    _episode_key,
    _episode_output_candidates,
    _episode_output_identity,
    _episode_output_matches,
    _episode_output_patterns,
    _episode_storage_title,
    _get_cached_glob_files,
    _legacy_program_output_dirs,
    _program_filename_template,
    _program_output_dir,
    _program_search_dirs,
    _program_storage_id,
    _program_storage_title,
    _program_storage_titles,
)
from .manifest import (
    _clear_manifest_cache,
    _download_manifest_lock,
    _download_manifest_path,
    _load_download_manifest,
    _save_download_manifest,
    find_episode_downloaded_path,
    get_downloaded_episode_keys,
    is_episode_downloaded,
    mark_episode_downloaded,
    remove_episode_from_manifest,
    sync_episode_download_history,
)
from .runner import (
    _download_episode_command,
    _format_download_eta,
    _format_download_percent,
    _parse_yt_dlp_progress,
    _yt_dlp_command,
    run_yt_dlp_subprocess,
)

__all__ = [
    # manifest API (public)
    "mark_episode_downloaded",
    "remove_episode_from_manifest",
    "sync_episode_download_history",
    "get_downloaded_episode_keys",
    "is_episode_downloaded",
    "find_episode_downloaded_path",
    # manifest API (internal, used by tests)
    "_download_manifest_path",
    "_download_manifest_lock",
    "_load_download_manifest",
    "_save_download_manifest",
    "_clear_manifest_cache",
    # filesystem API (mostly private, but needed by GUI and tests)
    "_episode_key",
    "_program_output_dir",
    "_program_filename_template",
    "_program_storage_title",
    "_program_storage_titles",
    "_program_storage_id",
    "_program_search_dirs",
    "_legacy_program_output_dirs",
    "_episode_output_identity",
    "_episode_output_patterns",
    "_episode_output_matches",
    "_episode_output_candidates",
    "_episode_storage_title",
    "_get_cached_glob_files",
    "_clear_file_scan_cache",
    "_FILE_SCAN_CACHE",
    "_FILE_SCAN_CACHE_MAX_SIZE",
    # runner API
    "run_yt_dlp_subprocess",
    "_yt_dlp_command",
    "_download_episode_command",
    "_parse_yt_dlp_progress",
    "_format_download_eta",
    "_format_download_percent",
    # cleanup API
    "cleanup_partial_episode_files",
    "open_downloaded_folder",
]

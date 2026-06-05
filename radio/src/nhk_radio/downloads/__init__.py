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
    _program_search_dirs,
    _program_storage_id,
    _program_storage_title,
    _program_storage_titles,
    program_filename_template,
    program_output_dir,
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
    download_episode_command,
    _format_download_eta,
    _format_download_percent,
    _parse_yt_dlp_progress,
    _yt_dlp_command,
    run_yt_dlp_subprocess,
)

__all__ = [
    "cleanup_partial_episode_files",
    "download_episode_command",
    "find_episode_downloaded_path",
    "get_downloaded_episode_keys",
    "is_episode_downloaded",
    "mark_episode_downloaded",
    "open_downloaded_folder",
    "program_filename_template",
    "program_output_dir",
    "remove_episode_from_manifest",
    "run_yt_dlp_subprocess",
    "sync_episode_download_history",
]

"""Download tracking and output helpers."""

from .cleanup import (
    BACKUP_SUFFIX,  # noqa: F401
    cleanup_partial_episode_files,
    cleanup_residual_backup_files,
    open_downloaded_folder,
)
from .filesystem import (
    _FILE_SCAN_CACHE,  # noqa: F401
    _FILE_SCAN_CACHE_MAX_SIZE,  # noqa: F401
    _clear_file_scan_cache,  # noqa: F401
    _episode_key,  # noqa: F401
    _episode_output_candidates,  # noqa: F401
    _episode_output_identity,  # noqa: F401
    _episode_output_matches,  # noqa: F401
    _episode_output_patterns,  # noqa: F401
    _episode_storage_title,  # noqa: F401
    _get_cached_glob_files,  # noqa: F401
    _legacy_program_output_dirs,  # noqa: F401
    _program_search_dirs,  # noqa: F401
    _program_storage_id,  # noqa: F401
    _program_storage_title,  # noqa: F401
    _program_storage_titles,  # noqa: F401
    program_filename_template,
    program_output_dir,
)
from .manifest import (
    _clear_manifest_cache,  # noqa: F401
    _download_manifest_lock,  # noqa: F401
    _download_manifest_path,  # noqa: F401
    _load_download_manifest,  # noqa: F401
    _save_download_manifest,  # noqa: F401
    find_episode_downloaded_path,
    get_downloaded_episode_keys,
    is_episode_downloaded,
    is_within_output_dir,
    mark_episode_downloaded,
    remove_episode_from_manifest,
    sync_episode_download_history,
)
from .runner import (
    _format_download_eta,  # noqa: F401
    _format_download_percent,  # noqa: F401
    _parse_yt_dlp_progress,  # noqa: F401
    _yt_dlp_command,  # noqa: F401
    download_episode_command,
    output_template,
    run_yt_dlp_subprocess,
)

__all__ = [
    "cleanup_partial_episode_files",
    "cleanup_residual_backup_files",
    "download_episode_command",
    "find_episode_downloaded_path",
    "get_downloaded_episode_keys",
    "is_episode_downloaded",
    "is_within_output_dir",
    "mark_episode_downloaded",
    "open_downloaded_folder",
    "output_template",
    "program_filename_template",
    "program_output_dir",
    "remove_episode_from_manifest",
    "run_yt_dlp_subprocess",
    "sync_episode_download_history",
]

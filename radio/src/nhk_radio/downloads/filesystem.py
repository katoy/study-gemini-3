"""ダウンロード関連のパス計算とファイルスキャン。"""

import fnmatch
import logging
import os
from collections import OrderedDict
from pathlib import Path

from ..text import _program_genre_labels, _safe_name
from ..types import Episode, Program

logger = logging.getLogger(__name__)

# 同一セッション内でのファイル走査結果キャッシュ。
# mtime ベースの自動無効化により古いエントリは再スキャン時に上書きされる。
# メモリリーク防止のため、最大エントリ数を制限する。
# 環境変数 NHK_RADIO_FILE_SCAN_CACHE_SIZE で上書き可能（デフォルト 100）
_FILE_SCAN_CACHE_MAX_SIZE = int(os.environ.get("NHK_RADIO_FILE_SCAN_CACHE_SIZE", "100"))

import threading
_FILE_SCAN_CACHE: OrderedDict[Path, tuple[float, list[Path]]] = OrderedDict()
_FILE_SCAN_CACHE_LOCK = threading.Lock()


def _program_output_dir(output_dir: Path, program: Program) -> Path:
    return output_dir / _program_storage_id(program)


def _program_storage_id(program: Program) -> str:
    site_id = (program.site_id or "").strip()
    corner_id = (program.corner_id or "").strip()
    if site_id and corner_id:
        return f"{site_id}_{corner_id}"
    return _safe_name(_program_storage_title(program))


def _program_storage_title(program: Program) -> str:
    return str(program.title or program.display_title or "unknown")


def _program_storage_titles(program: Program) -> list[str]:
    titles: list[str] = []
    for value in (
        program.title,
        program.display_title,
        f"{program.site_id or ''}_{program.corner_id or ''}".strip("_"),
    ):
        normalized = _safe_name(str(value or ""))
        if normalized and normalized not in titles:
            titles.append(normalized)
    return titles or ["unknown"]


def _legacy_program_output_dirs(output_dir: Path, program: Program) -> list[Path]:
    genre_labels = [_safe_name(label) for label in _program_genre_labels(program)]
    candidates = [output_dir / genre_dir / title_dir for genre_dir in genre_labels for title_dir in _program_storage_titles(program)]
    return list(dict.fromkeys(candidates))


def _program_search_dirs(output_dir: Path, program: Program) -> list[Path]:
    primary = _program_output_dir(output_dir, program)
    dirs = [primary]
    for candidate in _legacy_program_output_dirs(output_dir, program):
        if candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _episode_storage_title(episode: Episode) -> str:
    return str(episode.title or episode.display_title or "unknown")


def _episode_output_identity(program: Program, episode: Episode) -> tuple[list[str], str, str]:
    program_titles = _program_storage_titles(program)
    episode_title = _safe_name(_episode_storage_title(episode))
    episode_date = (episode.date or "").strip()
    return program_titles, episode_title, episode_date


def _program_filename_template(program: Program, max_items: bool = False) -> str:
    title = _safe_name(_program_storage_title(program))
    if max_items:
        return f"%(playlist_index)s_%(upload_date)s_{title}_%(title)s.%(ext)s"
    return f"%(upload_date)s_{title}_%(title)s.%(ext)s"


def _episode_key(episode: Episode) -> str:
    episode_id = (episode.id or "").strip()
    if episode_id:
        return episode_id
    return f"{episode.date or ''}:{episode.title or ''}"


def _episode_output_patterns(program: Program, episode: Episode) -> list[str]:
    program_titles, episode_title, episode_date = _episode_output_identity(program, episode)
    patterns: list[str] = []
    for program_title in program_titles:
        if episode_date:
            patterns.append(f"{episode_date}_{program_title}_{episode_title}.*")
            patterns.append(f"*_{episode_date}_{program_title}_{episode_title}.*")
        else:
            patterns.append(f"{program_title}_{episode_title}.*")
            patterns.append(f"*_{program_title}_{episode_title}.*")
    return patterns


def _episode_output_matches(path: Path, program: Program, episode: Episode) -> bool:
    if not path.is_file() or path.name == ".downloaded.json" or path.suffix in {".part", ".ytdl"}:
        return False

    program_titles, episode_title, episode_date = _episode_output_identity(program, episode)
    name = path.name

    # 1) 日付による絞り込み (最も強力な指標)
    if episode_date and episode_date not in name:
        return False

    # 2) エピソードタイトルが含まれているか
    # (記号などが除去された safe_name で比較)
    if episode_title and episode_title not in _safe_name(name):
        return False

    # 3) 番組タイトルが含まれているか (少なくとも1つ)
    return any(title in _safe_name(name) for title in program_titles)


def _get_cached_glob_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []

    try:
        current_mtime = directory.stat().st_mtime
    except OSError:
        return []

    with _FILE_SCAN_CACHE_LOCK:
        entry = _FILE_SCAN_CACHE.get(directory)
        if entry is not None and entry[0] == current_mtime:
            # ヒットした場合は末尾に移動 (LRU)
            _FILE_SCAN_CACHE.move_to_end(directory)
            return entry[1]

        try:
            files = [p for p in directory.iterdir() if p.is_file()]
        except OSError as e:
            logger.debug(f"ディレクトリ走査に失敗: {directory} ({e})")
            return []

        _FILE_SCAN_CACHE[directory] = (current_mtime, files)
        # 容量制限（超過時は最古エントリを削除）
        if len(_FILE_SCAN_CACHE) > _FILE_SCAN_CACHE_MAX_SIZE:
            removed_path, _ = _FILE_SCAN_CACHE.popitem(last=False)
            logger.debug(f"ファイルスキャンキャッシュ超過。削除: {removed_path}")
        return files


def _clear_file_scan_cache(directory: Path | None = None):
    with _FILE_SCAN_CACHE_LOCK:
        if directory:
            _FILE_SCAN_CACHE.pop(directory, None)
        else:
            _FILE_SCAN_CACHE.clear()


def _episode_output_candidates(program_dir: Path, program: Program, episode: Episode) -> list[Path]:
    program_titles, episode_title, episode_date = _episode_output_identity(program, episode)

    files = _get_cached_glob_files(program_dir)
    candidates = [path for path in files if _episode_output_matches(path, program, episode)]

    suffix_priority = {
        ".mp3": 0,
        ".m4a": 1,
        ".aac": 2,
        ".wav": 3,
        ".mp4": 4,
    }
    candidates.sort(
        key=lambda path: (
            0
            if episode_date
            and any(path.name.startswith(f"{episode_date}_{program_title}_") for program_title in program_titles)
            else 1,
            0 if episode_title and f"_{episode_title}." in path.name else 1,
            suffix_priority.get(path.suffix.lower(), 99),
            -path.stat().st_mtime,
        )
    )
    return candidates

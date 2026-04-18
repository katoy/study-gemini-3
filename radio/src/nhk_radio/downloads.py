"""Download tracking and output helpers."""

import fnmatch
import json
import logging
import re
import threading
from pathlib import Path

from .cache import _save_json_cache
from .text import _genre_label, _safe_name
from .types import Episode, Program

logger = logging.getLogger(__name__)

_MANIFEST_LOCKS: dict[Path, threading.RLock] = {}
_MANIFEST_LOCKS_GUARD = threading.Lock()

# 同一セッション内でのファイル走査結果キャッシュ
_FILE_SCAN_CACHE: dict[Path, tuple[float, list[Path]]] = {}
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
    genre_labels = [_safe_name(program.genre_label or _genre_label(program.genre))]
    if program.genre:
        genre_labels.append(_safe_name(_genre_label(program.genre)))

    dirs: list[Path] = []
    seen: set[Path] = set()
    for genre_dir in genre_labels:
        for title_dir in _program_storage_titles(program):
            candidate = output_dir / genre_dir / title_dir
            if candidate in seen:
                continue
            seen.add(candidate)
            dirs.append(candidate)
    return dirs


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


def _download_manifest_path(program: Program, output_dir: Path) -> Path:
    return _program_output_dir(output_dir, program) / ".downloaded.json"


def _download_manifest_lock(program: Program, output_dir: Path) -> threading.RLock:
    manifest_path = _download_manifest_path(program, output_dir)
    with _MANIFEST_LOCKS_GUARD:
        lock = _MANIFEST_LOCKS.get(manifest_path)
        if lock is None:
            lock = threading.RLock()
            _MANIFEST_LOCKS[manifest_path] = lock
        return lock


def _load_download_manifest(program: Program, output_dir: Path) -> tuple[set[str], dict[str, str]]:
    downloaded_items: set[str] = set()
    saved_paths: dict[str, str] = {}
    manifest_paths = [_download_manifest_path(program, output_dir)]
    for legacy_dir in _legacy_program_output_dirs(output_dir, program):
        manifest_path = legacy_dir / ".downloaded.json"
        if manifest_path not in manifest_paths:
            manifest_paths.append(manifest_path)

    for manifest_path in manifest_paths:
        if not manifest_path.exists():
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.debug(f"マニフェストの読み込みに失敗: {manifest_path} ({e})")
            continue

        downloaded = payload.get("downloaded")
        if isinstance(downloaded, list):
            downloaded_items.update(str(item) for item in downloaded)

        paths = payload.get("paths")
        if isinstance(paths, dict):
            for key, value in paths.items():
                saved_paths[str(key)] = str(value)

    return downloaded_items, saved_paths


def _save_download_manifest(program: Program, output_dir: Path, downloaded: set[str], paths: dict[str, str]):
    manifest_path = _download_manifest_path(program, output_dir)
    payload = {"downloaded": sorted(downloaded), "paths": paths}
    _save_json_cache(manifest_path, payload)


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
    try:
        current_mtime = directory.stat().st_mtime
    except OSError:
        return []
    with _FILE_SCAN_CACHE_LOCK:
        entry = _FILE_SCAN_CACHE.get(directory)
        if entry is not None and entry[0] == current_mtime:
            return entry[1]
        files = [p for p in directory.iterdir() if p.is_file()]
        _FILE_SCAN_CACHE[directory] = (current_mtime, files)
        return files


def _clear_file_scan_cache(directory: Path | None = None):
    with _FILE_SCAN_CACHE_LOCK:
        if directory:
            _FILE_SCAN_CACHE.pop(directory, None)
        else:
            _FILE_SCAN_CACHE.clear()


def _episode_output_candidates(program_dir: Path, program: Program, episode: Episode) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    program_titles, episode_title, episode_date = _episode_output_identity(program, episode)

    files = _get_cached_glob_files(program_dir)
    for path in files:
        if not _episode_output_matches(path, program, episode):
            continue
        if path in seen:
            continue
        seen.add(path)
        candidates.append(path)

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


def mark_episode_downloaded(output_dir: Path, program: Program, episode: Episode, path: Path | None = None):
    with _download_manifest_lock(program, output_dir):
        downloaded, saved_paths = _load_download_manifest(program, output_dir)
        episode_key = _episode_key(episode)
        downloaded.add(episode_key)
        program_dir = _program_output_dir(output_dir, program)
        if path is not None and path.exists():
            try:
                saved_paths[episode_key] = str(path.relative_to(program_dir))
            except ValueError:
                saved_paths[episode_key] = str(path)
        _save_download_manifest(program, output_dir, downloaded, saved_paths)
        _clear_file_scan_cache(program_dir)


def is_episode_downloaded(output_dir: Path, program: Program, episode: Episode) -> bool:
    # キャッシュはディレクトリの mtime で自動無効化されるため明示クリアは不要

    downloaded, saved_paths = _load_download_manifest(program, output_dir)
    episode_key = _episode_key(episode)

    # 1) マニフェストに記録されたパスの実在を確認
    saved_path_str = saved_paths.get(episode_key)
    if saved_path_str:
        resolved = Path(saved_path_str)
        if not resolved.is_absolute():
            resolved = _program_output_dir(output_dir, program) / resolved
        if resolved.exists():
            return True

    # 2) ディレクトリをスキャンして候補を探す
    for program_dir in _program_search_dirs(output_dir, program):
        candidates = _episode_output_candidates(program_dir, program, episode)
        if candidates:
            return True

    return False


def resolve_episode_downloaded_path(output_dir: Path, program: Program, episode: Episode) -> Path | None:
    downloaded, saved_paths = _load_download_manifest(program, output_dir)
    episode_key = _episode_key(episode)

    # 1) マニフェストに記録されたパスを最優先で確認
    saved_path_str = saved_paths.get(episode_key)
    if saved_path_str:
        resolved = Path(saved_path_str)
        if not resolved.is_absolute():
            resolved = _program_output_dir(output_dir, program) / resolved
        if resolved.exists():
            return resolved

    # 2) ディレクトリをスキャンして候補を探す
    for program_dir in _program_search_dirs(output_dir, program):
        candidates = _episode_output_candidates(program_dir, program, episode)
        if candidates:
            # 見つかった場合はマニフェストを更新しておく（次回から高速化）
            mark_episode_downloaded(output_dir, program, episode, candidates[0])
            return candidates[0]

    return None


def cleanup_partial_episode_files(output_dir: Path, program: Program, episode: Episode):
    for program_dir in _program_search_dirs(output_dir, program):
        if not program_dir.exists():
            continue
        _clear_file_scan_cache(program_dir)
        files = [p for p in program_dir.iterdir() if p.is_file()]
        for path in files:
            if path.suffix in {".part", ".ytdl"} and any(
                fnmatch.fnmatch(path.name, pattern)
                for pattern in _episode_output_patterns(program, episode)
            ):
                try:
                    path.unlink()
                except OSError as e:
                    logger.warning(f"一時ファイルの削除に失敗: {path} ({e})")


def _format_download_percent(percent: float | None) -> str:
    if percent is None:
        return "--%"
    percent = min(max(percent, 0.0), 100.0)
    rounded = round(percent)
    if abs(percent - rounded) < 0.05:
        return f"{int(rounded)}%"
    return f"{percent:.1f}%"


def _format_download_eta(eta: str | None) -> str:
    return f"残り {eta}" if eta else "残り --:--"


def _parse_yt_dlp_progress(line: str) -> tuple[float | None, str | None, str | None]:
    text = line.strip()
    if not text:
        return None, None, None

    if "[ExtractAudio]" in text or "Post-process" in text:
        return 100.0, None, "変換中..."

    percent_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", text)
    if percent_match:
        percent = float(percent_match.group(1))
        eta_match = re.search(r"\bETA\s+([0-9:]+)", text)
        eta = eta_match.group(1) if eta_match else None
        status = "変換中..." if percent >= 100 else "ダウンロード中..."
        return percent, eta, status

    return None, None, None


def _download_episode_command(url: str, output_dir: Path, filename_template: str, audio_only: bool = True) -> list[str]:
    return _yt_dlp_command(
        url,
        str(output_dir / filename_template),
        audio_only=audio_only,
        no_playlist=True,
        newline=True,
    )


def _yt_dlp_command(
    url: str,
    output_template: str,
    *,
    audio_only: bool,
    no_playlist: bool,
    newline: bool = False,
    max_items: int | None = None,
) -> list[str]:
    cmd = ["yt-dlp"]
    if newline:
        cmd.append("--newline")
    # AES-128 暗号化 HLS ストリームで ffmpeg が aac_adtstoasc フィルタに失敗するのを防ぐ
    cmd.append("--hls-use-mpegts")
    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    cmd += ["-o", output_template]
    if max_items:
        cmd += ["--playlist-end", str(max_items)]
    elif no_playlist:
        cmd.append("--no-playlist")
    cmd.append(url)
    return cmd

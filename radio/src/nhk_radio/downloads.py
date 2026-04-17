"""Download tracking and output helpers."""

import json
import re
import threading
from pathlib import Path

from .cache import _save_json_cache
from .text import _genre_label, _safe_name

_MANIFEST_LOCKS: dict[Path, threading.RLock] = {}
_MANIFEST_LOCKS_GUARD = threading.Lock()


def _program_output_dir(output_dir: Path, program: dict) -> Path:
    return output_dir / _program_storage_id(program)


def _program_storage_id(program: dict) -> str:
    site_id = str(program.get("site_id") or "").strip()
    corner_id = str(program.get("corner_id") or "").strip()
    if site_id and corner_id:
        return f"{site_id}_{corner_id}"
    return _safe_name(_program_storage_title(program))


def _program_storage_title(program: dict) -> str:
    return str(program.get("title") or program.get("display_title") or "unknown")


def _program_storage_titles(program: dict) -> list[str]:
    titles: list[str] = []
    for value in (
        program.get("title"),
        program.get("display_title"),
        f"{program.get('site_id', '')}_{program.get('corner_id', '')}".strip("_"),
    ):
        normalized = _safe_name(str(value or ""))
        if normalized and normalized not in titles:
            titles.append(normalized)
    return titles or ["unknown"]


def _legacy_program_output_dirs(output_dir: Path, program: dict) -> list[Path]:
    genre_labels = [_safe_name(program.get("genre_label") or _genre_label(program.get("genre")))]
    if program.get("genre"):
        genre_labels.append(_safe_name(_genre_label(program.get("genre"))))

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


def _program_search_dirs(output_dir: Path, program: dict) -> list[Path]:
    primary = _program_output_dir(output_dir, program)
    dirs = [primary]
    for candidate in _legacy_program_output_dirs(output_dir, program):
        if candidate not in dirs:
            dirs.append(candidate)
    return dirs


def _episode_storage_title(episode: dict) -> str:
    return str(episode.get("title") or episode.get("display_title") or "unknown")


def _episode_output_identity(program: dict, episode: dict) -> tuple[list[str], str, str]:
    program_titles = _program_storage_titles(program)
    episode_title = _safe_name(_episode_storage_title(episode))
    episode_date = str(episode.get("date") or "").strip()
    return program_titles, episode_title, episode_date


def _program_filename_template(program: dict, max_items: bool = False) -> str:
    title = _safe_name(_program_storage_title(program))
    if max_items:
        return f"%(playlist_index)s_%(upload_date)s_{title}_%(title)s.%(ext)s"
    return f"%(upload_date)s_{title}_%(title)s.%(ext)s"


def _episode_key(episode: dict) -> str:
    episode_id = str(episode.get("id") or "").strip()
    if episode_id:
        return episode_id
    return f"{episode.get('date', '')}:{episode.get('title', '')}"


def _download_manifest_path(program: dict, output_dir: Path) -> Path:
    return _program_output_dir(output_dir, program) / ".downloaded.json"


def _download_manifest_lock(program: dict, output_dir: Path) -> threading.RLock:
    manifest_path = _download_manifest_path(program, output_dir)
    with _MANIFEST_LOCKS_GUARD:
        lock = _MANIFEST_LOCKS.get(manifest_path)
        if lock is None:
            lock = threading.RLock()
            _MANIFEST_LOCKS[manifest_path] = lock
        return lock


def _load_download_manifest(program: dict, output_dir: Path) -> tuple[set[str], dict[str, str]]:
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
        except (OSError, json.JSONDecodeError):
            continue

        downloaded = payload.get("downloaded")
        if isinstance(downloaded, list):
            downloaded_items.update(str(item) for item in downloaded)

        paths = payload.get("paths")
        if isinstance(paths, dict):
            for key, value in paths.items():
                saved_paths[str(key)] = str(value)

    return downloaded_items, saved_paths


def _save_download_manifest(program: dict, output_dir: Path, downloaded: set[str], paths: dict[str, str]):
    manifest_path = _download_manifest_path(program, output_dir)
    payload = {"downloaded": sorted(downloaded), "paths": paths}
    _save_json_cache(manifest_path, payload)


def _episode_output_patterns(program: dict, episode: dict) -> list[str]:
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


def _episode_output_matches(path: Path, program: dict, episode: dict) -> bool:
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
    if not any(title in _safe_name(name) for title in program_titles):
        return False

    return True


def _episode_output_candidates(program_dir: Path, program: dict, episode: dict) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    program_titles, episode_title, episode_date = _episode_output_identity(program, episode)
    for pattern in _episode_output_patterns(program, episode):
        for path in program_dir.glob(pattern):
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


def mark_episode_downloaded(output_dir: Path, program: dict, episode: dict, path: Path | None = None):
    with _download_manifest_lock(program, output_dir):
        downloaded, saved_paths = _load_download_manifest(program, output_dir)
        episode_key = _episode_key(episode)
        downloaded.add(episode_key)
        if path is not None and path.exists():
            program_dir = _program_output_dir(output_dir, program)
            try:
                saved_paths[episode_key] = str(path.relative_to(program_dir))
            except ValueError:
                saved_paths[episode_key] = str(path)
        _save_download_manifest(program, output_dir, downloaded, saved_paths)


def is_episode_downloaded(output_dir: Path, program: dict, episode: dict) -> bool:
    downloaded, saved_paths = _load_download_manifest(program, output_dir)
    episode_key = _episode_key(episode)

    # 1) マニフェストに直接「済み」の記録があるか (即時反映のため)
    if episode_key in downloaded:
        return True

    # 2) マニフェストに記録されたパスの実在を確認
    saved_path_str = saved_paths.get(episode_key)
    if saved_path_str:
        resolved = Path(saved_path_str)
        if not resolved.is_absolute():
            resolved = _program_output_dir(output_dir, program) / resolved
        if resolved.exists():
            return True

    # 3) ディレクトリをスキャンして候補を探す
    for program_dir in _program_search_dirs(output_dir, program):
        if program_dir.exists() and _episode_output_candidates(program_dir, program, episode):
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
        if not program_dir.exists():
            continue
        candidates = _episode_output_candidates(program_dir, program, episode)
        if candidates:
            # 見つかった場合はマニフェストを更新しておく（次回から高速化）
            mark_episode_downloaded(output_dir, program, episode, candidates[0])
            return candidates[0]

    # 3) (整合性修復) マニフェストにはあるが実体がない場合は、判定と一致させるため None を返す
    return None


def cleanup_partial_episode_files(output_dir: Path, program: dict, episode: dict):
    for program_dir in _program_search_dirs(output_dir, program):
        if not program_dir.exists():
            continue
        for pattern in _episode_output_patterns(program, episode):
            for path in program_dir.glob(pattern):
                if path.is_file() and path.suffix in {".part", ".ytdl"}:
                    path.unlink()


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

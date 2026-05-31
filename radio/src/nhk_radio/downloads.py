"""Download tracking and output helpers."""

import fnmatch
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from contextlib import suppress
from pathlib import Path

from . import _io
from .constants import YTDLP_CONCURRENT_FRAGMENTS, YTDLP_SOCKET_TIMEOUT
from .text import _program_genre_labels, _safe_name
from .types import Episode, Program

logger = logging.getLogger(__name__)

# マニフェストパスごとのロック。
# 典型的なユースケース (数～数十番組) では上限を設けなくても問題ないが、
# 保存先切り替えを頻繁に行う長寿命プロセスでは単調増加する点に注意。
_MANIFEST_LOCKS: dict[Path, threading.RLock] = {}
_MANIFEST_LOCKS_GUARD = threading.Lock()

# 同一セッション内でのファイル走査結果キャッシュ。
# mtime ベースの自動無効化により古いエントリは再スキャン時に上書きされる。
# メモリリーク防止のため、最大エントリ数を制限する。
# 環境変数 NHK_RADIO_FILE_SCAN_CACHE_SIZE で上書き可能（デフォルト 100）
def _get_file_scan_cache_max_size() -> int:
    import os
    return int(os.environ.get("NHK_RADIO_FILE_SCAN_CACHE_SIZE", "100"))

_FILE_SCAN_CACHE_MAX_SIZE = _get_file_scan_cache_max_size()
_FILE_SCAN_CACHE: OrderedDict[Path, tuple[float, list[Path]]] = OrderedDict()
_FILE_SCAN_CACHE_LOCK = threading.Lock()

# マニフェスト読み込み結果のキャッシュ（短期 TTL）。
# GUI レンダリングで is_episode_downloaded が何度も呼ばれるため、
# 番組単位で manifest の読み込み結果を時間限定で保持する。
_MANIFEST_CACHE_TTL_SECONDS = 10
_MANIFEST_CACHE: dict[Path, tuple[float, dict[str, str]]] = {}
_MANIFEST_CACHE_LOCK = threading.Lock()


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


def _load_download_manifest(program: Program, output_dir: Path) -> dict[str, str]:
    """保存済みエピソードのパス辞書を返す (key: episode_key, value: 相対or絶対パス)

    短期キャッシュにより、同一番組への繰り返しアクセスの I/O 負荷を削減。
    ファイルの mtime 変化を検出してキャッシュを無効化。
    """
    primary_manifest_path = _download_manifest_path(program, output_dir)

    # プライマリマニフェストの mtime を取得
    try:
        primary_mtime = primary_manifest_path.stat().st_mtime if primary_manifest_path.exists() else -1.0
    except OSError:
        primary_mtime = -1.0

    # キャッシュをチェック: TTL と mtime の両方を確認
    with _MANIFEST_CACHE_LOCK:
        if primary_manifest_path in _MANIFEST_CACHE:
            cached_at, cached_mtime, cached_data = _MANIFEST_CACHE[primary_manifest_path]
            if (time.time() - cached_at < _MANIFEST_CACHE_TTL_SECONDS and
                cached_mtime == primary_mtime):
                return cached_data

    # キャッシュミス: ディスクから読み込み
    saved_paths: dict[str, str] = {}
    manifest_paths = [primary_manifest_path]
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

        paths = payload.get("paths")
        if isinstance(paths, dict):
            for key, value in paths.items():
                saved_paths[str(key)] = str(value)

    # キャッシュに格納 (timestamp, mtime, data)
    with _MANIFEST_CACHE_LOCK:
        _MANIFEST_CACHE[primary_manifest_path] = (time.time(), primary_mtime, saved_paths)

    return saved_paths


def _save_download_manifest(program: Program, output_dir: Path, paths: dict[str, str]) -> bool:
    """マニフェストをアトミックに保存する。失敗時は warning を出して False を返す。

    一時ファイルへ書き込み後に rename するため、プロセスクラッシュ時も破損しない。
    """
    manifest_path = _download_manifest_path(program, output_dir)
    try:
        _io.atomic_write_json(manifest_path, {"paths": paths}, indent=None)
    except OSError as e:
        logger.warning(f"ダウンロード履歴の保存に失敗: {manifest_path} ({e})")
        return False
    return True


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


def _clear_manifest_cache(manifest_path: Path | None = None):
    """マニフェストキャッシュをクリアする。

    Args:
        manifest_path: 特定の番組のマニフェストをクリアする場合は指定。
                      None の場合はすべてクリア。
    """
    with _MANIFEST_CACHE_LOCK:
        if manifest_path:
            _MANIFEST_CACHE.pop(manifest_path, None)
        else:
            _MANIFEST_CACHE.clear()


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


def mark_episode_downloaded(
    output_dir: Path, program: Program, episode: Episode, path: Path | None = None
) -> bool:
    """ダウンロード済みエピソードをマニフェストに記録する。保存成功なら True。"""
    with _download_manifest_lock(program, output_dir):
        saved_paths = _load_download_manifest(program, output_dir)
        episode_key = _episode_key(episode)
        program_dir = _program_output_dir(output_dir, program)
        if path is not None and path.exists():
            try:
                saved_paths[episode_key] = str(path.relative_to(program_dir))
            except ValueError:
                saved_paths[episode_key] = str(path)
        saved = _save_download_manifest(program, output_dir, saved_paths)
        _clear_file_scan_cache(program_dir)
        # マニフェストが更新されたので、キャッシュも無効化
        _clear_manifest_cache(_download_manifest_path(program, output_dir))
        return saved


def get_downloaded_episode_keys(output_dir: Path, program: Program, episodes: list[Episode]) -> set[str]:
    """複数エピソードの保存状態を効率的に判定する（バッチ処理）。

    マニフェスト 1 回読み込みとディレクトリスキャン共有で N+1 問題を解決。
    """
    downloaded_keys: set[str] = set()
    saved_paths = _load_download_manifest(program, output_dir)

    # ステップ 1: マニフェスト確認
    for episode in episodes:
        episode_key = _episode_key(episode)
        saved_path_str = saved_paths.get(episode_key)
        if saved_path_str:
            resolved = Path(saved_path_str)
            if not resolved.is_absolute():
                resolved = _program_output_dir(output_dir, program) / resolved
            if resolved.exists():
                downloaded_keys.add(episode_key)

    # ステップ 2: ディレクトリスキャン (マニフェスト未記録のエピソードのみ)
    program_dirs = _program_search_dirs(output_dir, program)
    for program_dir in program_dirs:
        files = _get_cached_glob_files(program_dir)
        for episode in episodes:
            if _episode_key(episode) in downloaded_keys:
                continue
            if any(_episode_output_matches(f, program, episode) for f in files):
                downloaded_keys.add(_episode_key(episode))

    return downloaded_keys


def is_episode_downloaded(output_dir: Path, program: Program, episode: Episode) -> bool:
    # キャッシュはディレクトリの mtime で自動無効化されるため明示クリアは不要

    saved_paths = _load_download_manifest(program, output_dir)
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


def find_episode_downloaded_path(output_dir: Path, program: Program, episode: Episode) -> Path | None:
    """保存済みエピソードのパスを検索して返す (副作用なし)。"""
    saved_paths = _load_download_manifest(program, output_dir)
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
            return candidates[0]

    return None


def remove_episode_from_manifest(output_dir: Path, program: Program, episode: Episode) -> bool:
    """マニフェストから指定エピソードを削除する。"""
    with _download_manifest_lock(program, output_dir):
        saved_paths = _load_download_manifest(program, output_dir)
        episode_key = _episode_key(episode)
        if episode_key not in saved_paths:
            return False
        del saved_paths[episode_key]
        saved = _save_download_manifest(program, output_dir, saved_paths)
        program_dir = _program_output_dir(output_dir, program)
        _clear_file_scan_cache(program_dir)
        _clear_manifest_cache(_download_manifest_path(program, output_dir))
        return saved


def sync_episode_download_history(output_dir: Path, program: Program, episode: Episode) -> Path | None:
    """ディスク上の実ファイルを確認し、必要に応じてマニフェストを更新する (明示的な副作用)。"""
    path = find_episode_downloaded_path(output_dir, program, episode)
    if path:
        # 見つかった場合はマニフェストに反映しておく (副作用の明示化)
        mark_episode_downloaded(output_dir, program, episode, path)
    return path


def cleanup_partial_episode_files(output_dir: Path, program: Program, episode: Episode):
    for program_dir in _program_search_dirs(output_dir, program):
        if not program_dir.exists():
            continue
        _clear_file_scan_cache(program_dir)
        try:
            files = [p for p in program_dir.iterdir() if p.is_file()]
        except OSError as e:
            logger.debug(f"ディレクトリ走査に失敗: {program_dir} ({e})")
            continue
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
    # HLS フラグメントの並列ダウンロードとソケットタイムアウトを設定
    cmd += ["--concurrent-fragments", str(YTDLP_CONCURRENT_FRAGMENTS)]
    cmd += ["--socket-timeout", str(YTDLP_SOCKET_TIMEOUT)]
    if audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    cmd += ["-o", output_template]
    if max_items:
        cmd += ["--playlist-end", str(max_items)]
    elif no_playlist:
        cmd.append("--no-playlist")
    cmd.append(url)
    return cmd


def run_yt_dlp_subprocess(
    cmd: list[str],
    on_progress: callable[[float | None, str | None, str | None], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    """yt-dlp サブプロセスを実行し、進捗をコールバックで報告する。

    Args:
        cmd: yt-dlp コマンド (リスト形式)
        on_progress: 進捗コールバック (percent, eta, status)
        cancel_event: キャンセルイベント（設定されたら terminate）

    Returns:
        成功時 True、キャンセル時 False、失敗時 False
    """
    import subprocess

    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if process.stdout:
            for line in process.stdout:
                # キャンセルイベントがセットされたら terminate
                if cancel_event and cancel_event.is_set():
                    process.terminate()
                    break

                # 進捗コールバックを実行
                if on_progress:
                    percent, eta, status = _parse_yt_dlp_progress(line)
                    if percent is not None or eta is not None or status is not None:
                        on_progress(percent, eta, status)

        # タイムアウト 120 秒で wait
        try:
            return process.wait(timeout=120) == 0
        except subprocess.TimeoutExpired:
            logger.warning("yt-dlp プロセスが応答しません。強制終了します。")
            process.kill()
            process.wait()
            return False
    except Exception as e:
        logger.error(f"yt-dlp 実行エラー: {e}")
        if process is not None:
            with suppress(Exception):
                process.terminate()
                process.wait()
        return False


def open_downloaded_folder(folder_path: Path) -> bool:
    """ダウンロード済みエピソードの保存先フォルダをファイルマネージャーで開く。

    Args:
        folder_path: 開くフォルダのパス

    Returns:
        成功時 True、失敗時 False
    """
    import subprocess
    import sys

    if not folder_path.exists():
        logger.warning(f"フォルダが存在しません: {folder_path}")
        return False

    try:
        if sys.platform == "darwin":
            # macOS
            subprocess.run(["open", str(folder_path)], check=True)
        elif sys.platform == "win32":
            # Windows
            subprocess.run(["explorer", str(folder_path)], check=True)
        else:
            # Linux その他
            subprocess.run(["xdg-open", str(folder_path)], check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        logger.error(f"フォルダを開く際にエラー: {e}")
        return False

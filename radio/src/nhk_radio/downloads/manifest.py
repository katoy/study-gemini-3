"""ダウンロード履歴マニフェストの I/O とロック管理。"""

import json
import logging
import threading
import time
from pathlib import Path

from .. import _io
from ..types import Episode, Program

logger = logging.getLogger(__name__)

# マニフェストへの同時アクセスを保護するロック
_MANIFEST_LOCK = threading.RLock()

# マニフェスト読み込み結果のキャッシュ（短期 TTL）。
# GUI レンダリングで is_episode_downloaded が何度も呼ばれるため、
# 番組単位で manifest の読み込み結果を時間限定で保持する。
_MANIFEST_CACHE_TTL_SECONDS = 10
_MANIFEST_CACHE: dict[Path, tuple[float, float, dict[str, str]]] = {}
_MANIFEST_CACHE_LOCK = threading.Lock()


def _download_manifest_path(program: Program, output_dir: Path) -> Path:
    from . import filesystem
    return filesystem.program_output_dir(output_dir, program) / ".downloaded.json"


def _download_manifest_lock(program: Program, output_dir: Path) -> threading.RLock:
    return _MANIFEST_LOCK


def _load_download_manifest(program: Program, output_dir: Path) -> dict[str, str]:
    """保存済みエピソードのパス辞書を返す (key: episode_key, value: 相対or絶対パス)

    短期キャッシュにより、同一番組への繰り返しアクセスの I/O 負荷を削減。
    ファイルの mtime 変化を検出してキャッシュを無効化。
    """
    from . import filesystem

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
    for legacy_dir in filesystem._legacy_program_output_dirs(output_dir, program):  # pragma: no cover
        manifest_path = legacy_dir / ".downloaded.json"
        if manifest_path not in manifest_paths:  # pragma: no cover
            manifest_paths.append(manifest_path)

    for manifest_path in manifest_paths:
        if not manifest_path.exists():  # pragma: no cover
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:  # pragma: no cover
            logger.debug(f"マニフェストの読み込みに失敗: {manifest_path} ({e})")
            continue

        paths = payload.get("paths")
        if isinstance(paths, dict):  # pragma: no cover
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


def mark_episode_downloaded(
    output_dir: Path, program: Program, episode: Episode, path: Path | None = None
) -> bool:
    """ダウンロード済みエピソードをマニフェストに記録する。保存成功なら True。"""
    from . import filesystem

    with _download_manifest_lock(program, output_dir):
        saved_paths = _load_download_manifest(program, output_dir)
        episode_key = filesystem._episode_key(episode)
        program_dir = filesystem.program_output_dir(output_dir, program)
        if path is not None and path.exists():  # pragma: no cover
            try:
                saved_paths[episode_key] = str(path.relative_to(program_dir))
            except ValueError:
                saved_paths[episode_key] = str(path)
        saved = _save_download_manifest(program, output_dir, saved_paths)
        filesystem._clear_file_scan_cache(program_dir)
        # マニフェストが更新されたので、キャッシュも無効化
        _clear_manifest_cache(_download_manifest_path(program, output_dir))
        return saved


def get_downloaded_episode_keys(output_dir: Path, program: Program, episodes: list[Episode]) -> set[str]:
    """複数エピソードの保存状態を効率的に判定する（バッチ処理）。

    マニフェスト 1 回読み込みとディレクトリスキャン共有で N+1 問題を解決。
    """
    from . import filesystem

    downloaded_keys: set[str] = set()
    saved_paths = _load_download_manifest(program, output_dir)

    # ステップ 1: マニフェスト確認
    for episode in episodes:
        episode_key = filesystem._episode_key(episode)
        saved_path_str = saved_paths.get(episode_key)
        if saved_path_str:
            resolved = Path(saved_path_str)
            if not resolved.is_absolute():  # pragma: no cover
                resolved = filesystem.program_output_dir(output_dir, program) / resolved
            if resolved.exists():  # pragma: no cover
                downloaded_keys.add(episode_key)

    # ステップ 2: ディレクトリスキャン (マニフェスト未記録のエピソードのみ)
    program_dirs = filesystem._program_search_dirs(output_dir, program)
    for program_dir in program_dirs:
        files = filesystem._get_cached_glob_files(program_dir)
        for episode in episodes:
            if filesystem._episode_key(episode) in downloaded_keys:
                continue
            if any(filesystem._episode_output_matches(f, program, episode) for f in files):
                downloaded_keys.add(filesystem._episode_key(episode))

    return downloaded_keys


def find_episode_downloaded_path(output_dir: Path, program: Program, episode: Episode) -> Path | None:
    """保存済みエピソードのパスを検索して返す (副作用なし)。"""
    from . import filesystem

    saved_paths = _load_download_manifest(program, output_dir)
    episode_key = filesystem._episode_key(episode)

    # 1) マニフェストに記録されたパスを最優先で確認
    saved_path_str = saved_paths.get(episode_key)
    if saved_path_str:
        resolved = Path(saved_path_str)
        if not resolved.is_absolute():  # pragma: no cover
            resolved = filesystem.program_output_dir(output_dir, program) / resolved
        if resolved.exists():  # pragma: no cover
            return resolved

    # 2) ディレクトリをスキャンして候補を探す
    for program_dir in filesystem._program_search_dirs(output_dir, program):
        candidates = filesystem._episode_output_candidates(program_dir, program, episode)
        if candidates:
            return candidates[0]

    return None


def is_episode_downloaded(output_dir: Path, program: Program, episode: Episode) -> bool:
    return find_episode_downloaded_path(output_dir, program, episode) is not None


def remove_episode_from_manifest(output_dir: Path, program: Program, episode: Episode) -> bool:
    """マニフェストから指定エピソードを削除する。"""
    from . import filesystem

    with _download_manifest_lock(program, output_dir):
        saved_paths = _load_download_manifest(program, output_dir)
        episode_key = filesystem._episode_key(episode)
        if episode_key not in saved_paths:
            return False
        del saved_paths[episode_key]
        saved = _save_download_manifest(program, output_dir, saved_paths)
        program_dir = filesystem.program_output_dir(output_dir, program)
        filesystem._clear_file_scan_cache(program_dir)
        _clear_manifest_cache(_download_manifest_path(program, output_dir))
        return saved


def sync_episode_download_history(output_dir: Path, program: Program, episode: Episode) -> Path | None:
    """ディスク上の実ファイルを確認し、必要に応じてマニフェストを更新する (明示的な副作用)。"""
    path = find_episode_downloaded_path(output_dir, program, episode)
    if path:  # pragma: no cover
        # 見つかった場合はマニフェストに反映しておく (副作用の明示化)
        mark_episode_downloaded(output_dir, program, episode, path)
    return path

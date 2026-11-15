"""ダウンロード履歴マニフェストの I/O とロック管理。"""

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
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
    # 遅延インポート: manifest.py と filesystem.py の循環インポートを回避
    from . import filesystem
    return filesystem.program_output_dir(output_dir, program) / ".downloaded.json"


def _download_manifest_lock(program: Program, output_dir: Path) -> threading.RLock:
    # 全番組共有の単一ロック。個別番組ごとのロックではなく、
    # マニフェスト全体へのアクセスを保護するため統一ロックを使用。
    return _MANIFEST_LOCK


@contextmanager
def _manifest_write_lock(program: Program, output_dir: Path) -> Iterator[None]:
    """マニフェストの読み込みから保存までを、スレッド間とプロセス間 (GUI と CLI など) で排他する (L3)。

    ロックを取った直後に読み込みキャッシュを捨てる。キャッシュは mtime で新しさを判定するため、
    別プロセスの書き込みが同じ mtime の刻みで起きると、古い内容を読んで上書きしてしまう。

    Args:
        program: 対象の番組。
        output_dir: 保存先のルートディレクトリ。

    Yields:
        None。ブロックを抜けるとロックを外す。
    """
    manifest_path = _download_manifest_path(program, output_dir)
    with _download_manifest_lock(program, output_dir), _io.file_lock(manifest_path.with_name(".downloaded.json.lock")):
        _clear_manifest_cache(manifest_path)
        yield


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
                # 呼び出し側が書き換えてもキャッシュが変わらないよう、コピーを返す (L3)
                return dict(cached_data)

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

        if not isinstance(payload, dict):
            logger.debug(f"マニフェストの形式が辞書ではありません: {manifest_path}")
            continue

        paths = payload.get("paths")
        if isinstance(paths, dict):  # pragma: no cover
            for key, value in paths.items():
                path_str = str(value)
                # 旧ディレクトリの相対パスは、そのマニフェストがあるディレクトリを基準に解決する (L3)
                if manifest_path != primary_manifest_path and not Path(path_str).is_absolute():
                    path_str = str(manifest_path.parent / path_str)
                saved_paths[str(key)] = path_str

    # キャッシュに格納 (timestamp, mtime, data)
    with _MANIFEST_CACHE_LOCK:
        _MANIFEST_CACHE[primary_manifest_path] = (time.time(), primary_mtime, saved_paths)

    return dict(saved_paths)


def _resolve_manifest_path(saved_path_str: str, output_dir: Path, program: Program) -> Path | None:
    """マニフェストに記録されたパスを解決する。保存先の外を指す場合は None を返す。

    マニフェストが改ざんされても、GUI の削除などで保存先の外のファイルを触らないようにする (L4)。

    Args:
        saved_path_str: マニフェストに記録されたパス (番組ディレクトリ基準の相対パスか絶対パス)。
        output_dir: 保存先のルートディレクトリ。
        program: 対象の番組。

    Returns:
        保存先の下にある正規化したパス。保存先の外なら None。
    """
    from . import filesystem

    resolved = Path(saved_path_str)
    if not resolved.is_absolute():
        resolved = filesystem.program_output_dir(output_dir, program) / resolved
    # resolve() はパスの階層ごとに lstat を呼び、NAS では UI が固まるほど遅くなる (G13)。
    # 改ざん対策には絶対パスと `..` を弾けば足りるため、ファイルシステムに触れずに字句的に判定する
    normalized = Path(os.path.normpath(os.path.abspath(resolved)))
    root = Path(os.path.normpath(os.path.abspath(output_dir)))
    if not normalized.is_relative_to(root):
        logger.warning(f"保存先の外を指すマニフェストの記録を無視しました: {saved_path_str}")
        return None
    return normalized


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

    with _manifest_write_lock(program, output_dir):
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


def get_downloaded_episode_keys(
    output_dir: Path, program: Program, episodes: list[Episode], *, audio_only: bool = True
) -> set[str]:
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
        resolved = _resolve_manifest_path(saved_path_str, output_dir, program) if saved_path_str else None
        if resolved is not None:
            if resolved.exists():  # pragma: no cover
                if not audio_only or resolved.suffix.lower() in {".mp3", ".m4a", ".aac", ".wav"}:
                    downloaded_keys.add(episode_key)

    # ステップ 2: ディレクトリスキャン (マニフェスト未記録のエピソードのみ)
    program_dirs = filesystem._program_search_dirs(output_dir, program)
    for program_dir in program_dirs:
        files = filesystem._get_cached_glob_files(program_dir)
        for episode in episodes:
            if filesystem._episode_key(episode) in downloaded_keys:
                continue
            if any(filesystem._episode_output_matches(f, program, episode, audio_only=audio_only) for f in files):  # pragma: no cover
                downloaded_keys.add(filesystem._episode_key(episode))

    return downloaded_keys


def find_episode_downloaded_path(
    output_dir: Path, program: Program, episode: Episode, *, audio_only: bool = True
) -> Path | None:
    """保存済みエピソードのパスを検索して返す (副作用なし)。"""
    from . import filesystem

    saved_paths = _load_download_manifest(program, output_dir)
    episode_key = filesystem._episode_key(episode)

    # 1) マニフェストに記録されたパスを最優先で確認
    saved_path_str = saved_paths.get(episode_key)
    resolved = _resolve_manifest_path(saved_path_str, output_dir, program) if saved_path_str else None
    if resolved is not None:
        if resolved.exists():  # pragma: no cover
            if not audio_only or resolved.suffix.lower() in {".mp3", ".m4a", ".aac", ".wav"}:
                return resolved

    # 2) ディレクトリをスキャンして候補を探す
    for program_dir in filesystem._program_search_dirs(output_dir, program):
        candidates = filesystem._episode_output_candidates(program_dir, program, episode, audio_only=audio_only)
        if candidates:
            return candidates[0]

    return None


def is_episode_downloaded(output_dir: Path, program: Program, episode: Episode, *, audio_only: bool = True) -> bool:
    return find_episode_downloaded_path(output_dir, program, episode, audio_only=audio_only) is not None


def remove_episode_from_manifest(output_dir: Path, program: Program, episode: Episode) -> bool:
    """マニフェストから指定エピソードを削除する。"""
    from . import filesystem

    with _manifest_write_lock(program, output_dir):
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


def sync_episode_download_history(
    output_dir: Path, program: Program, episode: Episode, *, audio_only: bool = True
) -> Path | None:
    """ディスク上の実ファイルを確認し、必要に応じてマニフェストを更新する (明示的な副作用)。"""
    path = find_episode_downloaded_path(output_dir, program, episode, audio_only=audio_only)
    if path:  # pragma: no cover
        # 見つかった場合はマニフェストに反映しておく (副作用の明示化)
        mark_episode_downloaded(output_dir, program, episode, path)
    return path

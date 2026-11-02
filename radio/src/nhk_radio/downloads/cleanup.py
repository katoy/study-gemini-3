"""ダウンロードの部分削除とフォルダオープン機能。"""

import fnmatch
import logging
import subprocess
import sys
import time
from pathlib import Path

from ..types import Episode, Program
from . import filesystem

logger = logging.getLogger(__name__)

BACKUP_SUFFIX = ".nhkradio-bak"
# 起動時整理で、この秒数以内に更新された退避ファイルは DL 中とみなしてスキップする
BACKUP_MIN_AGE_SECONDS = 10.0
BACKUP_EXTENSIONS = (BACKUP_SUFFIX,)
MEDIA_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".mp4"}


def _extract_backup_orig_name(path: Path) -> str | None:
    """バックアップファイルから復元対象の元ファイル名を抽出する。

    アプリ専用接尾辞 (.nhkradio-bak) のみを対象とし、
    それ以外の一般ファイルやユーザー作成の .bak（例: memo.txt.bak, song.mp3.bak）は
    対象外 (None) とする (2-3)。
    """
    name = path.name
    if name.endswith(BACKUP_SUFFIX):
        candidate = name[: -len(BACKUP_SUFFIX)]
        if Path(candidate).suffix.lower() in MEDIA_EXTENSIONS:
            return candidate
    return None


def cleanup_partial_episode_files(output_dir: Path, program: Program, episode: Episode):
    """ダウンロード中の一時ファイル (.part, .ytdl) を削除する。"""
    for program_dir in filesystem._program_search_dirs(output_dir, program):
        if not program_dir.exists():
            continue
        filesystem._clear_file_scan_cache(program_dir)
        try:
            files = [p for p in program_dir.iterdir() if p.is_file()]
        except OSError as e:
            logger.debug(f"ディレクトリ走査に失敗: {program_dir} ({e})")
            continue
        patterns = filesystem._episode_output_patterns(program, episode)
        for path in files:
            orig_name = _extract_backup_orig_name(path)
            if orig_name is not None:
                # 前回のクラッシュ等で残った該当エピソードのバックアップを復元または掃除 (G4, 2-1)
                if any(fnmatch.fnmatch(orig_name, pattern) for pattern in patterns):
                    orig = path.with_name(orig_name)
                    try:
                        if not orig.exists():
                            path.replace(orig)
                        else:
                            path.unlink()
                    except OSError as e:
                        logger.debug(f"バックアップファイルの整理に失敗: {path} ({e})")
                continue

            is_temp = (".part" in path.name) or path.name.endswith(".ytdl")
            if is_temp and any(fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
                try:
                    path.unlink()
                except OSError as e:
                    logger.warning(f"一時ファイルの削除に失敗: {path} ({e})")


def cleanup_residual_backup_files(
    output_dir: Path,
    active_program_dirs: set[Path] | None = None,
    min_age_seconds: float = 0.0,
) -> int:
    """クラッシュ等で残されたバックアップファイルを復元または掃除する。

    ダウンロード中などのアクティブな番組ディレクトリ (active_program_dirs) は除外する (2-2)。
    また、直近に更新されたファイル (min_age_seconds 以内) は他プロセスでダウンロード中の
    可能性があるためスキップする (2-2)。
    対象はメディアファイル（.mp3, .m4a, .aac, .wav, .mp4）のバックアップに限定され、
    ユーザーが作成した一般ファイル（例: memo.txt.bak）は変更・削除されない (2-1)。

    Args:
        output_dir: 保存先ルートディレクトリ
        active_program_dirs: スキップする番組ディレクトリの集合（省略時はすべて対象）
        min_age_seconds: スキップする最小経過時間（秒、デフォルト 0.0）

    Returns:
        処理したバックアップファイルの数
    """
    if not output_dir.exists():
        return 0

    active_dirs = active_program_dirs or set()
    cleaned = 0

    try:
        candidate_dirs = [output_dir] + [p for p in output_dir.iterdir() if p.is_dir()]
    except OSError as e:
        logger.debug(f"ディレクトリ走査に失敗: {output_dir} ({e})")
        return 0

    now = time.time()
    for prog_dir in candidate_dirs:
        if prog_dir in active_dirs:
            continue
        try:
            files = [p for p in prog_dir.iterdir() if p.is_file()]
        except OSError:
            continue

        for path in files:
            orig_name = _extract_backup_orig_name(path)
            if orig_name is None:
                continue

            if min_age_seconds > 0:
                try:
                    mtime = path.stat().st_mtime
                    if now - mtime < min_age_seconds:
                        continue
                except OSError:
                    continue

            orig = path.with_name(orig_name)
            try:
                if not orig.exists():
                    path.replace(orig)
                else:
                    path.unlink()
                cleaned += 1
            except OSError as e:
                logger.debug(f"残存バックアップの整理に失敗: {path} ({e})")

    return cleaned


def open_downloaded_folder(folder_path: Path) -> bool:
    """ダウンロード済みエピソードの保存先フォルダをファイルマネージャーで開く。

    Args:
        folder_path: 開くフォルダのパス

    Returns:
        成功時 True、失敗時 False
    """
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

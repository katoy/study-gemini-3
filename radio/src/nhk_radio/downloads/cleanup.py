"""ダウンロードの部分削除とフォルダオープン機能。"""

import fnmatch
import logging
import subprocess
import sys
from pathlib import Path

from ..types import Episode, Program
from . import filesystem

logger = logging.getLogger(__name__)


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
        for path in files:
            if path.suffix in {".part", ".ytdl"} and any(
                fnmatch.fnmatch(path.name, pattern)
                for pattern in filesystem._episode_output_patterns(program, episode)
            ):
                try:
                    path.unlink()
                except OSError as e:
                    logger.warning(f"一時ファイルの削除に失敗: {path} ({e})")


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

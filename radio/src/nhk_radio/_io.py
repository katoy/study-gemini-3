"""ファイル I/O ユーティリティ（アトミック書き込みなど）。"""

import json
import os
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

# Windows でロックの取得を再試行する間隔 (秒)
_WINDOWS_LOCK_RETRY_SECONDS = 0.05

# スレッドごとに、取得済みのファイルロックの入れ子の深さを持つ
_held_file_locks = threading.local()


def atomic_write_text(path: Path, text: str) -> None:
    """テキストをアトミックに書き込む。

    Args:
        path: 書き込み先パス
        text: 書き込むテキスト
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        Path(tmp_path).replace(path)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp_path)
        raise


def atomic_write_json(path: Path, payload: dict | list, *, indent: int | None = 2) -> None:
    """JSON をアトミックに書き込む。

    Args:
        path: 書き込み先パス
        payload: JSON 化するオブジェクト
        indent: インデント幅（None で圧縮）
    """
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    atomic_write_text(path, text)


def _lock_fd(fd: int) -> None:
    """ファイル記述子に排他ロックをかける (取れるまで待つ)。"""
    if sys.platform == "win32":  # pragma: no cover - Windows でのみ通る
        import msvcrt

        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(_WINDOWS_LOCK_RETRY_SECONDS)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock_fd(fd: int) -> None:
    """ファイル記述子の排他ロックを外す。"""
    if sys.platform == "win32":  # pragma: no cover - Windows でのみ通る
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    """プロセスをまたいで排他するファイルロックを取る。

    同じスレッドで同じパスを入れ子に取得しても、自分自身を待って止まらない。
    別スレッドとの排他は、呼び出し側のスレッド用ロックと組み合わせて行う
    (ロックはプロセス単位ではなく、開いたファイルごとにかかるため別スレッドとも排他される)。

    Args:
        lock_path: ロックに使うファイルのパス。無ければ作る。

    Yields:
        None。ブロックを抜けるとロックを外す。
    """
    held: dict[str, int] = getattr(_held_file_locks, "depth", None) or {}
    _held_file_locks.depth = held
    key = os.path.abspath(lock_path)
    if held.get(key, 0) > 0:
        held[key] += 1
        try:
            yield
        finally:
            held[key] -= 1
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        _lock_fd(fd)
        held[key] = 1
        try:
            yield
        finally:
            held[key] = 0
            _unlock_fd(fd)
    finally:
        os.close(fd)

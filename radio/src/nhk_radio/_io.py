"""ファイル I/O ユーティリティ（アトミック書き込みなど）。"""

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path


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

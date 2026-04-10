"""
utils/download.py
=================
タイムアウト付きファイルダウンロードユーティリティ。
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from pathlib import Path

_DEFAULT_TIMEOUT = 60  # 秒（長時間ハングを防ぐため短めに設定）


def verify_hash(path: Path, expected_sha256: str) -> bool:
    """ファイルの SHA256 ハッシュを検証する。"""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest() == expected_sha256


def download_file(
    url: str,
    dest: Path,
    timeout: int = _DEFAULT_TIMEOUT,
    expected_sha256: str | None = None,
) -> None:
    """url を dest にダウンロードする（タイムアウト・ハッシュ検証付き）。

    Args:
        url: ダウンロード元 URL。
        dest: 保存先パス。
        timeout: 接続・読み取りタイムアウト（秒）。デフォルト 60 秒。
        expected_sha256: 期待する SHA256 ハッシュ値。指定時はダウンロード後に検証し、
            不一致の場合はファイルを削除して ValueError を送出する。
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = response.read()
    except TimeoutError as e:
        raise TimeoutError(
            f"ダウンロードが {timeout} 秒でタイムアウトしました: {url}"
        ) from e
    except urllib.error.URLError as e:
        raise IOError(f"ダウンロードに失敗しました: {url}") from e

    try:
        dest.write_bytes(data)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    if expected_sha256 is not None:
        sha256 = hashlib.sha256(data).hexdigest()
        if sha256 != expected_sha256:
            dest.unlink(missing_ok=True)
            raise ValueError(
                f"ダウンロードファイルのハッシュが一致しません: {dest.name}\n"
                f"  期待値: {expected_sha256}\n"
                f"  実際値: {sha256}"
            )

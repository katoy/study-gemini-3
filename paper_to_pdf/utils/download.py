"""
utils/download.py
=================
タイムアウト付きファイルダウンロードユーティリティ。
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

_DEFAULT_TIMEOUT = 300  # 秒


def download_file(url: str, dest: Path, timeout: int = _DEFAULT_TIMEOUT) -> None:
    """url を dest にダウンロードする（タイムアウト付き）。

    Args:
        url: ダウンロード元 URL。
        dest: 保存先パス。
        timeout: 接続・読み取りタイムアウト（秒）。デフォルト 300 秒。
    """
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = response.read()
    dest.write_bytes(data)

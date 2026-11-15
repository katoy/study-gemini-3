"""レビュー G13（UI スレッドでのファイル I/O）の回帰テスト。"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from nhk_radio.downloads import manifest
from nhk_radio.types import Program

PROGRAM = Program(title="番組A", display_title="番組A", display_date="", site_id="SITE", corner_id="01", url="U")


def _count_fs_calls(func) -> int:
    """func を実行し、その間の os.stat / os.lstat の呼び出し回数を返す。"""
    calls = 0
    real_stat, real_lstat = os.stat, os.lstat

    def counting_stat(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_stat(*args, **kwargs)

    def counting_lstat(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_lstat(*args, **kwargs)

    with patch("os.stat", counting_stat), patch("os.lstat", counting_lstat):
        func()
    return calls


def test_resolve_manifest_path_does_not_touch_filesystem(tmp_path: Path) -> None:
    """パス検証は字句的に行い、ファイルシステムに問い合わせない (NAS で UI が固まらないように)。"""
    calls = _count_fs_calls(lambda: manifest._resolve_manifest_path("a/b/c.mp3", tmp_path, PROGRAM))
    assert calls == 0


@pytest.mark.parametrize("saved", ["../../victim.mp3", "sub/../../../victim.mp3", "/etc/passwd"])
def test_resolve_manifest_path_rejects_outside(tmp_path: Path, saved: str) -> None:
    """字句的な検証でも、`..` や保存先の外の絶対パスは弾く。"""
    assert manifest._resolve_manifest_path(saved, tmp_path / "out", PROGRAM) is None


def test_resolve_manifest_path_accepts_inside_with_dotdot(tmp_path: Path) -> None:
    """`..` を含んでも、正規化して保存先の下に収まるパスは受け付ける。"""
    output_dir = tmp_path / "out"
    resolved = manifest._resolve_manifest_path("sub/../a.mp3", output_dir, PROGRAM)
    assert resolved == output_dir / "SITE_01" / "a.mp3"


def test_resolve_manifest_path_with_relative_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """保存先が相対パス (既定の ./downloads など) でも正しく判定する。"""
    monkeypatch.chdir(tmp_path)
    assert manifest._resolve_manifest_path("a.mp3", Path("downloads"), PROGRAM) is not None
    assert manifest._resolve_manifest_path("../../../x.mp3", Path("downloads"), PROGRAM) is None

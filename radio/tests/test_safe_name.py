"""レビュー L5（`_safe_name`）の回帰テスト。"""

import pytest

from nhk_radio import text
from nhk_radio.text import SAFE_NAME_MAX_BYTES


@pytest.mark.parametrize("name", ["CON", "con", "PRN", "AUX", "NUL", "COM1", "com9", "LPT1", "LPT9"])
def test_safe_name_avoids_windows_reserved_names(name: str) -> None:
    """Windows の予約名は、末尾に `_` を付けて避ける。"""
    assert text._safe_name(name) == f"{name}_"


def test_safe_name_avoids_reserved_name_with_extension() -> None:
    """拡張子の付いた予約名 (NUL.txt など) も Windows では使えないため避ける。"""
    assert text._safe_name("NUL.txt") == "NUL_.txt"


@pytest.mark.parametrize("name", ["CONSOLE", "COM10", "LPT0", "番組CON", "CON番組"])
def test_safe_name_keeps_names_that_only_contain_reserved_words(name: str) -> None:
    """予約名そのものでない名前は変えない。"""
    assert text._safe_name(name) == name


def test_safe_name_replaces_control_characters() -> None:
    """制御文字 (改行・タブ・NUL など) は `_` に置き換える。"""
    assert text._safe_name("番組\nA\tB\x00C\x7f") == "番組_A_B_C_"


def test_safe_name_truncates_to_max_bytes_on_char_boundary() -> None:
    """UTF-8 で上限バイト数を超える名前は、文字の途中で切らずに詰める。"""
    # 「あ」は UTF-8 で 3 バイト
    name = "あ" * 100
    result = text._safe_name(name)

    assert len(result.encode("utf-8")) <= SAFE_NAME_MAX_BYTES
    assert result == "あ" * (SAFE_NAME_MAX_BYTES // 3)


def test_safe_name_keeps_name_within_max_bytes() -> None:
    """上限ちょうどの名前は変えない。"""
    name = "a" * SAFE_NAME_MAX_BYTES
    assert text._safe_name(name) == name


def test_safe_name_strips_trailing_dot_after_truncation() -> None:
    """詰めた結果の末尾がドットや空白になっても、Windows で使えるよう取り除く。"""
    name = "a" * (SAFE_NAME_MAX_BYTES - 1) + ".b"
    assert text._safe_name(name) == "a" * (SAFE_NAME_MAX_BYTES - 1)


def test_safe_name_keeps_ordinary_names() -> None:
    """普通の名前は従来どおりの結果になる (既存の保存先・ファイル名との照合を保つ)。"""
    assert text._safe_name("番組A") == "番組A"
    assert text._safe_name("番組/A:B") == "番組_A_B"
    assert text._safe_name("　番組A　") == "番組A"

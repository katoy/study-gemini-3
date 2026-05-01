"""kindle_capture モジュールのユニットテスト。"""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from kindle_capture import (
    _calculate_md5,
    _extract_title,
    _get_chrome_executable,
    _is_port_open,
    find_free_port,
    sanitize_filename,
)


class TestSanitizeFilename:
    """sanitize_filename のテスト。"""

    def test_normal_name(self):
        assert sanitize_filename("my_book") == "my_book"

    def test_removes_invalid_chars(self):
        assert sanitize_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"

    def test_collapses_consecutive_underscores(self):
        assert sanitize_filename("a<<<b") == "a_b"

    def test_strips_leading_trailing_underscores(self):
        assert sanitize_filename("***name***") == "name"

    def test_truncates_to_80_chars(self):
        long_name = "a" * 100
        result = sanitize_filename(long_name)
        assert len(result) == 80

    def test_empty_string_returns_default(self):
        assert sanitize_filename("***") == "kindle_book"

    def test_newlines_and_tabs(self):
        assert sanitize_filename("hello\nworld\ttab") == "hello_world_tab"


class TestExtractTitle:
    """_extract_title のテスト。"""

    def test_removes_kindle_cloud_reader(self):
        assert _extract_title("My Book - Kindle Cloud Reader") == "My Book"

    def test_plain_title(self):
        assert _extract_title("Some Title") == "Some Title"

    def test_only_kindle_cloud_reader(self):
        assert _extract_title("Kindle Cloud Reader") == "kindle_book"

    def test_title_with_special_chars(self):
        result = _extract_title('Book: "Subtitle" - Kindle Cloud Reader')
        assert ":" not in result
        assert '"' not in result


class TestGetChromeExecutable:
    """_get_chrome_executable のテスト。"""

    @patch("kindle_capture.platform.system", return_value="Darwin")
    def test_macos(self, _mock):
        path = _get_chrome_executable()
        assert "Google Chrome" in path
        assert "MacOS" in path

    @patch("kindle_capture.platform.system", return_value="Linux")
    def test_linux(self, _mock):
        assert _get_chrome_executable() == "google-chrome"

    @patch("kindle_capture.platform.system", return_value="Windows")
    def test_windows(self, _mock):
        path = _get_chrome_executable()
        assert "chrome.exe" in path


class TestFindFreePort:
    """find_free_port のテスト。"""

    def test_returns_valid_port(self):
        port = find_free_port()
        assert 1024 <= port <= 65535

    def test_returns_different_ports(self):
        ports = {find_free_port() for _ in range(5)}
        assert len(ports) >= 2


class TestIsPortOpen:
    """_is_port_open のテスト。"""

    def test_closed_port(self):
        assert _is_port_open(1, timeout=0.1) is False


class TestCalculateMd5:
    """_calculate_md5 のテスト。"""

    def test_known_content(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"hello world")
            tmp = Path(f.name)
        try:
            result = _calculate_md5(tmp)
            expected = hashlib.md5(b"hello world").hexdigest()
            assert result == expected
        finally:
            tmp.unlink()

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            tmp = Path(f.name)
        try:
            result = _calculate_md5(tmp)
            expected = hashlib.md5(b"").hexdigest()
            assert result == expected
        finally:
            tmp.unlink()

    def test_different_content_different_hash(self):
        paths = []
        try:
            for content in [b"aaa", b"bbb"]:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
                    f.write(content)
                    paths.append(Path(f.name))
            assert _calculate_md5(paths[0]) != _calculate_md5(paths[1])
        finally:
            for p in paths:
                p.unlink()

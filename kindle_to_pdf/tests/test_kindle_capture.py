"""kindle_capture モジュールのユニットテスト。"""

import asyncio
import hashlib
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import kindle_capture
from kindle_capture import (
    _calculate_md5,
    _capture_all_pages,
    _extract_title,
    _get_chrome_executable,
    _is_port_open,
    _tail_log,
    _terminate_process,
    _wait_for_page_stable,
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


class TestTailLog:
    """_tail_log のテスト。"""

    def test_missing_file_returns_diagnostic(self, tmp_path):
        result = _tail_log(tmp_path / "does_not_exist.log")
        assert "stderr ログ読み取り失敗" in result

    def test_empty_file_returns_marker(self, tmp_path):
        log = tmp_path / "empty.log"
        log.write_bytes(b"")
        assert _tail_log(log) == "(空)"

    def test_small_file_returned_in_full(self, tmp_path):
        log = tmp_path / "small.log"
        log.write_text("hello\nworld\n")
        assert _tail_log(log) == "hello\nworld\n"

    def test_large_file_truncated_to_max_bytes(self, tmp_path):
        log = tmp_path / "big.log"
        # 8KB の英数字。先頭は捨てられ末尾だけが返るはず。
        content = ("a" * 4000) + ("b" * 4000)
        log.write_text(content)
        result = _tail_log(log, max_bytes=4096)
        assert len(result) == 4096
        # 末尾は "b"、先頭の "a" は切り捨てられる
        assert result.endswith("b")
        assert "a" * 4000 not in result

    def test_invalid_utf8_replaced(self, tmp_path):
        log = tmp_path / "binary.log"
        log.write_bytes(b"\xff\xfe\xfd valid_part")
        result = _tail_log(log)
        assert "valid_part" in result


class TestTerminateProcess:
    """_terminate_process のテスト。"""

    def test_already_terminated_is_noop(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = 0  # 既に終了
        _terminate_process(proc)
        proc.terminate.assert_not_called()
        proc.kill.assert_not_called()
        proc.wait.assert_not_called()

    def test_terminate_succeeds(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None  # 起動中
        proc.wait.return_value = 0
        _terminate_process(proc, timeout=1.0)
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=1.0)
        proc.kill.assert_not_called()

    def test_falls_back_to_kill_on_timeout(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        # 1 回目の wait はタイムアウト、2 回目（kill 後）は成功
        proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=1.0), 0]
        _terminate_process(proc, timeout=1.0)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        assert proc.wait.call_count == 2

    def test_logs_error_when_kill_also_times_out(self, caplog):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.pid = 12345
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=1.0),
            subprocess.TimeoutExpired(cmd="x", timeout=1.0),
        ]
        with caplog.at_level("ERROR", logger="kindle_capture"):
            _terminate_process(proc, timeout=1.0)
        assert any("終了に失敗" in rec.message for rec in caplog.records)


class TestWaitForPageStable:
    """_wait_for_page_stable のテスト。bool を返すことを検証する。"""

    def test_returns_true_when_screenshots_match(self):
        page = MagicMock()
        page.screenshot = AsyncMock(return_value=b"same_bytes")

        result = asyncio.run(_wait_for_page_stable(page, check_interval=0.01, stable_checks=2, timeout=2.0))
        assert result is True

    def test_returns_false_on_timeout(self):
        page = MagicMock()
        # 毎回違う画像を返すので安定検知は永遠に成立しない
        counter = {"i": 0}

        async def screenshot(*_args, **_kwargs):
            counter["i"] += 1
            return f"frame_{counter['i']}".encode()

        page.screenshot = screenshot

        result = asyncio.run(_wait_for_page_stable(page, check_interval=0.01, stable_checks=2, timeout=0.1))
        assert result is False

    def test_returns_false_on_screenshot_exception(self):
        page = MagicMock()
        page.screenshot = AsyncMock(side_effect=RuntimeError("disconnected"))
        result = asyncio.run(_wait_for_page_stable(page, check_interval=0.01, stable_checks=2, timeout=2.0))
        assert result is False


class TestCaptureAllPagesMaxPages:
    """_capture_all_pages の暴走防止 (MAX_PAGES) のテスト。"""

    def test_stops_at_max_pages_cap(self, tmp_path, caplog, monkeypatch):
        """終端が永遠に検出されないケースで MAX_PAGES に達したら停止することを確認。"""
        # テストを高速化するため、MAX_PAGES を小さい値に差し替える
        monkeypatch.setattr(kindle_capture, "MAX_PAGES", 3)

        page = MagicMock()
        # 毎回異なる PNG を生成（ハッシュが毎回変わる → 終端は検出されない）
        counter = {"i": 0}

        async def fake_screenshot(*, path=None, full_page=False):
            if path is not None:
                counter["i"] += 1
                Path(path).write_bytes(f"png_data_{counter['i']}".encode())
                return None
            return f"bytes_{counter['i']}".encode()

        page.screenshot = fake_screenshot
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()

        # _wait_for_page_stable はテスト時間短縮のため即時 True を返す
        async def stable_stub(*_a, **_kw):
            return True

        monkeypatch.setattr(kindle_capture, "_wait_for_page_stable", stable_stub)

        with caplog.at_level("WARNING", logger="kindle_capture"):
            screenshots = asyncio.run(_capture_all_pages(page, tmp_path, page_delay=0.0))

        assert len(screenshots) == 3
        assert any("上限" in rec.message for rec in caplog.records)

    def test_capture_failure_propagates(self, tmp_path, monkeypatch):
        """screenshot が例外を投げたら ERROR ログとともに再 raise される。"""
        page = MagicMock()
        page.screenshot = AsyncMock(side_effect=RuntimeError("browser crashed"))
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()

        async def stable_stub(*_a, **_kw):
            return True

        monkeypatch.setattr(kindle_capture, "_wait_for_page_stable", stable_stub)

        with pytest.raises(RuntimeError, match="browser crashed"):
            asyncio.run(_capture_all_pages(page, tmp_path, page_delay=0.0))

    def test_normal_end_detection(self, tmp_path, monkeypatch):
        """同一ハッシュが MAX_SAME_PAGES 連続したら終端と判定して停止する。"""
        monkeypatch.setattr(kindle_capture, "MAX_SAME_PAGES", 2)

        # 2 ページ撮ったあと、同じ画像を返し続けて終端を演出
        seq = [b"a", b"b", b"end", b"end", b"end"]
        idx = {"i": 0}

        async def fake_screenshot(*, path=None, full_page=False):
            data = seq[idx["i"]]
            idx["i"] += 1
            if path is not None:
                Path(path).write_bytes(data)
            return data

        page = MagicMock()
        page.screenshot = fake_screenshot
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()

        async def stable_stub(*_a, **_kw):
            return True

        monkeypatch.setattr(kindle_capture, "_wait_for_page_stable", stable_stub)

        screenshots = asyncio.run(_capture_all_pages(page, tmp_path, page_delay=0.0))
        # 異なるハッシュ "a", "b", "end" まで取り込まれる（"end" は最初の 1 回だけスクショとして残る）
        assert len(screenshots) == 3

    def test_progress_line_used_when_tty(self, tmp_path, monkeypatch, capsys):
        """sys.stderr.isatty() が True のときは print による進捗表示が使われる。"""
        monkeypatch.setattr(kindle_capture, "MAX_SAME_PAGES", 2)
        monkeypatch.setattr(kindle_capture.sys.stderr, "isatty", lambda: True)

        seq = [b"a", b"end", b"end", b"end", b"end"]
        idx = {"i": 0}

        async def fake_screenshot(*, path=None, full_page=False):
            data = seq[idx["i"]]
            idx["i"] += 1
            if path is not None:
                Path(path).write_bytes(data)
            return data

        page = MagicMock()
        page.screenshot = fake_screenshot
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()

        async def stable_stub(*_a, **_kw):
            return True

        monkeypatch.setattr(kindle_capture, "_wait_for_page_stable", stable_stub)

        asyncio.run(_capture_all_pages(page, tmp_path, page_delay=0.0))
        captured = capsys.readouterr()
        assert "キャプチャ中" in captured.out

    def test_warns_on_stable_timeout(self, tmp_path, monkeypatch, caplog):
        """_wait_for_page_stable が False を返したら WARNING が出る。"""
        monkeypatch.setattr(kindle_capture, "MAX_SAME_PAGES", 2)

        seq = [b"a", b"b", b"end", b"end"]
        idx = {"i": 0}

        async def fake_screenshot(*, path=None, full_page=False):
            data = seq[min(idx["i"], len(seq) - 1)]
            idx["i"] += 1
            if path is not None:
                Path(path).write_bytes(data)
            return data

        page = MagicMock()
        page.screenshot = fake_screenshot
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()

        async def stable_stub(*_a, **_kw):
            return False  # 常にタイムアウト扱い

        monkeypatch.setattr(kindle_capture, "_wait_for_page_stable", stable_stub)

        with caplog.at_level("WARNING", logger="kindle_capture"):
            asyncio.run(_capture_all_pages(page, tmp_path, page_delay=0.0))
        assert any("安定検知がタイムアウト" in rec.message for rec in caplog.records)


class TestIsPortOpenSuccess:
    """_is_port_open の成功パス。"""

    def test_open_port_detected(self):
        # 一時的にローカルポートをバインドして listen 状態にする
        with __import__("socket").socket() as sock:
            sock.bind(("localhost", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            assert _is_port_open(port, timeout=1.0) is True


class TestGetChromeExecutableWindowsExisting:
    """Windows の Chrome 検出で実在パスを返す分岐をテスト。"""

    def test_windows_returns_first_existing(self, monkeypatch):
        monkeypatch.setattr(kindle_capture.platform, "system", lambda: "Windows")
        # candidates の先頭パスのみ存在することにする
        from pathlib import Path as _Path

        original_exists = _Path.exists

        def fake_exists(self):
            return str(self) == r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        monkeypatch.setattr(_Path, "exists", fake_exists)
        try:
            result = _get_chrome_executable()
            assert result == r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        finally:
            monkeypatch.setattr(_Path, "exists", original_exists)


class TestConnectToChromeFailure:
    """_connect_to_chrome の例外パス（OS 別）。"""

    @pytest.mark.parametrize(
        "os_name,expected_substr",
        [
            ("Darwin", "Google\\ Chrome.app"),
            ("Windows", "chrome.exe"),
            ("Linux", "google-chrome"),
        ],
    )
    def test_raises_runtime_error_with_chrome_command(self, monkeypatch, os_name, expected_substr):
        from kindle_capture import _connect_to_chrome

        class FailingPlaywright:
            class chromium:
                @staticmethod
                async def connect_over_cdp(_url):
                    raise ConnectionRefusedError("nope")

        monkeypatch.setattr(kindle_capture.platform, "system", lambda: os_name)

        with pytest.raises(RuntimeError, match="Chrome に接続できません") as excinfo:
            asyncio.run(_connect_to_chrome(FailingPlaywright(), "http://localhost:9999"))
        assert expected_substr in str(excinfo.value)
        assert excinfo.value.__cause__ is not None  # raise ... from e のチェーン


class TestFindKindleTab:
    """_find_kindle_tab のテスト。"""

    def _make_browser(self, urls):
        contexts = []

        def _ctx(page_urls):
            ctx = MagicMock()
            pages = []
            for u in page_urls:
                p = MagicMock()
                p.url = u
                pages.append(p)
            ctx.pages = pages
            return ctx

        contexts.append(_ctx(urls))
        browser = MagicMock()
        browser.contexts = contexts
        return browser

    def test_picks_asin_page(self):
        from kindle_capture import _find_kindle_tab

        browser = self._make_browser(
            [
                "https://www.google.com/",
                "https://read.amazon.co.jp/landing",
                "https://read.amazon.co.jp/?asin=B000",
            ]
        )
        page = _find_kindle_tab(browser)
        assert "asin=" in page.url

    def test_picks_reading_page(self):
        from kindle_capture import _find_kindle_tab

        browser = self._make_browser(
            [
                "https://read.amazon.co.jp/landing",
                "https://read.amazon.co.jp/reading?id=1",
            ]
        )
        page = _find_kindle_tab(browser)
        assert "reading" in page.url

    def test_falls_back_to_last_kindle_page(self):
        from kindle_capture import _find_kindle_tab

        browser = self._make_browser(
            [
                "https://read.amazon.co.jp/page1",
                "https://read.amazon.co.jp/page2",
            ]
        )
        page = _find_kindle_tab(browser)
        assert page.url.endswith("page2")

    def test_raises_with_url_listing(self):
        from kindle_capture import _find_kindle_tab

        browser = self._make_browser(["https://www.google.com/", "https://example.com/"])
        with pytest.raises(RuntimeError, match="Kindle Cloud Reader のタブが見つかりません"):
            _find_kindle_tab(browser)

    def test_raises_when_no_tabs(self):
        from kindle_capture import _find_kindle_tab

        browser = MagicMock()
        browser.contexts = []
        with pytest.raises(RuntimeError, match="タブなし"):
            _find_kindle_tab(browser)


class TestFocusReader:
    """_focus_reader のテスト。"""

    def test_success(self):
        from kindle_capture import _focus_reader

        page = MagicMock()
        page.bring_to_front = AsyncMock()
        page.focus = AsyncMock()
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()
        # 例外なく完走することを確認
        asyncio.run(_focus_reader(page))
        assert page.keyboard.press.await_count == 2

    def test_swallows_exception(self, caplog):
        from kindle_capture import _focus_reader

        page = MagicMock()
        page.bring_to_front = AsyncMock(side_effect=RuntimeError("disconnected"))
        with caplog.at_level("DEBUG", logger="kindle_capture"):
            asyncio.run(_focus_reader(page))  # 例外を投げない
        assert any("リーダーへのフォーカス" in rec.message for rec in caplog.records)


class TestLaunchChrome:
    """launch_chrome のテスト。"""

    def test_raises_when_chrome_not_found(self, monkeypatch, tmp_path):
        from kindle_capture import launch_chrome

        monkeypatch.setattr(kindle_capture, "_get_chrome_executable", lambda: str(tmp_path / "missing"))
        monkeypatch.setattr(kindle_capture.platform, "system", lambda: "Darwin")
        with pytest.raises(FileNotFoundError, match="Chrome が見つかりません"):
            launch_chrome(cdp_port=12345, user_data_dir=str(tmp_path))

    def test_success_after_port_opens(self, monkeypatch, tmp_path):
        from kindle_capture import launch_chrome

        # 実在するダミー実行ファイル
        fake_chrome = tmp_path / "chrome"
        fake_chrome.write_text("#!/bin/sh\nsleep 60\n")
        fake_chrome.chmod(0o755)

        monkeypatch.setattr(kindle_capture, "_get_chrome_executable", lambda: str(fake_chrome))

        proc_mock = MagicMock()
        proc_mock.poll.return_value = None
        monkeypatch.setattr(kindle_capture.subprocess, "Popen", lambda *a, **kw: proc_mock)
        monkeypatch.setattr(kindle_capture, "_is_port_open", lambda port, timeout=1.0: True)
        monkeypatch.setattr(kindle_capture.time, "sleep", lambda _s: None)

        result = launch_chrome(cdp_port=12345, user_data_dir=str(tmp_path), initial_url="https://example.com")
        assert result is proc_mock

    def test_raises_when_proc_exits_early(self, monkeypatch, tmp_path):
        from kindle_capture import launch_chrome

        fake_chrome = tmp_path / "chrome"
        fake_chrome.write_text("#!/bin/sh\nexit 1\n")
        fake_chrome.chmod(0o755)

        monkeypatch.setattr(kindle_capture, "_get_chrome_executable", lambda: str(fake_chrome))

        proc_mock = MagicMock()
        proc_mock.poll.return_value = 1  # 即時 exit
        proc_mock.returncode = 1

        # stderr ログにメッセージを残しておく
        def fake_popen(cmd, stdout=None, stderr=None, **kw):
            if hasattr(stderr, "write"):
                stderr.write("crash log content\n")
                stderr.flush()
            return proc_mock

        monkeypatch.setattr(kindle_capture.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(kindle_capture, "_is_port_open", lambda port, timeout=1.0: False)
        monkeypatch.setattr(kindle_capture.time, "sleep", lambda _s: None)

        with pytest.raises(RuntimeError, match="exit code 1"):
            launch_chrome(cdp_port=12345, user_data_dir=str(tmp_path))

    def test_raises_on_port_timeout(self, monkeypatch, tmp_path):
        from kindle_capture import launch_chrome

        fake_chrome = tmp_path / "chrome"
        fake_chrome.write_text("#!/bin/sh\nsleep 60\n")
        fake_chrome.chmod(0o755)

        monkeypatch.setattr(kindle_capture, "_get_chrome_executable", lambda: str(fake_chrome))

        proc_mock = MagicMock()
        proc_mock.poll.return_value = None
        proc_mock.wait.return_value = 0
        monkeypatch.setattr(kindle_capture.subprocess, "Popen", lambda *a, **kw: proc_mock)
        monkeypatch.setattr(kindle_capture, "_is_port_open", lambda port, timeout=1.0: False)
        # CHROME_LAUNCH_TIMEOUT を即座に超過させる
        monkeypatch.setattr(kindle_capture, "CHROME_LAUNCH_TIMEOUT", 0.0)
        monkeypatch.setattr(kindle_capture.time, "sleep", lambda _s: None)

        with pytest.raises(RuntimeError, match="応答しませんでした"):
            launch_chrome(cdp_port=12345, user_data_dir=str(tmp_path))

    def test_polls_until_port_opens(self, monkeypatch, tmp_path):
        """ポートが開くまで sleep を挟みつつポーリングするパス。"""
        from kindle_capture import launch_chrome

        fake_chrome = tmp_path / "chrome"
        fake_chrome.write_text("#!/bin/sh\nsleep 60\n")
        fake_chrome.chmod(0o755)
        monkeypatch.setattr(kindle_capture, "_get_chrome_executable", lambda: str(fake_chrome))

        proc_mock = MagicMock()
        proc_mock.poll.return_value = None
        monkeypatch.setattr(kindle_capture.subprocess, "Popen", lambda *a, **kw: proc_mock)

        # 最初の 2 回は閉じている → 3 回目に開く
        port_states = iter([False, False, True])
        monkeypatch.setattr(kindle_capture, "_is_port_open", lambda port, timeout=1.0: next(port_states))

        sleep_calls = []
        monkeypatch.setattr(kindle_capture.time, "sleep", lambda s: sleep_calls.append(s))

        result = launch_chrome(cdp_port=12345, user_data_dir=str(tmp_path))
        assert result is proc_mock
        assert sleep_calls  # time.sleep が少なくとも 1 回呼ばれた

    def test_creates_temp_user_data_dir_when_none(self, monkeypatch, tmp_path):
        from kindle_capture import launch_chrome

        fake_chrome = tmp_path / "chrome"
        fake_chrome.write_text("#!/bin/sh\nsleep 60\n")
        fake_chrome.chmod(0o755)

        monkeypatch.setattr(kindle_capture, "_get_chrome_executable", lambda: str(fake_chrome))

        captured_cmd = {}

        def fake_popen(cmd, stdout=None, stderr=None, **kw):
            captured_cmd["cmd"] = cmd
            m = MagicMock()
            m.poll.return_value = None
            return m

        monkeypatch.setattr(kindle_capture.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(kindle_capture, "_is_port_open", lambda port, timeout=1.0: True)
        monkeypatch.setattr(kindle_capture.time, "sleep", lambda _s: None)

        launch_chrome(cdp_port=12345, user_data_dir=None)
        assert any("--user-data-dir=" in arg for arg in captured_cmd["cmd"])


class TestCaptureKindlePages:
    """capture_kindle_pages のテスト。Playwright を完全モック。"""

    def test_full_flow(self, tmp_path, monkeypatch):
        from kindle_capture import capture_kindle_pages

        # ページのモック
        page = MagicMock()
        page.url = "https://read.amazon.co.jp/?asin=B000"
        page.title = AsyncMock(return_value="My Book - Kindle Cloud Reader")
        page.bring_to_front = AsyncMock()
        page.focus = AsyncMock()
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()

        seq = [b"a", b"b", b"end", b"end", b"end"]
        idx = {"i": 0}

        async def fake_screenshot(*, path=None, full_page=False):
            data = seq[min(idx["i"], len(seq) - 1)]
            idx["i"] += 1
            if path is not None:
                Path(path).write_bytes(data)
            return data

        page.screenshot = fake_screenshot

        ctx = MagicMock()
        ctx.pages = [page]
        browser = MagicMock()
        browser.contexts = [ctx]
        browser.close = AsyncMock()

        # async_playwright のコンテキストマネージャ
        class FakePW:
            class chromium:
                @staticmethod
                async def connect_over_cdp(_url):
                    return browser

        class FakeAsyncPW:
            async def __aenter__(self):
                return FakePW()

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(kindle_capture, "async_playwright", lambda: FakeAsyncPW())
        monkeypatch.setattr(kindle_capture, "MAX_SAME_PAGES", 2)
        monkeypatch.setattr(kindle_capture.asyncio, "sleep", AsyncMock())

        async def stable_stub(*_a, **_kw):
            return True

        monkeypatch.setattr(kindle_capture, "_wait_for_page_stable", stable_stub)

        title, screenshots = asyncio.run(capture_kindle_pages(str(tmp_path), cdp_url="http://x"))
        assert title == "My Book"
        assert len(screenshots) == 3
        browser.close.assert_awaited()

    def test_book_dir_collision_appends_counter(self, tmp_path, monkeypatch):
        """同名ディレクトリが既にあるとき _2, _3 とサフィックスを付ける。"""
        from kindle_capture import capture_kindle_pages

        # 既存ディレクトリを作る（sanitize_filename はスペースを残すので "My Book"）
        (tmp_path / "My Book").mkdir()
        (tmp_path / "My Book_2").mkdir()

        page = MagicMock()
        page.url = "https://read.amazon.co.jp/?asin=B000"
        page.title = AsyncMock(return_value="My Book - Kindle Cloud Reader")
        page.bring_to_front = AsyncMock()
        page.focus = AsyncMock()
        page.keyboard = MagicMock()
        page.keyboard.press = AsyncMock()
        # 即座に終端検出
        page.screenshot = AsyncMock(return_value=b"end")

        async def fake_screenshot_path(*, path=None, full_page=False):
            if path is not None:
                Path(path).write_bytes(b"end")
            return b"end"

        page.screenshot = fake_screenshot_path

        ctx = MagicMock()
        ctx.pages = [page]
        browser = MagicMock()
        browser.contexts = [ctx]
        browser.close = AsyncMock()

        class FakePW:
            class chromium:
                @staticmethod
                async def connect_over_cdp(_url):
                    return browser

        class FakeAsyncPW:
            async def __aenter__(self):
                return FakePW()

            async def __aexit__(self, *exc):
                return False

        monkeypatch.setattr(kindle_capture, "async_playwright", lambda: FakeAsyncPW())
        monkeypatch.setattr(kindle_capture, "MAX_SAME_PAGES", 1)
        monkeypatch.setattr(kindle_capture.asyncio, "sleep", AsyncMock())

        async def stable_stub(*_a, **_kw):
            return True

        monkeypatch.setattr(kindle_capture, "_wait_for_page_stable", stable_stub)

        asyncio.run(capture_kindle_pages(str(tmp_path), cdp_url="http://x"))
        # 衝突を避けて "My Book_3" が作られているはず
        assert (tmp_path / "My Book_3").exists()

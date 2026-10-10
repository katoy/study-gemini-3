import hashlib
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, call, patch
import pytest

import kindle_capture
from kindle_capture import (
    KINDLE_APP_NAMES,
    MAX_SAME_PAGES,
    MacKindleCapturer,
    _calculate_md5,
    _escape_applescript_string,
    capture_kindle_pages,
    sanitize_filename,
)


def test_sanitize_filename() -> None:
    """sanitize_filename: 特殊文字の置換、連続アンダースコア、80文字切り詰め、空文字デフォルト。"""
    assert sanitize_filename('Invalid:<File>"Name"?') == "Invalid_File_Name"
    assert sanitize_filename("___Multiple___Underscores___") == "Multiple_Underscores"
    long_name = "a" * 100
    assert len(sanitize_filename(long_name)) == 80
    assert sanitize_filename("") == "kindle_book"
    assert sanitize_filename("   ") == "kindle_book"
    assert sanitize_filename("___") == "kindle_book"


def test_escape_applescript_string() -> None:
    """_escape_applescript_string: バックスラッシュとダブルクォートのエスケープ。"""
    raw = r'Hello "World" \ Backslash'
    escaped = _escape_applescript_string(raw)
    assert escaped == r'Hello \"World\" \\ Backslash'


def test_calculate_md5(tmp_path: Path) -> None:
    """_calculate_md5: 複数チャンクの MD5 ハッシュ計算。"""
    test_file = tmp_path / "test.bin"
    content = b"x" * 10000  # 4096 bytes chunk を超えるデータ
    test_file.write_bytes(content)

    expected = hashlib.md5(content).hexdigest()
    assert _calculate_md5(test_file) == expected


class TestMacKindleCapturer:
    """MacKindleCapturer のテスト。"""

    def test_run_applescript_success(self) -> None:
        capturer = MacKindleCapturer()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="  Success Output  \n")
            out = capturer._run_applescript("test script")
            assert out == "Success Output"
            mock_run.assert_called_once_with(["osascript", "-e", "test script"], capture_output=True, text=True)

    def test_run_applescript_failure(self) -> None:
        capturer = MacKindleCapturer()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Something broke")
            with pytest.raises(RuntimeError, match="AppleScript エラー: Something broke"):
                capturer._run_applescript("bad script")

    def test_find_and_activate_kindle_first_succeeds(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript") as mock_as, \
             patch.object(capturer, "_find_kindle_process_name", return_value="Kindle"):
            mock_as.return_value = ""
            app_name, proc_name = capturer._find_and_activate_kindle()
            assert app_name == KINDLE_APP_NAMES[0]
            assert proc_name == "Kindle"

    def test_find_and_activate_kindle_second_succeeds(self) -> None:
        capturer = MacKindleCapturer()
        # 1 つ目のアプリ名 ("Kindle") の activate で RuntimeError, 2 つ目 ("Amazon Kindle") で成功
        def fake_applescript(script: str) -> str:
            if f'tell application "{KINDLE_APP_NAMES[0]}" to activate' in script:
                raise RuntimeError("not found")
            return ""

        with patch.object(capturer, "_run_applescript", side_effect=fake_applescript), \
             patch.object(capturer, "_find_kindle_process_name", return_value="Amazon Kindle"):
            app_name, proc_name = capturer._find_and_activate_kindle()
            assert app_name == KINDLE_APP_NAMES[1]
            assert proc_name == "Amazon Kindle"

    def test_find_and_activate_kindle_all_fail(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript", side_effect=RuntimeError("none")):
            with pytest.raises(RuntimeError, match="Kindle アプリが見つかりません"):
                capturer._find_and_activate_kindle()

    def test_find_kindle_process_name(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript", return_value="KindleProcess"):
            assert capturer._find_kindle_process_name() == "KindleProcess"

        with patch.object(capturer, "_run_applescript", return_value=""):
            with pytest.raises(RuntimeError, match="Kindle プロセスが見つかりません"):
                capturer._find_kindle_process_name()

    def test_get_window_title(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript", return_value="My Kindle Book"):
            assert capturer._get_window_title("Kindle") == "My Kindle Book"

        with patch.object(capturer, "_run_applescript", side_effect=RuntimeError("no title")):
            assert capturer._get_window_title("Kindle") == "kindle_book"

    def test_get_window_bounds_success(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript", return_value="10, 20, 800, 600"):
            bounds = capturer._get_window_bounds("Kindle")
            assert bounds == (10, 20, 800, 600)

    def test_get_window_bounds_invalid(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript", return_value="10, 20, 800"):
            with pytest.raises(RuntimeError, match="ウィンドウ領域の取得に失敗しました"):
                capturer._get_window_bounds("Kindle")

    def test_capture_window_region_success(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript"), \
             patch.object(capturer, "_get_window_bounds", return_value=(0, 0, 1000, 800)), \
             patch("subprocess.run") as mock_run:
            capturer._capture_window_region("Kindle", "/tmp/shot.png")
            mock_run.assert_called_once_with(
                ["screencapture", "-x", "-R", "0,0,1000,800", "/tmp/shot.png"],
                check=True,
            )

    def test_capture_window_region_zero_size(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript"), \
             patch.object(capturer, "_get_window_bounds", return_value=(0, 0, 0, 800)):
            with pytest.raises(RuntimeError, match="Kindle ウィンドウが見つかりません"):
                capturer._capture_window_region("Kindle", "/tmp/shot.png")

    def test_send_next_page(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript") as mock_as:
            # left
            capturer._send_next_page("Kindle", direction="left")
            assert "key code 123" in mock_as.call_args[0][0]

            # space
            capturer._send_next_page("Kindle", direction="space")
            assert "key code 49" in mock_as.call_args[0][0]

            # right (default)
            capturer._send_next_page("Kindle", direction="right")
            assert "key code 124" in mock_as.call_args[0][0]

    def test_dismiss_dialog(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript") as mock_as:
            assert capturer._dismiss_dialog("Kindle") is True
            mock_as.side_effect = RuntimeError("failed")
            assert capturer._dismiss_dialog("Kindle") is False

    def test_is_dialog_active(self) -> None:
        capturer = MacKindleCapturer()
        with patch.object(capturer, "_run_applescript") as mock_as:
            # false
            mock_as.return_value = "false"
            assert capturer._is_dialog_active("Kindle", "Title") is False

            # empty
            mock_as.return_value = ""
            assert capturer._is_dialog_active("Kindle", "Title") is False

            # true with reason
            mock_as.return_value = "true|title_mismatch|Library"
            assert capturer._is_dialog_active("Kindle", "Title") is True

            # exception returns False
            mock_as.side_effect = RuntimeError("error")
            assert capturer._is_dialog_active("Kindle", "Title") is False

    def test_capture_pages_pre_dialog_dismissed_and_duplicate_break(self, tmp_path: Path) -> None:
        """capture_pages: 撮影前ダイアログのdismissと、同一画像ハッシュの繰り返しによる終端検出。"""
        capturer = MacKindleCapturer()

        # 既存ディレクトリを用意して、重複連番 _2 が作られる分岐も確認
        existing_dir = tmp_path / "Book Title"
        existing_dir.mkdir()

        call_count = 0
        def fake_capture(proc: str, path_str: str) -> None:
            nonlocal call_count
            call_count += 1
            # 常に同じ内容を書き込むことでハッシュが重複するようにする
            Path(path_str).write_text("duplicate image content")

        with patch.object(capturer, "_find_and_activate_kindle", return_value=("Kindle", "Kindle")), \
             patch.object(capturer, "_get_window_title", return_value="Book Title"), \
             patch.object(capturer, "_is_dialog_active", side_effect=[True, False, False, False, False, False, False, False, False]), \
             patch.object(capturer, "_dismiss_dialog") as mock_dismiss, \
             patch.object(capturer, "_capture_window_region", side_effect=fake_capture), \
             patch.object(capturer, "_send_next_page"), \
             patch("time.sleep"):
            title, shots = capturer.capture_pages(str(tmp_path), page_delay=0.0, direction="right")

            assert title == "Book Title"
            mock_dismiss.assert_called_once()
            # MAX_SAME_PAGES 回重複して検出された後、最後の重複元画像が除外されるため shots は空になる
            assert len(shots) == 0

    def test_capture_pages_post_dialog_discard(self, tmp_path: Path) -> None:
        """capture_pages: 撮影直後にダイアログが検出された場合に撮影画像を破棄して終了。"""
        capturer = MacKindleCapturer()

        def fake_capture(proc: str, path_str: str) -> None:
            Path(path_str).write_text("shot with dialog")

        with patch.object(capturer, "_find_and_activate_kindle", return_value=("Kindle", "Kindle")), \
             patch.object(capturer, "_get_window_title", return_value="Book Title"), \
             patch.object(capturer, "_is_dialog_active", side_effect=[False, True]), \
             patch.object(capturer, "_capture_window_region", side_effect=fake_capture), \
             patch("time.sleep"):
            title, shots = capturer.capture_pages(str(tmp_path), page_delay=0.0)

            assert len(shots) == 0

    def test_capture_pages_multiple_pages_success(self, tmp_path: Path) -> None:
        """capture_pages: 複数ページが正常に撮影され、MAX_HISTORY を超えて保持され、最後に重複で終了するケース。"""
        capturer = MacKindleCapturer()
        page_idx = 0

        def fake_capture(proc: str, path_str: str) -> None:
            nonlocal page_idx
            page_idx += 1
            if page_idx <= 7:
                # 7ページ目までは異なる内容（MAX_HISTORY=5を超える）
                Path(path_str).write_text(f"content page {page_idx}")
            else:
                # 8ページ目以降はページ7と同じ内容にして重複を発生させる
                Path(path_str).write_text("content page 7")

        with patch.object(capturer, "_find_and_activate_kindle", return_value=("Kindle", "Kindle")), \
             patch.object(capturer, "_get_window_title", return_value="Multi Book"), \
             patch.object(capturer, "_is_dialog_active", return_value=False), \
             patch.object(capturer, "_capture_window_region", side_effect=fake_capture), \
             patch.object(capturer, "_send_next_page"), \
             patch("time.sleep"):
            title, shots = capturer.capture_pages(str(tmp_path), page_delay=0.0)

            assert title == "Multi Book"
            # ページ1〜6が残り、ページ7は末尾除外されるため 6 ページとなる
            assert len(shots) == 6


def test_capture_kindle_pages_mac() -> None:
    """capture_kindle_pages: Mac 環境で MacKindleCapturer が呼び出されることのテスト。"""
    with patch("platform.system", return_value="Darwin"), \
         patch.object(MacKindleCapturer, "capture_pages", return_value=("Title", ["page_01.png"])) as mock_cap:
        title, shots = capture_kindle_pages("/out", page_delay=1.0, direction="space")
        assert title == "Title"
        assert shots == ["page_01.png"]
        mock_cap.assert_called_once_with("/out", 1.0, "space")

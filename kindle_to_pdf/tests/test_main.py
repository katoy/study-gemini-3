"""main モジュールのユニットテスト。"""

import argparse
import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import main
from main import (
    _configure_logging,
    _delete_screenshots,
    _generate_pdf,
    _prepare_screenshots,
    _print_summary,
    parse_args,
    run,
)


class TestParseArgs:
    """parse_args のテスト。"""

    def test_defaults(self):
        with patch("sys.argv", ["main.py"]):
            args = parse_args()
        assert args.output_dir == "./output"
        assert args.cdp_url == "http://localhost:9222"
        assert args.launch_chrome is False
        assert args.screenshots == "delete"
        assert args.page_delay == 0.8
        assert args.images_dir is None
        assert args.chrome_user_data_dir is None
        assert args.verbose is False

    def test_launch_chrome_flag(self):
        with patch("sys.argv", ["main.py", "--launch-chrome"]):
            args = parse_args()
        assert args.launch_chrome is True

    def test_output_dir_short_flag(self):
        with patch("sys.argv", ["main.py", "-o", "/tmp/out"]):
            args = parse_args()
        assert args.output_dir == "/tmp/out"

    def test_screenshots_keep(self):
        with patch("sys.argv", ["main.py", "--screenshots", "keep"]):
            args = parse_args()
        assert args.screenshots == "keep"

    def test_page_delay(self):
        with patch("sys.argv", ["main.py", "--page-delay", "2.5"]):
            args = parse_args()
        assert args.page_delay == 2.5

    def test_images_dir(self):
        with patch("sys.argv", ["main.py", "--images-dir", "./imgs"]):
            args = parse_args()
        assert args.images_dir == "./imgs"

    def test_invalid_screenshots_choice(self):
        with patch("sys.argv", ["main.py", "--screenshots", "invalid"]):
            with pytest.raises(SystemExit):
                parse_args()

    def test_verbose_flag(self):
        with patch("sys.argv", ["main.py", "-v"]):
            args = parse_args()
        assert args.verbose is True


class TestPrintSummary:
    """_print_summary のテスト。"""

    def test_outputs_pdf_path(self, capsys):
        pdf_path = Path("/tmp/test.pdf")
        _print_summary(pdf_path)
        captured = capsys.readouterr()
        assert "test.pdf" in captured.out
        assert "処理が完了しました" in captured.out


class TestConfigureLogging:
    """_configure_logging のテスト。"""

    def test_info_level_default(self):
        # basicConfig は一度しか効かないため、ハンドラを掃除してから検証する
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        root.handlers.clear()
        try:
            _configure_logging(verbose=False)
            assert root.level == logging.INFO
        finally:
            root.handlers = old_handlers
            root.level = old_level

    def test_debug_level_when_verbose(self):
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        root.handlers.clear()
        try:
            _configure_logging(verbose=True)
            assert root.level == logging.DEBUG
        finally:
            root.handlers = old_handlers
            root.level = old_level


class TestDeleteScreenshots:
    """_delete_screenshots のテスト。"""

    def test_removes_directory(self, tmp_path):
        target = tmp_path / "shots"
        target.mkdir()
        (target / "page_0001.png").write_bytes(b"x")
        _delete_screenshots(target)
        assert not target.exists()

    def test_no_error_on_missing(self, tmp_path):
        # 存在しないディレクトリでも shutil.rmtree(ignore_errors=True) なので例外は出ない
        _delete_screenshots(tmp_path / "missing")


class TestGeneratePdf:
    """_generate_pdf のテスト。"""

    def test_creates_pdf_at_expected_path(self, tmp_path, monkeypatch):
        called = {}

        def fake_make_pdf(screenshots, output_path):
            called["screenshots"] = screenshots
            called["output_path"] = output_path
            Path(output_path).write_bytes(b"%PDF-")

        monkeypatch.setattr(main, "make_pdf", fake_make_pdf)
        result = _generate_pdf(tmp_path, "Hello World", ["a.png", "b.png"])
        assert result.name == "Hello World.pdf"
        assert called["output_path"] == str(result)

    def test_collision_uses_counter_suffix(self, tmp_path, monkeypatch):
        # 同名 PDF が既に存在する場合 _2, _3 を試す
        (tmp_path / "Hello World.pdf").write_bytes(b"x")
        (tmp_path / "Hello World_2.pdf").write_bytes(b"x")

        def fake_make_pdf(screenshots, output_path):
            Path(output_path).write_bytes(b"%PDF-")

        monkeypatch.setattr(main, "make_pdf", fake_make_pdf)
        result = _generate_pdf(tmp_path, "Hello World", ["a.png"])
        assert result.name == "Hello World_3.pdf"


class TestPrepareScreenshots:
    """_prepare_screenshots のテスト。"""

    def test_uses_existing_images_dir(self, tmp_path):
        shots = tmp_path / "book"
        shots.mkdir()
        (shots / "page_0001.png").write_bytes(b"x")
        (shots / "page_0002.png").write_bytes(b"x")

        args = argparse.Namespace(images_dir=str(shots), cdp_url="http://x", page_delay=0.0)
        title, files, returned_dir = asyncio.run(_prepare_screenshots(args, tmp_path))
        assert title == "book"
        assert len(files) == 2
        assert returned_dir is None  # delete 対象から外す

    def test_missing_images_dir_raises(self, tmp_path):
        args = argparse.Namespace(images_dir=str(tmp_path / "missing"), cdp_url="x", page_delay=0.0)
        with pytest.raises(FileNotFoundError, match="見つかりません"):
            asyncio.run(_prepare_screenshots(args, tmp_path))

    def test_calls_capture_kindle_pages(self, tmp_path, monkeypatch):
        async def fake_capture(output_dir, cdp_url, page_delay):
            book_dir = Path(output_dir) / "Book"
            book_dir.mkdir(parents=True, exist_ok=True)
            shot = book_dir / "page_0001.png"
            shot.write_bytes(b"x")
            return "Book", [str(shot)]

        monkeypatch.setattr(main, "capture_kindle_pages", fake_capture)
        args = argparse.Namespace(images_dir=None, cdp_url="x", page_delay=0.0)
        title, files, returned_dir = asyncio.run(_prepare_screenshots(args, tmp_path))
        assert title == "Book"
        assert returned_dir == tmp_path / "Book"

    def test_capture_returns_empty_handles_none_dir(self, tmp_path, monkeypatch):
        async def fake_capture(output_dir, cdp_url, page_delay):
            return "Book", []

        monkeypatch.setattr(main, "capture_kindle_pages", fake_capture)
        args = argparse.Namespace(images_dir=None, cdp_url="x", page_delay=0.0)
        title, files, returned_dir = asyncio.run(_prepare_screenshots(args, tmp_path))
        assert returned_dir is None


def _make_args(**overrides):
    base = dict(
        output_dir="./output",
        cdp_url="http://localhost:9222",
        launch_chrome=False,
        chrome_user_data_dir=None,
        images_dir=None,
        screenshots="delete",
        page_delay=0.0,
        verbose=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRun:
    """run のテスト（対話フローはモックで駆動）。"""

    def test_quit_without_processing(self, tmp_path, monkeypatch, capsys):
        args = _make_args(output_dir=str(tmp_path / "out"))
        monkeypatch.setattr("builtins.input", lambda _prompt: "q")
        asyncio.run(run(args))
        out = capsys.readouterr().out
        assert "Kindle Cloud Reader" in out

    def test_eof_input_breaks(self, tmp_path, monkeypatch):
        args = _make_args(output_dir=str(tmp_path / "out"))
        monkeypatch.setattr("builtins.input", MagicMock(side_effect=EOFError))
        asyncio.run(run(args))  # 例外なく抜ける

    def test_empty_input_then_quit(self, tmp_path, monkeypatch):
        args = _make_args(output_dir=str(tmp_path / "out"))
        responses = iter(["", "q"])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))
        asyncio.run(run(args))

    def test_full_pipeline_with_existing_images(self, tmp_path, monkeypatch, capsys):
        # キャプチャ済みディレクトリを用意
        shots = tmp_path / "ExistingBook"
        shots.mkdir()
        (shots / "page_0001.png").write_bytes(b"x")
        args = _make_args(
            output_dir=str(tmp_path / "out"),
            images_dir=str(shots),
            screenshots="delete",
        )

        def fake_make_pdf(screenshots, output_path):
            Path(output_path).write_bytes(b"%PDF-")

        monkeypatch.setattr(main, "make_pdf", fake_make_pdf)
        responses = iter(["go", "q"])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

        asyncio.run(run(args))
        out = capsys.readouterr().out
        assert "処理が完了しました" in out
        # images_dir モードでは shot_dir=None なので削除されない
        assert shots.exists()

    def test_pipeline_deletes_screenshots_when_capture_used(self, tmp_path, monkeypatch):
        args = _make_args(output_dir=str(tmp_path / "out"), screenshots="delete")

        async def fake_capture(output_dir, cdp_url, page_delay):
            book_dir = Path(output_dir) / "Book"
            book_dir.mkdir(parents=True, exist_ok=True)
            shot = book_dir / "page_0001.png"
            shot.write_bytes(b"x")
            return "Book", [str(shot)]

        def fake_make_pdf(screenshots, output_path):
            Path(output_path).write_bytes(b"%PDF-")

        monkeypatch.setattr(main, "capture_kindle_pages", fake_capture)
        monkeypatch.setattr(main, "make_pdf", fake_make_pdf)
        responses = iter(["go", "q"])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))

        asyncio.run(run(args))
        # delete モードなのでスクリーンショットディレクトリは消える
        assert not (tmp_path / "out" / "Book").exists()

    def test_inner_exception_is_caught(self, tmp_path, monkeypatch, caplog):
        args = _make_args(output_dir=str(tmp_path / "out"))

        async def failing_capture(*_a, **_kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(main, "capture_kindle_pages", failing_capture)
        responses = iter(["go", "q"])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(responses))
        with caplog.at_level(logging.ERROR, logger="main"):
            asyncio.run(run(args))
        assert any("エラーが発生しました" in rec.message for rec in caplog.records)

    def test_launch_chrome_success(self, tmp_path, monkeypatch):
        args = _make_args(output_dir=str(tmp_path / "out"), launch_chrome=True)

        proc = MagicMock()
        proc.poll.return_value = None
        monkeypatch.setattr(main, "find_free_port", lambda: 12345)
        monkeypatch.setattr(main, "launch_chrome", lambda **kw: proc)
        monkeypatch.setattr(main, "_terminate_process", lambda p: None)
        monkeypatch.setattr("builtins.input", lambda _prompt: "q")
        asyncio.run(run(args))

    def test_launch_chrome_failure_exits(self, tmp_path, monkeypatch):
        args = _make_args(output_dir=str(tmp_path / "out"), launch_chrome=True)

        monkeypatch.setattr(main, "find_free_port", lambda: 12345)

        def boom(**kw):
            raise FileNotFoundError("chrome missing")

        monkeypatch.setattr(main, "launch_chrome", boom)

        with pytest.raises(SystemExit) as excinfo:
            asyncio.run(run(args))
        assert excinfo.value.code == 1

    def test_launch_chrome_with_user_data_dir(self, tmp_path, monkeypatch):
        """--chrome-user-data-dir 指定時は一時ディレクトリを作らない。"""
        user_dir = tmp_path / "udir"
        user_dir.mkdir()
        args = _make_args(
            output_dir=str(tmp_path / "out"),
            launch_chrome=True,
            chrome_user_data_dir=str(user_dir),
        )

        proc = MagicMock()
        proc.poll.return_value = None
        monkeypatch.setattr(main, "find_free_port", lambda: 12345)
        monkeypatch.setattr(main, "launch_chrome", lambda **kw: proc)
        monkeypatch.setattr(main, "_terminate_process", lambda p: None)
        monkeypatch.setattr("builtins.input", lambda _prompt: "q")
        asyncio.run(run(args))
        # 明示指定した dir はテスト終了後も残るはず
        assert user_dir.exists()


class TestMainEntry:
    """main() エントリーポイントのテスト。"""

    def test_keyboard_interrupt(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["main.py"])

        def raise_ki(coro):
            coro.close()  # コルーチンを破棄して RuntimeWarning を防ぐ
            raise KeyboardInterrupt()

        monkeypatch.setattr(main.asyncio, "run", raise_ki)
        with pytest.raises(SystemExit) as excinfo:
            main.main()
        assert excinfo.value.code == 0

    def test_unexpected_exception(self, monkeypatch, caplog):
        monkeypatch.setattr("sys.argv", ["main.py"])

        def raise_err(coro):
            coro.close()
            raise RuntimeError("unexpected")

        monkeypatch.setattr(main.asyncio, "run", raise_err)
        with caplog.at_level(logging.CRITICAL, logger="main"):
            with pytest.raises(SystemExit) as excinfo:
                main.main()
        assert excinfo.value.code == 1
        assert any("予期しないエラー" in rec.message for rec in caplog.records)

    def test_log_level_env(self, monkeypatch):
        """LOG_LEVEL=DEBUG で DEBUG レベルが有効になる。"""
        monkeypatch.setattr("sys.argv", ["main.py"])
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        captured = {}

        def fake_run(_coro):
            captured["level"] = logging.getLogger().level
            # asyncio.run が AsyncMock のコルーチンを参照しないと警告が出るので閉じる
            _coro.close()
            return None

        monkeypatch.setattr(main.asyncio, "run", fake_run)
        # basicConfig の冪等性を打ち消すため、root のハンドラを掃除
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        old_level = root.level
        root.handlers.clear()
        try:
            main.main()
        finally:
            root.handlers = old_handlers
            root.level = old_level
        assert captured["level"] == logging.DEBUG

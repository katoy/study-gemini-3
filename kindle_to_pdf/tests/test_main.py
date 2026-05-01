"""main モジュールのユニットテスト。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from main import _print_summary, parse_args


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


class TestPrintSummary:
    """_print_summary のテスト。"""

    def test_outputs_pdf_path(self, capsys):
        pdf_path = Path("/tmp/test.pdf")
        _print_summary(pdf_path)
        captured = capsys.readouterr()
        assert "test.pdf" in captured.out
        assert "処理が完了しました" in captured.out

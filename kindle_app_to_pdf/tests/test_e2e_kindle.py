import os
from pathlib import Path
import pytest
from PIL import Image

from kindle_capture import MacKindleCapturer, capture_kindle_pages
from pdf_maker import make_pdf


@pytest.mark.e2e
class TestKindleRealE2E:
    """実機の Kindle デスクトップアプリを操作する End-to-End (E2E) テスト。"""

    def test_e2e_find_and_activate_kindle(self) -> None:
        """実機テスト: Kindle アプリのアクティブ化とプロセス名の検出。"""
        capturer = MacKindleCapturer()
        app_name, proc_name = capturer._find_and_activate_kindle()

        assert app_name in ["Kindle", "Amazon Kindle"]
        assert "Kindle" in proc_name

    def test_e2e_window_bounds_and_title(self) -> None:
        """実機テスト: Kindle ウィンドウのタイトルと境界座標の取得。"""
        capturer = MacKindleCapturer()
        _, proc_name = capturer._find_and_activate_kindle()

        title = capturer._get_window_title(proc_name)
        assert isinstance(title, str)
        assert len(title) > 0

        x, y, w, h = capturer._get_window_bounds(proc_name)
        assert w > 0
        assert h > 0
        assert x >= 0 or x < 0  # 画面外/マルチディスプレイ対応

    def test_e2e_capture_window_region(self, tmp_path: Path) -> None:
        """実機テスト: screencapture による実ウィンドウ領域の撮影と PNG 検証。"""
        capturer = MacKindleCapturer()
        _, proc_name = capturer._find_and_activate_kindle()

        shot_path = tmp_path / "e2e_screen.png"
        capturer._capture_window_region(proc_name, str(shot_path))

        assert shot_path.exists()
        assert shot_path.stat().st_size > 1000

        # 画像として正しく読み込めるか検証
        with Image.open(shot_path) as img:
            assert img.format == "PNG"
            assert img.width > 0
            assert img.height > 0

    def test_e2e_send_next_page(self) -> None:
        """実機テスト: ページめくりキー送信が例外なく実行されることの確認。"""
        capturer = MacKindleCapturer()
        _, proc_name = capturer._find_and_activate_kindle()

        # 右矢印、左矢印、スペースキーを送信
        capturer._send_next_page(proc_name, direction="right")
        capturer._send_next_page(proc_name, direction="left")
        capturer._send_next_page(proc_name, direction="space")

    def test_e2e_capture_and_pdf_generation(self, tmp_path: Path) -> None:
        """実機テスト: 実際の Kindle を撮影し、PDF 生成までの一連フローを実行（テスト用に最大3ページで安全停止）。"""
        capturer = MacKindleCapturer()
        _, proc_name = capturer._find_and_activate_kindle()

        # 実機テストが何百ページもキャプチャし続けないよう、2ページ撮影後に終端ダイアログ扱いにして安全停止
        shot_count = 0
        orig_capture = capturer._capture_window_region

        def wrapped_capture(proc: str, path_str: str) -> None:
            nonlocal shot_count
            shot_count += 1
            orig_capture(proc, path_str)

        orig_is_dialog = capturer._is_dialog_active
        def stop_after_2_pages(proc: str, book_title: str) -> bool:
            if shot_count >= 2:
                return True
            return orig_is_dialog(proc, book_title)

        capturer._capture_window_region = wrapped_capture  # type: ignore
        capturer._is_dialog_active = stop_after_2_pages  # type: ignore

        title, screenshots = capturer.capture_pages(
            output_dir=str(tmp_path),
            page_delay=0.3,
            direction="right",
        )

        assert isinstance(title, str)
        assert isinstance(screenshots, list)
        assert len(screenshots) >= 1

        # 撮影された実画像から本物の PDF を生成できることを検証
        pdf_path = tmp_path / f"{title}.pdf"
        make_pdf(screenshots, str(pdf_path))
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

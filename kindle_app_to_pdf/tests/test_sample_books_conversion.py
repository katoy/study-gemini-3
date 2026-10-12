"""
サンプル書籍（縦書き本: '走れメロス'、横書き本: "Alice's Adventures in Wonderland"）を使用した
キャプチャから PDF 変換出力結果までの検証テスト。
"""

import argparse
from pathlib import Path
import shutil

from PIL import Image, ImageDraw
from pypdf import PdfReader
import pytest

from kindle_capture import _run_capture_loop
import main
from pdf_maker import make_pdf


def _create_sample_page(
    width: int,
    height: int,
    bg_color: tuple[int, int, int],
    text: str,
    page_num: int,
) -> Image.Image:
    """指定された寸法・内容のサンプル書籍ページ画像を生成します。"""
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    # ページごとに確実にハッシュが異なるよう、テキストと識別用図形を描画
    draw.rectangle([20, 20, width - 20, height - 20], outline=(100, 100, 100), width=3)
    draw.text((40, 40), f"{text} (Page {page_num})", fill=(0, 0, 0))
    # ページ番号を目印として描画
    draw.rectangle([50, 80 + page_num * 30, 200, 100 + page_num * 30], fill=(50, 50, 200))
    return img


class TestSampleBooksConversion:
    """縦書き本・横書き本を想定した PDF 変換結果チェックテスト。"""

    def test_vertical_book_merosu_pdf_conversion(self, tmp_path: Path) -> None:
        """縦書き本 '走れメロス' のキャプチャ〜PDF変換結果をチェック。"""
        book_title = "走れメロス"
        # 縦長レイアウト (800 x 1200)
        page_w, page_h = 800, 1200
        total_pages = 3

        sample_pages = [
            _create_sample_page(page_w, page_h, (250, 248, 245), "走れメロス - 太宰治", i + 1)
            for i in range(total_pages)
        ]

        shot_files: list[str] = []
        for i, page_img in enumerate(sample_pages):
            path = tmp_path / f"page_{i + 1:04d}.png"
            page_img.save(str(path))
            shot_files.append(str(path))

        # 1. make_pdf による PDF 生成
        pdf_path = tmp_path / f"{book_title}.pdf"
        make_pdf(shot_files, str(pdf_path))

        # 2. 出力 PDF の検証
        assert pdf_path.exists(), "PDF ファイルが生成されていること"
        assert pdf_path.stat().st_size > 0, "ファイルサイズが 0 より大きいこと"

        reader = PdfReader(str(pdf_path))
        assert len(reader.pages) == total_pages, f"ページ数が {total_pages} であること"

        for idx, page in enumerate(reader.pages):
            box = page.mediabox
            # 縦長アスペクト比であることを検証（縦 > 横）
            assert box.height > box.width, f"ページ {idx + 1} が縦長レイアウトであること"
            # アスペクト比 (1200 / 800 = 1.5) が一致すること
            assert float(box.height / box.width) == pytest.approx(page_h / page_w, rel=1e-2)

        # 目視確認用に ./output/test_samples に保存
        samples_dir = Path("./output/test_samples")
        samples_dir.mkdir(parents=True, exist_ok=True)
        sample_pdf = samples_dir / f"{book_title}.pdf"
        shutil.copy2(pdf_path, sample_pdf)
        print(f"\n[サンプルテスト: 縦書き] 生成された PDF: {sample_pdf.resolve()}")

    def test_horizontal_book_alice_pdf_conversion(self, tmp_path: Path) -> None:
        """横書き本 "Alice's Adventures in Wonderland" のキャプチャ〜PDF変換結果をチェック。"""
        book_title = "Alice's Adventures in Wonderland"
        # 横長・標準レイアウト (1200 x 800)
        page_w, page_h = 1200, 800
        total_pages = 3

        sample_pages = [
            _create_sample_page(
                page_w, page_h, (255, 255, 255), "Alice's Adventures in Wonderland", i + 1
            )
            for i in range(total_pages)
        ]

        shot_files: list[str] = []
        for i, page_img in enumerate(sample_pages):
            path = tmp_path / f"page_{i + 1:04d}.png"
            page_img.save(str(path))
            shot_files.append(str(path))

        # 1. make_pdf による PDF 生成
        pdf_path = tmp_path / f"{book_title}.pdf"
        make_pdf(shot_files, str(pdf_path))

        # 2. 出力 PDF の検証
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

        reader = PdfReader(str(pdf_path))
        assert len(reader.pages) == total_pages

        for idx, page in enumerate(reader.pages):
            box = page.mediabox
            # 横長レイアウトであることを検証（横 > 縦）
            assert box.width > box.height, f"ページ {idx + 1} が横長レイアウトであること"
            # アスペクト比 (1200 / 800 = 1.5) が一致すること
            assert float(box.width / box.height) == pytest.approx(page_w / page_h, rel=1e-2)

        # 目視確認用に ./output/test_samples に保存
        samples_dir = Path("./output/test_samples")
        samples_dir.mkdir(parents=True, exist_ok=True)
        sample_pdf = samples_dir / f"{book_title}.pdf"
        shutil.copy2(pdf_path, sample_pdf)
        print(f"\n[サンプルテスト: 横書き] 生成された PDF: {sample_pdf.resolve()}")

    def test_capture_loop_with_sample_books(self, tmp_path: Path) -> None:
        """キャプチャループ (_run_capture_loop) が direction='space' でサンプル本を正しく処理するか検証。"""
        for book_title, is_vertical in [
            ("走れメロス", True),
            ("Alice's Adventures in Wonderland", False),
        ]:
            out_dir = tmp_path / book_title
            out_dir.mkdir(parents=True, exist_ok=True)

            w, h = (800, 1200) if is_vertical else (1200, 800)
            pages = [
                _create_sample_page(w, h, (250, 250, 250), book_title, i + 1) for i in range(3)
            ]

            call_count = 0

            def mock_capture(path: Path) -> None:
                nonlocal call_count
                page_idx = min(call_count, len(pages) - 1)
                pages[page_idx].save(str(path))
                call_count += 1

            keys_sent: list[str] = []

            def mock_send(direction: str) -> None:
                keys_sent.append(direction)

            # 3回撮影・受理後に終端判定
            def mock_is_dialog() -> bool:
                return call_count > 3

            title, screenshots = _run_capture_loop(
                book_title=book_title,
                raw_book_title=book_title,
                output_dir=str(out_dir),
                page_delay=0.01,
                direction="space",
                max_pages=10,
                capture_screenshot=mock_capture,
                send_next_page=mock_send,
                is_dialog_active=mock_is_dialog,
                dismiss_dialog=lambda: True,
            )

            assert title == book_title
            assert len(screenshots) == 3
            # デフォルト 'space' でキーが送信されたことを検証
            assert all(d == "space" for d in keys_sent)

            # 生成された画像から PDF を生成して検証
            pdf_path = out_dir / f"{title}.pdf"
            make_pdf(screenshots, str(pdf_path))
            reader = PdfReader(str(pdf_path))
            assert len(reader.pages) == 3

    def test_main_cli_sample_books_flow(self, tmp_path: Path) -> None:
        """main.run を通じた CLI 実行フローで両サンプル書籍の変換と出力をチェック。"""
        for title in ["走れメロス", "Alice's Adventures in Wonderland"]:
            out_dir = tmp_path / f"out_{title}"
            img_dir = tmp_path / title
            img_dir.mkdir(parents=True, exist_ok=True)

            # サンプル PNG を作成
            for i in range(2):
                img = _create_sample_page(800, 1000, (255, 255, 255), title, i + 1)
                img.save(str(img_dir / f"page_{i + 1:04d}.png"))

            args = argparse.Namespace(
                output_dir=str(out_dir),
                images_dir=str(img_dir),
                screenshots="keep",
                page_delay=0.1,
                direction="space",
                max_pages=10,
            )

            # 既存画像指定での run 実行
            main.run(args)

            expected_pdf = out_dir / f"{title}.pdf"
            assert expected_pdf.exists(), f"{title}.pdf が生成されること"
            reader = PdfReader(str(expected_pdf))
            assert len(reader.pages) == 2

from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image

from pdf_maker import make_pdf


def test_make_pdf_empty_screenshots(tmp_path: Path) -> None:
    """スクリーンショットリストが空の場合に ValueError が発生することを確認。"""
    output_path = tmp_path / "output.pdf"
    with pytest.raises(ValueError, match="スクリーンショットが 0 枚です。"):
        make_pdf([], str(output_path))


def test_make_pdf_success(tmp_path: Path) -> None:
    """正常系: 画像から PDF が正しく生成されることを確認。"""
    # テスト用画像を作成 (1つは Path, 1つは str で渡す)
    img1_path = tmp_path / "img1.png"
    img2_path = tmp_path / "img2.png"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img1_path)
    img.save(img2_path)

    output_path = tmp_path / "nested" / "output.pdf"

    make_pdf([img1_path, str(img2_path)], str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_make_pdf_exception_raised(tmp_path: Path) -> None:
    """異常系: img2pdf.convert で例外が発生した際にログ出力され例外が再送出されることを確認。"""
    dummy_img = tmp_path / "dummy.png"
    dummy_img.touch()
    output_path = tmp_path / "output.pdf"

    with patch("img2pdf.convert", side_effect=RuntimeError("convert failure")):
        with pytest.raises(RuntimeError, match="convert failure"):
            make_pdf([dummy_img], str(output_path))


def test_l5_make_pdf_uses_outputstream(tmp_path: Path) -> None:
    """L-5 再現テスト: メモリ逼迫を防ぐため img2pdf.convert に outputstream が渡されること。"""
    dummy_img = tmp_path / "dummy.png"
    dummy_img.touch()
    output_path = tmp_path / "output.pdf"

    with patch("img2pdf.convert") as mock_convert:
        make_pdf([dummy_img], str(output_path))
        assert "outputstream" in mock_convert.call_args[1]


def test_l5_make_pdf_cleans_up_file_on_error(tmp_path: Path) -> None:
    """L-5 再現テスト: 変換失敗時に 0 バイトファイルが残らず削除されること。"""
    dummy_img = tmp_path / "dummy.png"
    dummy_img.touch()
    output_path = tmp_path / "output.pdf"

    with patch("img2pdf.convert", side_effect=RuntimeError("convert failure")):
        with pytest.raises(RuntimeError):
            make_pdf([dummy_img], str(output_path))

    assert not output_path.exists(), "エラー発生時に 0 バイトの出力ファイルが残ってしまっています"

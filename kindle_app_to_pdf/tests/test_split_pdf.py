from pathlib import Path
import runpy
import sys
from unittest.mock import patch
import pytest
from pypdf import PdfWriter

from split_pdf import main, split_pdf


def _create_sample_pdf(path: Path, num_pages: int = 5) -> None:
    """テスト用の複数ページ PDF を作成する。"""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def test_split_pdf_multi_parts(tmp_path: Path) -> None:
    """PDF が指定サイズ以下に複数分割されることを確認。"""
    pdf_path = tmp_path / "sample.pdf"
    _create_sample_pdf(pdf_path, num_pages=6)

    out_dir = tmp_path / "output"

    # 極小の max_mb (0.0001 MB = 104 bytes) を指定して、1ページずつ分割されるようにする
    # これにより size > max_bytes の分岐と 1 ページ書き出しのフォールバックが通る
    result_files = split_pdf(str(pdf_path), max_mb=0.0001, output_dir=str(out_dir))

    assert len(result_files) == 6
    for f in result_files:
        assert Path(f).exists()


def test_split_pdf_single_part(tmp_path: Path) -> None:
    """PDF が指定サイズに収まるため 1 ファイルのまま出力されることを確認。"""
    pdf_path = tmp_path / "sample.pdf"
    _create_sample_pdf(pdf_path, num_pages=3)

    out_dir = tmp_path / "output"
    # 十分大きな max_mb を指定
    result_files = split_pdf(str(pdf_path), max_mb=50.0, output_dir=str(out_dir))

    assert len(result_files) == 1
    assert Path(result_files[0]).exists()


def test_split_pdf_binary_search_both_branches(tmp_path: Path) -> None:
    """二分探索で size <= max_bytes と size > max_bytes の両方の分岐を通るテスト。"""
    pdf_path = tmp_path / "sample.pdf"
    _create_sample_pdf(pdf_path, num_pages=4)

    # 4ページのサイズを測定
    actual_size = pdf_path.stat().st_size
    # 2ページ分くらいが入るサイズ (MB 換算) を設定
    half_mb = (actual_size * 0.6) / (1024 * 1024)

    out_dir = tmp_path / "output_bs"
    result_files = split_pdf(str(pdf_path), max_mb=half_mb, output_dir=str(out_dir))

    assert len(result_files) >= 2


def test_main_file_not_found(tmp_path: Path) -> None:
    """main: 存在しない入力ファイルを指定した場合に sys.exit(1) で終了することを確認。"""
    non_existent = tmp_path / "not_found.pdf"
    test_args = ["split_pdf.py", str(non_existent)]

    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


def test_main_success(tmp_path: Path) -> None:
    """main: 正常な引数で実行した場合に split_pdf が実行されることを確認。"""
    pdf_path = tmp_path / "sample.pdf"
    _create_sample_pdf(pdf_path, num_pages=2)
    out_dir = tmp_path / "output_main"

    test_args = [
        "split_pdf.py",
        str(pdf_path),
        "--max-mb",
        "100",
        "--output-dir",
        str(out_dir),
    ]

    with patch.object(sys, "argv", test_args):
        main()

    assert (out_dir / "sample_part01.pdf").exists()


def test_split_pdf_entrypoint(tmp_path: Path) -> None:
    """__main__ 実行ブロックを通すテスト。"""
    pdf_path = tmp_path / "sample.pdf"
    _create_sample_pdf(pdf_path, num_pages=1)
    out_dir = tmp_path / "output_entry"

    test_args = ["split_pdf.py", str(pdf_path), "-o", str(out_dir)]
    with patch.object(sys, "argv", test_args):
        runpy.run_module("split_pdf", run_name="__main__")

    assert (out_dir / "sample_part01.pdf").exists()

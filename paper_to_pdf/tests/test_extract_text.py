import os
import pytest
import pypdfium2 as pdfium
from pathlib import Path
from unittest.mock import MagicMock, patch
from extract_text import extract_text_from_pdf, main
import sys

# テスト用のダミー PDF を作成するヘルパー
@pytest.fixture
def dummy_pdf(tmp_path):
    """1ページのダミー PDF を作成。"""
    pdf_path = tmp_path / "test.pdf"
    pdf = pdfium.PdfDocument.new()
    # A4 (595x842 pts)
    pdf.new_page(595, 842)
    pdf.save(str(pdf_path))
    return pdf_path

def test_extract_text_no_file(tmp_path):
    """存在しないファイルのエラーハンドリングテスト。"""
    non_existent = tmp_path / "missing.pdf"
    output_md = tmp_path / "out.md"
    success = extract_text_from_pdf(non_existent, output_md)
    assert success is False

@patch("extract_text.ocrmac.OCR")
def test_extract_text_basic(mock_ocr, dummy_pdf, tmp_path):
    """基本的な OCR 抽出と Markdown 出力のテスト。"""
    output_md = tmp_path / "out.md"
    
    # ocrmac.OCR().recognize() のモック
    mock_instance = MagicMock()
    mock_instance.recognize.return_value = [("Hello", (0,0,10,10)), ("World", (20,0,30,10))]
    mock_ocr.return_value = mock_instance
    
    # 自動回転なしで実行
    success = extract_text_from_pdf(dummy_pdf, output_md, auto_rotate=False)
    
    assert success is True
    assert output_md.exists()
    content = output_md.read_text(encoding="utf-8")
    assert "## Page 1" in content
    assert "Hello World" in content

@patch("extract_text.ocrmac.OCR")
def test_extract_text_auto_rotate(mock_ocr, dummy_pdf, tmp_path):
    """自動回転ロジックのテスト。"""
    output_md = tmp_path / "out.md"
    
    # 角度ごとに異なる単語数を返すように設定
    # 0, 90, 180, 270 度の順で呼ばれる
    mock_instance = MagicMock()
    # 180度 (3番目の呼び出し) で最も多い単語を返す
    mock_instance.recognize.side_effect = [
        [("A", (0,0,1,1))],             # 0度: 1語
        [("B", (0,0,1,1)), ("C", (0,0,1,1))], # 90度: 2語
        [("D", (0,0,1,1),), ("E", (0,0,1,1)), ("F", (0,0,1,1))], # 180度: 3語 (Best)
        [("G", (0,0,1,1))]              # 270度: 1語
    ]
    mock_ocr.return_value = mock_instance
    
    # capsys を使って標準出力を確認
    with patch("sys.stdout") as mock_stdout:
        success = extract_text_from_pdf(dummy_pdf, output_md, auto_rotate=True)
    
    assert success is True
    content = output_md.read_text(encoding="utf-8")
    # 180度の単語が含まれているか確認
    assert "D E F" in content

def test_main_argparse(tmp_path):
    """コマンドライン引数のパーステスト。"""
    pdf_path = tmp_path / "in.pdf"
    pdf_path.touch()
    out_path = tmp_path / "out.md"
    
    test_args = ["extract_text.py", str(pdf_path), str(out_path), "--lang", "ja-JP"]
    with patch.object(sys, 'argv', test_args):
        with patch("extract_text.extract_text_from_pdf") as mock_func:
            mock_func.return_value = True
            main()
            mock_func.assert_called_once()

def test_extract_text_exception(dummy_pdf, tmp_path):
    """例外発生時のテスト。"""
    with patch("pypdfium2.PdfDocument") as mock_pdf:
        mock_pdf.side_effect = Exception("PDF Error")
        success = extract_text_from_pdf(dummy_pdf, tmp_path / "out.md")
        assert success is False

def test_main_exit_on_failure(tmp_path):
    """失敗時に sys.exit(1) が呼ばれるかテスト。"""
    pdf_path = tmp_path / "in.pdf"
    pdf_path.touch()
    with patch.object(sys, 'argv', ["extract_text.py", str(pdf_path), "out.md"]):
        with patch("extract_text.extract_text_from_pdf") as mock_func:
            mock_func.return_value = False
            with pytest.raises(SystemExit) as e:
                main()
            assert e.value.code == 1

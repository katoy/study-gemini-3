import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# Add scripts directory to path to import split_pdf and pdf_utils
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

import pytest
import split_pdf
import pdf_utils

def test_get_file_size_mb():
    with patch("os.path.getsize") as mock_getsize:
        mock_getsize.return_value = 1024 * 1024 * 5  # 5 MB
        assert pdf_utils.get_file_size_mb("dummy.pdf") == 5.0
        mock_getsize.assert_called_once_with("dummy.pdf")

def test_get_page_count():
    with patch("pdf_utils.PdfReader") as mock_pdf_reader:
        mock_reader_instance = MagicMock()
        mock_reader_instance.pages = [MagicMock()] * 15
        mock_pdf_reader.return_value = mock_reader_instance
        
        assert pdf_utils.get_page_count("dummy.pdf") == 15
        mock_pdf_reader.assert_called_once_with("dummy.pdf")

def test_get_page_count_exception():
    with patch("pdf_utils.PdfReader", side_effect=Exception("Read error")):
        assert pdf_utils.get_page_count("dummy.pdf") == 0

def test_split_pdf_under_20mb():
    # File size <= 20MB: should just copy the file
    pdf_path = "dummy.pdf"
    output_dir = "out"
    base_filename = "dummy.pdf"
    
    with patch("split_pdf.pdf_utils.get_file_size_mb", return_value=15.0), \
         patch("split_pdf.pdf_utils.get_page_count", return_value=10), \
         patch("shutil.copy2") as mock_copy:
        
        expected_output = os.path.join(output_dir, base_filename)
        result = split_pdf.split_pdf(pdf_path, output_dir, base_filename)
        
        assert result == [expected_output]
        mock_copy.assert_called_once_with(pdf_path, expected_output)

def test_split_pdf_over_20mb():
    # File size > 20MB (e.g. 50MB): should split into 3 parts (ceil(50/20) = 3)
    pdf_path = "large.pdf"
    output_dir = "out"
    base_filename = "large.pdf"
    
    mock_pages = [MagicMock() for _ in range(15)]
    
    with patch("split_pdf.pdf_utils.get_file_size_mb") as mock_size, \
         patch("split_pdf.pdf_utils.get_page_count", return_value=15), \
         patch("split_pdf.PdfReader") as mock_reader_cls, \
         patch("split_pdf.PdfWriter") as mock_writer_cls, \
         patch("builtins.open", mock_open()):
        
        mock_size.side_effect = [50.0, 15.0, 15.0, 15.0]
        
        mock_reader = MagicMock()
        mock_reader.pages = mock_pages
        mock_reader_cls.return_value = mock_reader
        
        mock_writers = [MagicMock() for _ in range(3)]
        mock_writer_cls.side_effect = mock_writers
        
        result = split_pdf.split_pdf(pdf_path, output_dir, base_filename)
        
        assert len(result) == 3
        assert result[0] == os.path.join(output_dir, "large_part1.pdf")
        assert result[1] == os.path.join(output_dir, "large_part2.pdf")
        assert result[2] == os.path.join(output_dir, "large_part3.pdf")
        
        # Writer 1 (pages 0-4)
        for i in range(0, 5):
            mock_writers[0].add_page.assert_any_call(mock_pages[i])
        assert mock_writers[0].add_page.call_count == 5
        
        # Writer 2 (pages 5-9)
        for i in range(5, 10):
            mock_writers[1].add_page.assert_any_call(mock_pages[i])
        assert mock_writers[1].add_page.call_count == 5
        
        # Writer 3 (pages 10-14)
        for i in range(10, 15):
            mock_writers[2].add_page.assert_any_call(mock_pages[i])
        assert mock_writers[2].add_page.call_count == 5

def test_split_pdf_zero_pages():
    with patch("split_pdf.pdf_utils.get_file_size_mb", return_value=10.0), \
         patch("split_pdf.pdf_utils.get_page_count", return_value=0):
        
        result = split_pdf.split_pdf("dummy.pdf", "out", "dummy.pdf")
        assert result == []

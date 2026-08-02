import os
import sys
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# Add scripts directory to path to import pdf_chapter_pipeline
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

import pdf_chapter_pipeline
from pdf_chapter_pipeline import TocEntry

# Keep a reference to the original stat method to avoid infinite recursion
org_stat = Path.stat

def mock_path_stat(self_path, *args, **kwargs):
    # If it's a directory (no .pdf extension), use the original stat to keep mkdir() working
    if not str(self_path).endswith(".pdf"):
        return org_stat(self_path)
    
    # Return dummy stat for mock PDF files
    mock_res = MagicMock()
    mock_res.st_mode = stat.S_IFREG
    
    # Set size based on filename to simulate oversized vs normal split files
    filename = self_path.name
    if "large" in filename or "p5-24" in filename or "oversized" in filename:
        mock_res.st_size = 1024 * 1024 * 50  # 50 MB
    else:
        mock_res.st_size = 1024 * 1024 * 10  # 10 MB
        
    print(f"[DEBUG mock_path_stat] {filename} -> {mock_res.st_size / (1024**2)} MB")
    return mock_res

def test_normalize():
    assert pdf_chapter_pipeline.normalize("第 １ 章 　テスト") == "第1章テスト"
    assert pdf_chapter_pipeline.normalize("Chapter\t1") == "Chapter1"

def test_sanitize_filename():
    assert pdf_chapter_pipeline.sanitize_filename('第1章: テスト/サンプル?*') == '第1章_テストサンプル'
    # Test max length truncation
    long_title = "a" * 100
    assert pdf_chapter_pipeline.sanitize_filename(long_title) == "a" * 40

def test_find_toc_pages():
    mock_reader = MagicMock()
    # Page 0 has empty text, Page 1 has "目次", Page 2 has items, Page 3 has regular content
    page0 = MagicMock()
    page0.extract_text.return_value = "Title page"
    page1 = MagicMock()
    page1.extract_text.return_value = "目次\n第1章..............10\n第2章..............20"
    page2 = MagicMock()
    page2.extract_text.return_value = "第3章..............30\n第4章..............40"
    page3 = MagicMock()
    page3.extract_text.return_value = "Regular text contents on page 4..."
    
    mock_reader.pages = [page0, page1, page2, page3]
    
    # scan_limit = 30
    toc_pages = pdf_chapter_pipeline.find_toc_pages(mock_reader, scan_limit=10)
    assert toc_pages == [1, 2]

def test_parse_toc_entries():
    mock_reader = MagicMock()
    page1 = MagicMock()
    page1.extract_text.return_value = "目次\n第1章  ........... 10\nはじめに  ........... 1\n節 1.1  ........... 12\n第2章  ........... 20\n"
    mock_reader.pages = [MagicMock(), page1]
    
    entries = pdf_chapter_pipeline.parse_toc_entries(mock_reader, [1])
    
    # 4 entries should match pattern "title .... page"
    assert len(entries) == 4
    
    # Check is_chapter flag based on chapter_re
    # 第1章, はじめに, 第2章 should be chapters
    # 節 1.1 is not a chapter (no Chapter/第X章/はじめに etc. matching top level)
    assert entries[0].title == "第1章"
    assert entries[0].printed_page == 10
    assert entries[0].is_chapter is True
    
    assert entries[1].title == "はじめに"
    assert entries[1].printed_page == 1
    assert entries[1].is_chapter is True
    
    assert entries[2].title == "節 1.1"
    assert entries[2].printed_page == 12
    assert entries[2].is_chapter is False
    
    assert entries[3].title == "第2章"
    assert entries[3].printed_page == 20
    assert entries[3].is_chapter is True

def test_compute_offset():
    # printed pages:
    # はじめに: 1 (physical should be e.g. 5, so offset = 4)
    # 第1章: 10 (physical should be e.g. 14)
    entries = [
        TocEntry("はじめに", 1, is_chapter=True),
        TocEntry("第1章", 10, is_chapter=True),
    ]
    
    mock_reader = MagicMock()
    # Total 30 pages
    mock_pages = [MagicMock() for _ in range(30)]
    for p in mock_pages:
        p.extract_text.return_value = ""  # Default empty to prevent MagicMock slice errors
        
    # Setup page text for physical page index 4 (physical page 5): should match "はじめに"
    mock_pages[4].extract_text.return_value = "はじめに\nこの本は..."
    # Setup page text for physical page index 13 (physical page 14): should match "第1章"
    mock_pages[13].extract_text.return_value = "第1章\n概要について..."
    
    mock_reader.pages = mock_pages
    
    # Offset should be 4 (printed_page + 4 = physical_page)
    offset = pdf_chapter_pipeline.compute_offset(mock_reader, entries, sample_size=2)
    assert offset == 4

def test_build_chapter_boundaries():
    entries = [
        TocEntry("はじめに", 1, is_chapter=True),
        TocEntry("第1章", 10, is_chapter=True),
        TocEntry("第2章", 20, is_chapter=True),
        TocEntry("節2.1", 22, is_chapter=False),  # should be filtered out
        TocEntry("重複第2章", 20, is_chapter=True),  # duplicate printed page
    ]
    
    boundaries = pdf_chapter_pipeline.build_chapter_boundaries(entries, offset=5, total_pages=50)
    
    # Expected boundaries:
    # はじめに: printed 1 -> physical 6
    # 第1章: printed 10 -> physical 15
    # 第2章: printed 20 -> physical 25
    # 重複第2章: printed 20 -> physical 25 (filtered out because not > last_page which is 25)
    assert len(boundaries) == 3
    assert boundaries[0].title == "はじめに"
    assert boundaries[0].physical_page == 6
    assert boundaries[1].title == "第1章"
    assert boundaries[1].physical_page == 15
    assert boundaries[2].title == "第2章"
    assert boundaries[2].physical_page == 25

def test_split_by_boundaries(tmp_path):
    mock_reader = MagicMock()
    mock_reader.pages = [MagicMock() for _ in range(30)]  # 30 pages
    
    boundaries = [
        TocEntry("第1章", 5, is_chapter=True, physical_page=5),
        TocEntry("第2章", 15, is_chapter=True, physical_page=15),
    ]
    
    output_dir = tmp_path / "split_output"
    
    with patch("pdf_chapter_pipeline.PdfWriter") as mock_writer_cls, \
         patch("pdf_chapter_pipeline.open", mock_open()), \
         patch("pathlib.Path.stat", mock_path_stat):
        
        mock_writers = [MagicMock(), MagicMock(), MagicMock()]
        mock_writer_cls.side_effect = mock_writers
        
        outputs = pdf_chapter_pipeline.split_by_boundaries(mock_reader, boundaries, output_dir)
        
        assert len(outputs) == 3
        
        assert outputs[0]["title"] == "前付け"
        assert outputs[0]["start"] == 1
        assert outputs[0]["end"] == 4
        
        assert outputs[1]["title"] == "第1章"
        assert outputs[1]["start"] == 5
        assert outputs[1]["end"] == 14
        
        assert outputs[2]["title"] == "第2章"
        assert outputs[2]["start"] == 15
        assert outputs[2]["end"] == 30

def test_resplit_oversized(tmp_path):
    mock_reader = MagicMock()
    mock_reader.pages = [MagicMock() for _ in range(30)]
    
    # We use a real path under tmp_path so exists() checks don't fail,
    # and touch it so unlink() doesn't raise FileNotFoundError if it checks.
    output_dir = tmp_path / "chapters"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    target_path = output_dir / "02_第1章_p5-24.pdf"
    target_path.touch()
    
    chapter_info = {
        "path": str(target_path),
        "title": "第1章",
        "start": 5,
        "end": 24,
        "size_mb": 50.0  # Over 20MB limit
    }
    
    # fine entries for splitting
    all_entries = [
        TocEntry("節1.1", 10, is_chapter=False, physical_page=10),
        TocEntry("節1.2", 15, is_chapter=False, physical_page=15),
    ]
    
    with patch("pdf_chapter_pipeline.PdfWriter") as mock_writer_cls, \
         patch("pdf_chapter_pipeline.open", mock_open()), \
         patch("pathlib.Path.stat", mock_path_stat):
        
        # We need at least 2 writers for resplitting (ceil(50/20) = 3 parts)
        mock_writers = [MagicMock() for _ in range(3)]
        mock_writer_cls.side_effect = mock_writers
        
        result = pdf_chapter_pipeline.resplit_oversized(
            mock_reader, chapter_info, all_entries, output_dir, max_size_mb=20.0, index_prefix="02"
        )
        
        # Original oversized file should be deleted (it won't exist now because target_path.unlink() was called)
        assert not os.path.exists(target_path)
        
        # Should be split into 3 parts
        assert len(result) == 3

def test_detect_chapters_by_toc_titles():
    mock_reader = MagicMock()
    mock_pages = [MagicMock() for _ in range(10)]
    for p in mock_pages:
        p.extract_text.return_value = ""
        
    mock_pages[2].extract_text.return_value = "第1章　導入部分の解説\n本文テキスト..."
    mock_pages[6].extract_text.return_value = "第2章　詳細な手法\n本文テキスト..."
    mock_reader.pages = mock_pages
    
    toc_entries = [
        TocEntry("第1章 導入部", 1, is_chapter=True),
        TocEntry("第2章 詳細手法", 5, is_chapter=True),
    ]
    
    detected = pdf_chapter_pipeline.detect_chapters_by_toc_titles(mock_reader, toc_entries)
    
    assert len(detected) == 2
    assert detected[0].physical_page == 3 # index 2
    assert detected[1].physical_page == 7 # index 6

def test_detect_chapters_by_keywords():
    mock_reader = MagicMock()
    mock_pages = [MagicMock() for _ in range(10)]
    for p in mock_pages:
        p.extract_text.return_value = ""
        
    mock_pages[1].extract_text.return_value = "第1章 テスト見出し\n本文..."
    mock_pages[5].extract_text.return_value = "Chapter 2 Details\n本文..."
    mock_pages[8].extract_text.return_value = "おわりに\n本文..."
    mock_reader.pages = mock_pages
    
    detected = pdf_chapter_pipeline.detect_chapters_by_keywords(mock_reader)
    
    assert len(detected) == 3
    assert "第1章" in detected[0].title
    assert detected[0].physical_page == 2
    assert "Chapter 2" in detected[1].title
    assert detected[1].physical_page == 6
    assert "おわりに" in detected[2].title
    assert detected[2].physical_page == 9

def test_uniform_fallback_split(tmp_path):
    mock_reader = MagicMock()
    mock_reader.pages = [MagicMock() for _ in range(35)]
    
    output_dir = tmp_path / "fallback_output"
    
    with patch("pdf_chapter_pipeline.PdfWriter") as mock_writer_cls, \
         patch("pdf_chapter_pipeline.open", mock_open()), \
         patch("pathlib.Path.stat", mock_path_stat):
        
        # total_size = 50MB, max_size = 20MB -> 3 parts
        # 35 pages -> 12 pages, 12 pages, 11 pages
        mock_writers = [MagicMock() for _ in range(3)]
        mock_writer_cls.side_effect = mock_writers
        
        outputs = pdf_chapter_pipeline.uniform_fallback_split(
            mock_reader, output_dir, total_size_mb=50.0, max_size_mb=20.0
        )
        
        assert len(outputs) == 3
        assert outputs[0]["start"] == 1
        assert outputs[0]["end"] == 12
        assert outputs[1]["start"] == 13
        assert outputs[1]["end"] == 24
        assert outputs[2]["start"] == 25
        assert outputs[2]["end"] == 35

import importlib.util
from pathlib import Path
from pypdf import PdfReader, PdfWriter
import pytest

# output/pdf-chapter-splitter/split_pdf.py を安全に読み込む（ルートの split_pdf.py との衝突を防止）
splitter_path = (
    Path(__file__).resolve().parent.parent / "output" / "pdf-chapter-splitter" / "split_pdf.py"
)
spec = importlib.util.spec_from_file_location("chapter_splitter", splitter_path)
assert spec is not None and spec.loader is not None
chapter_splitter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chapter_splitter)


def _create_sample_pdf(path: Path, num_pages: int = 5) -> None:
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    with open(path, "wb") as f:
        writer.write(f)


def test_m8_does_not_rmtree_entire_directory(tmp_path: Path) -> None:
    """M-8 再現テスト: 出力ディレクトリ内の非 PDF ファイル（例: 重要データ）を無条件に削除しないこと。"""
    out_dir = tmp_path / "chapters_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    important_file = out_dir / "important_notes.txt"
    important_file.write_text("絶対に消してはいけないデータ")

    dummy_pdf = tmp_path / "dummy.pdf"
    _create_sample_pdf(dummy_pdf, 1)

    chapters = [["01", 1, 1]]

    chapter_splitter.split_pdf(str(dummy_pdf), str(out_dir), chapters)

    assert (out_dir / "01.pdf").exists()
    assert important_file.exists(), "非 PDF ファイルが rmtree によって削除されてしまいました"
    assert important_file.read_text() == "絶対に消してはいけないデータ"


def test_split_page_range_evenly_validation() -> None:
    """_split_page_range_evenly の入力バリデーション確認。"""
    with pytest.raises(ValueError, match="start_page は end_page 以下である必要があります"):
        chapter_splitter._split_page_range_evenly(5, 3, 2)


def test_split_page_range_evenly_logic() -> None:
    """_split_page_range_evenly で均等に分割されることの確認。"""
    # 10ページを3分割 -> 4, 3, 3
    ranges = chapter_splitter._split_page_range_evenly(1, 10, 3)
    assert ranges == [(1, 4), (5, 7), (8, 10)]


def test_plan_pdf_ranges_validation(tmp_path: Path) -> None:
    """_plan_pdf_ranges の入力バリデーション確認。"""
    sample_pdf = tmp_path / "sample.pdf"
    _create_sample_pdf(sample_pdf, 3)
    reader = PdfReader(str(sample_pdf))

    with pytest.raises(ValueError, match="start_page は end_page 以下である必要があります"):
        chapter_splitter._plan_pdf_ranges(reader, 3, 1)


def test_plan_pdf_ranges_exceeds_single_page(tmp_path: Path) -> None:
    """1ページでも上限バイトを超える場合に ValueError が発生することの確認。"""
    sample_pdf = tmp_path / "sample.pdf"
    _create_sample_pdf(sample_pdf, 3)
    reader = PdfReader(str(sample_pdf))

    # 極小の max_size_bytes を指定して必ず超過させる
    with pytest.raises(ValueError, match="1 ページごとに分割してもサイズ上限を超えるため"):
        chapter_splitter._plan_pdf_ranges(reader, 1, 3, max_size_bytes=10)


def test_split_pdf_multi_part(tmp_path: Path) -> None:
    """サイズ超過により複数パートに分割される場合の確認。"""
    sample_pdf = tmp_path / "sample.pdf"
    _create_sample_pdf(sample_pdf, 6)
    reader = PdfReader(str(sample_pdf))
    total_size = chapter_splitter._measure_pdf_size(reader, 1, 6)

    out_dir = tmp_path / "out"
    # 上限サイズを全体の約半分にして、2分割させる
    half_size = total_size // 2 + 100
    chapters = [["Chapter_A", 1, 6]]

    chapter_splitter.split_pdf(str(sample_pdf), str(out_dir), chapters, max_size_bytes=half_size)

    # 複数パートが作成されていること
    part1 = out_dir / "Chapter_A_part01.pdf"
    part2 = out_dir / "Chapter_A_part02.pdf"
    assert part1.exists()
    assert part2.exists()

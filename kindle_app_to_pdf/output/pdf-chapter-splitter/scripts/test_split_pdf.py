import importlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


MAX_SIZE = 20 * 1024 * 1024
PAGE = 1024 * 1024


def load_module():
    fake_pypdf = types.ModuleType("pypdf")

    class PlaceholderReader:
        def __init__(self, *_args, **_kwargs):
            self.pages = []

    class PlaceholderWriter:
        def add_page(self, _page):
            raise AssertionError("PdfWriter should be replaced in the test")

        def write(self, _fileobj):
            raise AssertionError("PdfWriter should be replaced in the test")

    fake_pypdf.PdfReader = PlaceholderReader
    fake_pypdf.PdfWriter = PlaceholderWriter
    sys.modules["pypdf"] = fake_pypdf
    sys.modules.pop("PyPDF2", None)
    sys.modules.pop("split_pdf", None)
    return importlib.import_module("split_pdf")


def measure_from_page_sizes(page_sizes):
    def _measure(_reader, start_page, end_page):
        return sum(page_sizes[start_page - 1 : end_page])

    return _measure


class SplitPdfTests(unittest.TestCase):
    def test_split_pdf_keeps_a_single_file_when_under_limit(self):
        module = load_module()
        page_sizes = [5 * PAGE, 5 * PAGE, 5 * PAGE]
        module._measure_pdf_size = measure_from_page_sizes(page_sizes)

        class FakeReader:
            def __init__(self, _path):
                self.pages = ["page-1", "page-2", "page-3"]

        class FakeWriter:
            written_page_counts = []

            def __init__(self):
                self.pages = []

            def add_page(self, page):
                self.pages.append(page)

            def write(self, fileobj):
                fileobj.write(b"x" * len(self.pages))
                self.__class__.written_page_counts.append(len(self.pages))

        module.PdfReader = FakeReader
        module.PdfWriter = FakeWriter

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "out"
            output_dir.mkdir()
            (output_dir / "stale.txt").write_text("old")

            module.split_pdf("input.pdf", str(output_dir), [["chapter", 1, 3]])

            self.assertEqual(sorted(p.name for p in output_dir.iterdir()), ["chapter.pdf"])
            self.assertEqual(FakeWriter.written_page_counts, [3])

    def test_split_pdf_uses_balanced_page_counts_for_split_files(self):
        module = load_module()
        page_sizes = [6 * PAGE] * 9
        module._measure_pdf_size = measure_from_page_sizes(page_sizes)

        class FakeReader:
            def __init__(self, _path):
                self.pages = [f"page-{index}" for index in range(1, 10)]

        class FakeWriter:
            written_page_counts = []

            def __init__(self):
                self.pages = []

            def add_page(self, page):
                self.pages.append(page)

            def write(self, fileobj):
                fileobj.write(b"x" * len(self.pages))
                self.__class__.written_page_counts.append(len(self.pages))

        module.PdfReader = FakeReader
        module.PdfWriter = FakeWriter

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "out"
            output_dir.mkdir()
            (output_dir / "stale.txt").write_text("old")

            module.split_pdf("input.pdf", str(output_dir), [["chapter", 1, 9]])

            self.assertEqual(
                sorted(p.name for p in output_dir.iterdir()),
                [
                    "chapter_part01.pdf",
                    "chapter_part02.pdf",
                    "chapter_part03.pdf",
                ],
            )
            self.assertEqual(FakeWriter.written_page_counts, [3, 3, 3])

    def test_plan_pdf_ranges_keeps_splits_balanced_even_when_more_parts_are_needed(self):
        module = load_module()
        page_sizes = [12 * PAGE] * 6
        module._measure_pdf_size = measure_from_page_sizes(page_sizes)

        ranges = module._plan_pdf_ranges(object(), 1, 6, MAX_SIZE)

        self.assertEqual(ranges, [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6)])


if __name__ == "__main__":
    unittest.main()

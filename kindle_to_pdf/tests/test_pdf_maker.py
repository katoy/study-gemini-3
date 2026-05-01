"""pdf_maker モジュールのユニットテスト。"""

import struct
import zlib
from pathlib import Path

import pytest

from pdf_maker import make_pdf


def _make_test_png(path: Path, width: int = 100, height: int = 100) -> None:
    """テスト用の PNG ファイルを生成する。"""
    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc & 0xFFFFFFFF)
    # IDAT (each row: filter byte 0 + width*3 bytes RGB)
    raw = b""
    for _ in range(height):
        raw += b"\x00" + b"\xff\xff\xff" * width
    compressed = zlib.compress(raw)
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc & 0xFFFFFFFF)
    # IEND
    iend_crc = zlib.crc32(b"IEND")
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend)


class TestMakePdf:
    """make_pdf のテスト。"""

    def test_empty_screenshots_raises(self):
        with pytest.raises(ValueError, match="0 枚"):
            make_pdf(screenshots=[], output_path="/tmp/test.pdf")

    def test_creates_pdf_from_pngs(self, tmp_path):
        """最小限の PNG を使って PDF が生成されることを確認する。"""
        png1 = tmp_path / "page_0001.png"
        png2 = tmp_path / "page_0002.png"
        _make_test_png(png1)
        _make_test_png(png2)

        output = tmp_path / "output.pdf"
        make_pdf(screenshots=[str(png1), str(png2)], output_path=str(output))

        assert output.exists()
        assert output.stat().st_size > 0
        assert output.read_bytes()[:5] == b"%PDF-"

    def test_creates_output_directory(self, tmp_path):
        """出力ディレクトリが存在しない場合に自動作成されることを確認する。"""
        png = tmp_path / "page_0001.png"
        _make_test_png(png)

        output = tmp_path / "subdir" / "nested" / "output.pdf"
        make_pdf(screenshots=[str(png)], output_path=str(output))
        assert output.exists()

"""
pdf_builder.py のテスト。
"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
import cv2
from PIL import Image

from pdf_builder import build_pdf_streaming, make_thumbnail, _build_pdf_pillow


# ── ヘルパー ──────────────────────────────────────────────────────────

def _make_temp_image(tmp_path, name="page.jpg", size=(100, 80)):
    """テスト用の一時 JPEG 画像を作成してパスを返す。"""
    img = Image.new("RGB", size, color=(200, 200, 200))
    path = tmp_path / name
    img.save(str(path))
    return path


# ── _build_pdf_pillow ─────────────────────────────────────────────────

class TestBuildPdfPillow:
    def test_creates_pdf(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        _build_pdf_pillow([img_path], out)
        assert out.exists()

    def test_multiple_pages(self, tmp_path):
        paths = [_make_temp_image(tmp_path, f"p{i}.jpg") for i in range(3)]
        out = tmp_path / "out.pdf"
        _build_pdf_pillow(paths, out)
        assert out.exists()

    def test_no_pages_raises(self, tmp_path):
        out = tmp_path / "out.pdf"
        with pytest.raises(ValueError, match="1枚もありません"):
            _build_pdf_pillow([], out)

    def test_progress_callback_called(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        calls = []
        _build_pdf_pillow([img_path], out, progress_cb=lambda p, m: calls.append((p, m)))
        assert len(calls) >= 2  # 開始 + 進捗 + 完了

    def test_custom_dpi(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        _build_pdf_pillow([img_path], out, dpi=150)
        assert out.exists()

    def test_parent_dir_created(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "subdir" / "out.pdf"
        _build_pdf_pillow([img_path], out)
        assert out.exists()


# ── build_pdf_streaming ───────────────────────────────────────────────

class TestBuildPdfStreaming:
    def test_uses_pillow_when_no_fitz(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        with patch.dict(sys.modules, {"fitz": None}):
            build_pdf_streaming([img_path], out)
        assert out.exists()

    def test_fitz_path_called_via_streaming(self, tmp_path):
        """fitz が利用可能なとき build_pdf_streaming は _build_pdf_fitz を呼ぶ（line 86）。"""
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        with patch("pdf_builder._build_pdf_fitz") as mock_fitz_fn:
            # fitz が利用可能を偽装: sys.modules に fake fitz を追加
            fake_fitz = MagicMock()
            saved = sys.modules.get("fitz")
            sys.modules["fitz"] = fake_fitz
            try:
                build_pdf_streaming([img_path], out)
                mock_fitz_fn.assert_called_once_with([img_path], out, 300, None)
            finally:
                if saved is None:
                    sys.modules.pop("fitz", None)
                else:
                    sys.modules["fitz"] = saved

    def test_uses_fitz_when_available(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        # fitz をフル mock して _build_pdf_fitz が呼ばれることを確認
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_img_doc = MagicMock()
        mock_img_doc.__enter__ = MagicMock(return_value=mock_img_doc)
        mock_img_doc.convert_to_pdf.return_value = b"%PDF-1.4"
        mock_img_pdf = MagicMock()
        mock_img_pdf.__enter__ = MagicMock(return_value=mock_img_pdf)
        # fitz.open(): 最初は pdf_doc, 次は img_doc, 3 番目は img_pdf
        call_count = [0]
        def _open_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_doc
            elif call_count[0] == 2:
                return mock_img_doc
            else:
                return mock_img_pdf
        mock_fitz.open.side_effect = _open_side_effect
        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            from pdf_builder import _build_pdf_fitz
            _build_pdf_fitz([img_path], out, dpi=300, progress_cb=None)
        mock_doc.save.assert_called_once()

    def test_progress_callback(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        calls = []
        with patch.dict(sys.modules, {"fitz": None}):
            build_pdf_streaming([img_path], out,
                                progress_cb=lambda p, m: calls.append((p, m)))
        assert len(calls) >= 1

    def test_fitz_progress_callback(self, tmp_path):
        """fitz パスでも progress_cb が呼ばれる（lines 115-116, 123）。"""
        img_path = _make_temp_image(tmp_path, "p1.jpg")
        out = tmp_path / "out.pdf"
        calls = []
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_img_doc = MagicMock()
        mock_img_doc.__enter__ = MagicMock(return_value=mock_img_doc)
        mock_img_doc.convert_to_pdf.return_value = b"%PDF-1.4"
        mock_img_pdf = MagicMock()
        mock_img_pdf.__enter__ = MagicMock(return_value=mock_img_pdf)
        call_count = [0]
        def _open_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_doc
            elif call_count[0] == 2:
                return mock_img_doc
            else:
                return mock_img_pdf
        mock_fitz.open.side_effect = _open_side_effect
        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            from pdf_builder import _build_pdf_fitz
            _build_pdf_fitz(
                [img_path], out, dpi=300,
                progress_cb=lambda p, m: calls.append((p, m))
            )
        assert len(calls) >= 2  # 進捗 + 完了


# ── make_thumbnail ────────────────────────────────────────────────────

class TestMakeThumbnail:
    def test_returns_pil_image(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg", size=(400, 600))
        result = make_thumbnail(img_path)
        assert isinstance(result, Image.Image)

    def test_default_size(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg", size=(400, 600))
        result = make_thumbnail(img_path)
        assert result.size == (150, 212)

    def test_custom_size(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "p1.jpg", size=(400, 600))
        result = make_thumbnail(img_path, size=(100, 140))
        assert result.size == (100, 140)

    def test_thumbnail_centered_on_white_canvas(self, tmp_path):
        img_path = _make_temp_image(tmp_path, "small.jpg", size=(50, 50))
        result = make_thumbnail(img_path, size=(150, 212))
        # キャンバスサイズは常に指定サイズ
        assert result.size == (150, 212)
        # 四隅は白背景
        corners = [
            result.getpixel((0, 0)),
            result.getpixel((149, 0)),
            result.getpixel((0, 211)),
        ]
        assert all(all(c >= 200 for c in px[:3]) for px in corners)

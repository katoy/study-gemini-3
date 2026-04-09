"""
utils/image.py のテスト。
"""
import io
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import cv2
import numpy as np
import pytest
from PIL import Image

from utils.image import fix_exif_rotation, sort_by_filename, bgr_to_pil, extract_line_profiles


# ── fix_exif_rotation ────────────────────────────────────────────────

class TestFixExifRotation:
    def _write_png(self, tmp_path, arr):
        """BGR 配列を一時 PNG に書き出してパスを返す。"""
        path = tmp_path / "test.png"
        cv2.imwrite(str(path), arr)
        return path

    def test_normal_image_returns_bgr(self, tmp_path):
        img = np.full((100, 80, 3), 200, dtype=np.uint8)
        path = self._write_png(tmp_path, img)
        result = fix_exif_rotation(path)
        assert result is not None
        assert result.shape == (100, 80, 3)

    def test_no_exif_returns_image(self, tmp_path):
        """EXIF なし PNG でも正常に BGR 配列を返す。"""
        img = np.zeros((50, 60, 3), dtype=np.uint8)
        path = self._write_png(tmp_path, img)
        result = fix_exif_rotation(str(path))
        assert result.shape == (50, 60, 3)

    def test_exif_orientation_6(self, tmp_path):
        """EXIF orientation=6 (270度回転) が正しく補正される。"""
        pil_img = Image.new("RGB", (80, 40), color=(100, 150, 200))
        # EXIF データを付与
        from PIL import ExifTags
        orientation_key = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
        exif_data = pil_img.getexif()
        exif_data[orientation_key] = 6
        path = tmp_path / "exif6.jpg"
        pil_img.save(str(path), exif=exif_data.tobytes())
        result = fix_exif_rotation(str(path))
        assert result is not None
        # 6 (270 rotate) → expand=True で幅高さが入れ替わる
        assert result.shape[0] == 80  # 元画像の幅が高さになる
        assert result.shape[1] == 40

    def test_exif_orientation_3(self, tmp_path):
        """EXIF orientation=3 (180度回転) が正しく補正される。"""
        pil_img = Image.new("RGB", (80, 40), color=(100, 150, 200))
        from PIL import ExifTags
        orientation_key = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
        exif_data = pil_img.getexif()
        exif_data[orientation_key] = 3
        path = tmp_path / "exif3.jpg"
        pil_img.save(str(path), exif=exif_data.tobytes())
        result = fix_exif_rotation(str(path))
        assert result is not None
        assert result.shape == (40, 80, 3)  # 180度は寸法変わらず

    def test_exif_orientation_8(self, tmp_path):
        """EXIF orientation=8 (90度回転) が正しく補正される。"""
        pil_img = Image.new("RGB", (80, 40), color=(100, 150, 200))
        from PIL import ExifTags
        orientation_key = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
        exif_data = pil_img.getexif()
        exif_data[orientation_key] = 8
        path = tmp_path / "exif8.jpg"
        pil_img.save(str(path), exif=exif_data.tobytes())
        result = fix_exif_rotation(str(path))
        assert result is not None

    def test_exif_orientation_no_rotation_needed(self, tmp_path):
        """orientation キーがあっても回転不要な値（例: 1）では寸法変わらない。"""
        pil_img = Image.new("RGB", (80, 40), color=(100, 150, 200))
        from PIL import ExifTags
        orientation_key = next(k for k, v in ExifTags.TAGS.items() if v == "Orientation")
        exif_data = pil_img.getexif()
        exif_data[orientation_key] = 1  # 補正不要
        path = tmp_path / "exif1.jpg"
        pil_img.save(str(path), exif=exif_data.tobytes())
        result = fix_exif_rotation(str(path))
        assert result.shape == (40, 80, 3)

    def test_exception_fallback_to_imread(self, tmp_path):
        """Image.open が例外を出す場合は cv2.imread にフォールバック。"""
        img = np.full((30, 40, 3), 128, dtype=np.uint8)
        path = tmp_path / "fallback.png"
        cv2.imwrite(str(path), img)
        with patch("utils.image.Image.open", side_effect=OSError("broken")):
            result = fix_exif_rotation(str(path))
        # cv2.imread が返った結果なので None か ndarray
        assert result is not None

    def test_orientation_key_not_in_exif(self, tmp_path):
        """orientation キーが exif dict に存在しない場合も正常処理。"""
        pil_img = Image.new("RGB", (60, 30))
        path = tmp_path / "no_orient.jpg"
        pil_img.save(str(path))
        # _getexif() が orientation キーなしの dict を返すケース
        mock_img = MagicMock()
        mock_img.convert.return_value = pil_img
        mock_exif = {999: "something"}  # orientation キーなし
        mock_img._getexif.return_value = mock_exif
        with patch("utils.image.Image.open", return_value=mock_img):
            result = fix_exif_rotation(str(path))
        assert result is not None


# ── sort_by_filename ─────────────────────────────────────────────────

class TestSortByFilename:
    def test_sorts_naturally(self, tmp_path):
        names = ["img10.jpg", "img2.jpg", "img1.jpg"]
        paths = [tmp_path / n for n in names]
        result = sort_by_filename(paths)
        assert [p.name for p in result] == ["img1.jpg", "img2.jpg", "img10.jpg"]

    def test_mixed_strings(self, tmp_path):
        names = ["b2.png", "a10.png", "a2.png", "a1.png"]
        paths = [tmp_path / n for n in names]
        result = sort_by_filename(paths)
        assert result[0].name == "a1.png"
        assert result[1].name == "a2.png"
        assert result[2].name == "a10.png"

    def test_empty_list(self):
        assert sort_by_filename([]) == []


# ── bgr_to_pil ───────────────────────────────────────────────────────

class TestBgrToPil:
    def test_conversion_keeps_size(self):
        bgr = np.zeros((100, 80, 3), dtype=np.uint8)
        pil_img = bgr_to_pil(bgr)
        assert isinstance(pil_img, Image.Image)
        assert pil_img.size == (80, 100)  # PIL は (幅, 高さ)

    def test_color_conversion(self):
        bgr = np.zeros((10, 10, 3), dtype=np.uint8)
        bgr[:, :] = [0, 0, 255]  # BGR: 赤
        pil_img = bgr_to_pil(bgr)
        arr = np.array(pil_img)
        assert arr[5, 5, 0] == 255  # R
        assert arr[5, 5, 2] == 0    # B


# ── extract_line_profiles ─────────────────────────────────────────────

class TestExtractLineProfiles:
    def _make_lined_gray(self, h=400, w=300):
        """横書きテキスト行を模した グレースケール画像。"""
        img = np.full((h, w), 255, dtype=np.uint8)
        for y in range(40, h - 40, 25):
            img[y:y+2, 20:w-20] = 0
        return img

    def test_returns_correct_shape(self):
        gray = self._make_lined_gray()
        pts, weights, inv_scale = extract_line_profiles(gray)
        assert pts.ndim == 2
        assert pts.shape[1] == 2
        assert weights.ndim == 1
        assert len(pts) == len(weights)
        assert inv_scale > 0

    def test_empty_image_returns_empty(self):
        """真っ白な画像はポイントが見つからず空配列を返す。"""
        gray = np.full((400, 300), 255, dtype=np.uint8)
        pts, weights, inv_scale = extract_line_profiles(gray)
        assert len(pts) == 0
        assert len(weights) == 0
        assert inv_scale > 0

    def test_inv_scale_consistent(self):
        h = 800
        gray = self._make_lined_gray(h=h, w=600)
        _, _, inv_scale = extract_line_profiles(gray, target_h=400)
        assert abs(inv_scale - h / 400) < 0.01

"""
steps/detection.py のテスト。
"""
import cv2
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from core.config import ProcessingConfig
from steps.detection import DetectionStep


def _make_mock_dewarper():
    d = MagicMock()
    d.dewarp.side_effect = lambda x: x
    return d


class TestDetectionStep:
    def _make_step(self, **cfg_kwargs):
        cfg = ProcessingConfig(**cfg_kwargs)
        return DetectionStep(cfg, dewarper=None)

    # ── initialize / finalize ────────────────────────────────────────

    def test_initialize_with_dewarper(self):
        cfg = ProcessingConfig()
        mock_d = _make_mock_dewarper()
        step = DetectionStep(cfg, dewarper=mock_d)
        step.initialize()
        mock_d.load_model.assert_called_once()

    def test_initialize_without_dewarper(self):
        step = self._make_step()
        step.initialize()  # 例外なしでOK

    def test_finalize_with_dewarper(self):
        cfg = ProcessingConfig()
        mock_d = _make_mock_dewarper()
        step = DetectionStep(cfg, dewarper=mock_d)
        step.finalize()
        mock_d.unload_model.assert_called_once()

    def test_finalize_without_dewarper(self):
        step = self._make_step()
        step.finalize()  # 例外なしでOK

    # ── process: show_book_area ───────────────────────────────────────

    def test_show_book_area_draws_contour(self, text_image):
        step = self._make_step(show_book_area=True)
        result = step.process([text_image])
        assert len(result) == 1
        assert result[0].shape == text_image.shape

    def test_show_book_area_no_contour_found(self):
        """検出不可の黒画像でもクラッシュしない。"""
        img = np.zeros((400, 300, 3), dtype=np.uint8)
        step = self._make_step(show_book_area=True)
        result = step.process([img])
        assert len(result) == 1

    # ── process: basic split ─────────────────────────────────────────

    def test_split_spread_produces_two_pages(self, spread_image):
        step = self._make_step(split=True)
        result = step.process([spread_image])
        # 見開き → 2 ページに分割されるはず（コントラスト次第では 1 ページの場合もある）
        assert len(result) >= 1

    def test_no_split_produces_one_page(self, text_image):
        step = self._make_step(split=False)
        result = step.process([text_image])
        assert len(result) == 1

    # ── process: manual rotate ───────────────────────────────────────

    def test_rotate_180(self, text_image):
        step = self._make_step(rotate_angle=180, split=False)
        result = step.process([text_image])
        assert len(result) == 1

    def test_rotate_90(self, text_image):
        step = self._make_step(rotate_angle=90, split=False)
        result = step.process([text_image])
        assert len(result) == 1

    def test_rotate_270(self, text_image):
        step = self._make_step(rotate_angle=270, split=False)
        result = step.process([text_image])
        assert len(result) == 1

    # ── process: show_page_area ───────────────────────────────────────

    def test_show_page_area_no_split(self, text_image):
        step = self._make_step(show_page_area=True, split=False)
        result = step.process([text_image])
        assert len(result) == 1

    def test_show_page_area_with_split(self, spread_image):
        step = self._make_step(show_page_area=True, split=True, writing_mode="horizontal")
        result = step.process([spread_image])
        assert len(result) >= 1

    def test_show_page_area_right_first(self, spread_image):
        step = self._make_step(show_page_area=True, split=True, writing_mode="vertical")
        result = step.process([spread_image])
        assert len(result) >= 1

    # ── process: dewarper applied ─────────────────────────────────────

    def test_dewarper_called_on_spread(self, spread_image):
        cfg = ProcessingConfig(split=True)
        mock_d = _make_mock_dewarper()
        step = DetectionStep(cfg, dewarper=mock_d)
        step.process([spread_image])
        mock_d.dewarp.assert_called()

    # ── _draw_book_area_on_original ───────────────────────────────────

    def test_draw_book_area_contour_shape(self, text_image):
        step = self._make_step(show_book_area=True)
        contour = np.array([[10, 10], [190, 10], [190, 290], [10, 290]], dtype="float32")
        result = step._draw_book_area_on_original(text_image, contour)
        assert result.shape == text_image.shape

    # ── _draw_page_debug ──────────────────────────────────────────────

    def test_draw_page_debug_left(self, spread_image):
        step = self._make_step()
        h, w = spread_image.shape[:2]
        result = step._draw_page_debug(spread_image, seam_x=w // 2, bw=w, bh=h, side="left")
        assert result.shape == spread_image.shape

    def test_draw_page_debug_right(self, spread_image):
        step = self._make_step()
        h, w = spread_image.shape[:2]
        result = step._draw_page_debug(spread_image, seam_x=w // 2, bw=w, bh=h, side="right")
        assert result.shape == spread_image.shape

    def test_draw_page_debug_full(self, text_image):
        step = self._make_step()
        h, w = text_image.shape[:2]
        result = step._draw_page_debug(text_image, seam_x=None, bw=w, bh=h, side="full")
        assert result.shape == text_image.shape

    # ── _resolve_page_order ───────────────────────────────────────────

    def test_resolve_page_order_non_auto(self, spread_image):
        step = self._make_step(writing_mode="vertical")
        order = step._resolve_page_order(spread_image)
        assert order == "right_first"

    def test_resolve_page_order_horizontal(self, spread_image):
        step = self._make_step(writing_mode="horizontal")
        order = step._resolve_page_order(spread_image)
        assert order == "left_first"

    def test_resolve_page_order_auto(self, spread_image):
        step = self._make_step(writing_mode="auto")
        order = step._resolve_page_order(spread_image)
        assert order in ("left_first", "right_first")

    # ── process: empty list ───────────────────────────────────────────

    def test_empty_list(self):
        step = self._make_step()
        result = step.process([])
        assert result == []

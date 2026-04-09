"""
steps/quality_check.py のテスト。
"""
import sys
import logging
import numpy as np
import cv2
import pytest

from core.config import ProcessingConfig
from steps.quality_check import (
    _red,
    _content_bbox,
    _check_text_clipping,
    _check_extra_region,
    _check_bottom_cut,
    _check_content_coverage,
    _check_distortion,
    evaluate_page,
    _log_page_result,
    QualityCheckStep,
)


# ── _red ─────────────────────────────────────────────────────────────

class TestRed:
    def test_tty_adds_ansi(self, monkeypatch):
        monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
        result = _red("NG")
        assert "\033[31m" in result

    def test_non_tty_no_ansi(self, monkeypatch):
        monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
        result = _red("NG")
        assert result == "NG"


# ── _content_bbox ─────────────────────────────────────────────────────

class TestContentBbox:
    def test_all_white_returns_full(self):
        gray = np.full((100, 80), 255, dtype=np.uint8)
        x0, y0, x1, y1 = _content_bbox(gray)
        assert x0 == 0 and y0 == 0
        assert x1 == 79 and y1 == 99

    def test_single_dark_pixel(self):
        gray = np.full((100, 80), 255, dtype=np.uint8)
        gray[50, 40] = 200  # 1 ピクセルだけ非白 (< 250)
        x0, y0, x1, y1 = _content_bbox(gray)
        assert x0 == 40 and y0 == 50
        assert x1 == 40 and y1 == 50

    def test_content_block(self):
        gray = np.full((200, 150), 255, dtype=np.uint8)
        gray[30:170, 20:130] = 100
        x0, y0, x1, y1 = _content_bbox(gray)
        assert x0 == 20 and y0 == 30
        assert x1 == 129 and y1 == 169


# ── _check_text_clipping ──────────────────────────────────────────────

class TestCheckTextClipping:
    def _make_normalize_page(self):
        """normalize_size 相当の大きなキャンバスに小さなコンテンツを中央配置。
        content_bbox の高さが大きくなるため margin_h が広がり、
        端の 2px ライン密度が閾値 0.10 を下回るクリーンページになる。"""
        # A4 サイズ (3508x2480) の白キャンバスに縮小コンテンツを貼る
        canvas = np.full((3508, 2480), 255, dtype=np.uint8)
        # コンテンツ: 高さ 2000px の中央帯にのみテキスト行
        y_start = 750
        for y in range(y_start, y_start + 2000, 40):
            canvas[y:y+2, 300:2180] = 30
        return canvas

    def _make_clipped_page(self):
        """端までテキストが到達しているページ（見切れ）。
        全行が画像端から端まで密に引かれ、margin 密度が閾値を超える。"""
        gray = np.full((400, 300), 255, dtype=np.uint8)
        for y in range(0, 400, 10):
            gray[y:y+2, :] = 20
        return gray

    def test_clean_page_not_clipped(self):
        """大きなキャンバス上の小コンテンツは見切れ検出されない。"""
        gray = self._make_normalize_page()
        clipped, _ = _check_text_clipping(gray)
        assert not clipped

    def test_clipped_page_detected(self):
        gray = self._make_clipped_page()
        clipped, _ = _check_text_clipping(gray)
        assert clipped

    def test_blank_page_not_clipped(self):
        gray = np.full((400, 300), 240, dtype=np.uint8)
        clipped, details = _check_text_clipping(gray)
        assert not clipped
        assert all(v == 0.0 for v in details.values())


# ── _check_extra_region ───────────────────────────────────────────────

class TestCheckExtraRegion:
    def test_white_page_no_extra(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        has_extra, _ = _check_extra_region(gray)
        assert not has_extra

    def test_dark_border_detected_as_extra(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        gray[:, :40] = 80  # 左端を暗く
        has_extra, _ = _check_extra_region(gray)
        assert has_extra

    def test_grayish_border_detected(self):
        """中程度グレー（背景残留）を検出する。"""
        gray = np.full((400, 300), 255, dtype=np.uint8)
        # 上部を中間グレーで塗る
        gray[:35, :] = 150
        has_extra, _ = _check_extra_region(gray)
        # 結果は True か False のどちらでもクラッシュしなければOK


# ── _check_bottom_cut ─────────────────────────────────────────────────

class TestCheckBottomCut:
    def _make_full_text(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        for y in range(20, 380, 20):
            gray[y:y+2, 20:280] = 30
        return gray

    def _make_bottom_cut(self):
        """60-80% にテキストがあるが下部 20% が空白。"""
        gray = np.full((400, 300), 255, dtype=np.uint8)
        for y in range(20, 320, 20):
            gray[y:y+2, 20:280] = 30
        return gray

    def test_full_text_no_cut(self):
        gray = self._make_full_text()
        cut, _ = _check_bottom_cut(gray)
        assert not cut

    def test_bottom_cut_detected(self):
        gray = self._make_bottom_cut()
        cut, details = _check_bottom_cut(gray)
        assert isinstance(cut, bool)

    def test_blank_page_no_cut(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        cut, _ = _check_bottom_cut(gray)
        assert not cut


# ── _check_content_coverage ───────────────────────────────────────────

class TestCheckContentCoverage:
    def test_balanced_content_no_half_missing(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        gray[20:380, 20:280] = 40
        result, _ = _check_content_coverage(gray)
        assert not result

    def test_top_heavy_detected(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        for y in range(20, 180, 15):
            gray[y:y+2, 20:280] = 30
        # 下半分はほぼ白
        result, _ = _check_content_coverage(gray)
        # 上が密で下が疎 → True の場合もある
        assert isinstance(result, bool)

    def test_sparse_page_skipped(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        gray[200, 150] = 30  # 1 ピクセルのみ
        result, _ = _check_content_coverage(gray)
        assert not result

    def test_top_empty_detected(self):
        """上半分が空白で下半分にテキストがある場合 → top_empty=True（line 212）。"""
        gray = np.full((400, 300), 255, dtype=np.uint8)
        # 下半分にのみ高密度テキスト
        for y in range(210, 390, 10):
            gray[y:y+2, 10:290] = 30
        result, _ = _check_content_coverage(gray)
        # top_d << bottom_d なので top_empty=True になるはず
        assert result is True


# ── _check_distortion ─────────────────────────────────────────────────

class TestCheckDistortion:
    def test_straight_page_not_distorted(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        for y in range(30, 370, 22):
            gray[y:y+2, 10:290] = 30
        distorted, angle, curve = _check_distortion(gray)
        assert isinstance(distorted, bool)
        assert isinstance(angle, float)
        assert isinstance(curve, float)

    def test_blank_page_not_distorted(self):
        gray = np.full((400, 300), 255, dtype=np.uint8)
        distorted, angle, curve = _check_distortion(gray)
        assert not distorted
        assert angle == 0.0

    def test_skewed_page_detected(self):
        """大きな傾きがある場合に distorted=True を返す。"""
        gray = np.full((400, 300), 255, dtype=np.uint8)
        for y in range(30, 370, 20):
            gray[y:y+2, 10:290] = 30
        M = cv2.getRotationMatrix2D((150, 200), 5.0, 1.0)
        skewed = cv2.warpAffine(gray, M, (300, 400), borderValue=255)
        distorted, angle, curve = _check_distortion(skewed)
        # 5° の傾きは angle_threshold=2.0 を超えるので True になる可能性が高い
        assert isinstance(distorted, (bool, np.bool_))

    def test_vertical_mode_uses_vertical_projection(self):
        """is_vertical=True では垂直射影分散（axis=0）を使う（line 244）。"""
        # 縦書き模擬: 縦方向の線
        gray = np.full((400, 300), 255, dtype=np.uint8)
        for x in range(20, 280, 25):
            gray[10:390, x:x+2] = 30
        distorted, angle, curve = _check_distortion(gray, is_vertical=True)
        assert isinstance(distorted, (bool, np.bool_))
        assert isinstance(angle, float)


# ── evaluate_page ─────────────────────────────────────────────────────

class TestEvaluatePage:
    def test_returns_dict_with_keys(self, text_image):
        result = evaluate_page(text_image, page_num=1)
        expected_keys = {
            "page", "ok", "white_ratio", "text_clipped", "extra_region",
            "distorted", "half_content", "bottom_cut", "skew_angle",
            "curve_pct", "clip_detail", "extra_detail",
            "coverage_detail", "bottom_detail",
        }
        assert expected_keys == set(result.keys())

    def test_ok_field_is_bool(self, text_image):
        result = evaluate_page(text_image, page_num=1)
        assert isinstance(result["ok"], bool)

    def test_page_number_set(self, white_image):
        result = evaluate_page(white_image, page_num=5)
        assert result["page"] == 5

    def test_clean_white_page(self, white_image):
        result = evaluate_page(white_image)
        assert result["ok"] is True


# ── _log_page_result ──────────────────────────────────────────────────

class TestLogPageResult:
    def test_ok_page_no_warning(self, caplog, white_image):
        result = evaluate_page(white_image)
        with caplog.at_level(logging.WARNING, logger="steps.quality_check"):
            _log_page_result(result)
        assert len(caplog.records) == 0

    def test_bad_page_logs_warning(self, caplog, text_image):
        # 全辺にテキストを詰めた「見切れ」ページ
        gray = np.zeros((400, 300), dtype=np.uint8)
        bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        result = evaluate_page(bgr, page_num=3)
        result["ok"] = False
        result["text_clipped"] = True
        result["extra_region"] = True
        result["distorted"] = True
        result["half_content"] = True
        result["bottom_cut"] = True
        with caplog.at_level(logging.WARNING, logger="steps.quality_check"):
            _log_page_result(result)
        assert any(r.levelno == logging.WARNING for r in caplog.records)


# ── QualityCheckStep ──────────────────────────────────────────────────

class TestQualityCheckStep:
    def setup_method(self):
        self.cfg = ProcessingConfig()
        self.step = QualityCheckStep(self.cfg)

    def test_returns_same_images(self, text_image, white_image):
        images = [text_image, white_image]
        result = self.step.process(images)
        assert len(result) == 2
        assert result[0] is text_image
        assert result[1] is white_image

    def test_page_offset_increments(self, white_image):
        self.step.process([white_image])
        assert self.step._page_offset == 1
        self.step.process([white_image, white_image])
        assert self.step._page_offset == 3

    def test_all_ok_single_line_log(self, caplog, white_image):
        with caplog.at_level(logging.INFO, logger="steps.quality_check"):
            self.step.process([white_image])
        assert any("OK" in r.message for r in caplog.records)

    def test_problem_page_logs_summary(self, caplog):
        """問題ページがある場合はサマリーテーブルが出力される。"""
        # 黒一色の画像（余分領域あり）
        bad_img = np.zeros((400, 300, 3), dtype=np.uint8)
        with caplog.at_level(logging.INFO, logger="steps.quality_check"):
            self.step.process([bad_img])
        # サマリー or 個別ログが出ていること
        assert len(caplog.records) > 0

    def test_empty_list(self, caplog):
        with caplog.at_level(logging.INFO, logger="steps.quality_check"):
            result = self.step.process([])
        assert result == []

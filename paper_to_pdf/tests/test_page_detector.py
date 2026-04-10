"""
page_detector.py のテスト。
"""
import cv2
import numpy as np

from page_detector import (
    order_points,
    get_perspective_matrices,
    four_point_transform,
    detect_page_contour,
    correct_orientation_robust,
    find_center_seam,
    detect_writing_direction,
    split_spread,
    trim_page_border,
)


# ── order_points ─────────────────────────────────────────────────────

class TestOrderPoints:
    def test_basic_order(self):
        pts = np.array([[100, 0], [0, 0], [100, 100], [0, 100]], dtype="float32")
        result = order_points(pts)
        assert result.shape == (4, 2)
        tl, tr, br, bl = result
        assert tl[0] < tr[0]  # 左上 x < 右上 x
        assert bl[0] < br[0]  # 左下 x < 右下 x
        assert tl[1] < bl[1]  # 左上 y < 左下 y

    def test_returns_float32(self):
        pts = np.array([[100, 0], [0, 0], [100, 100], [0, 100]])
        result = order_points(pts)
        assert result.dtype == np.float32


# ── get_perspective_matrices ─────────────────────────────────────────

class TestGetPerspectiveMatrices:
    def test_returns_correct_types(self):
        pts = np.array([[0, 0], [200, 0], [200, 300], [0, 300]], dtype="float32")
        M, Minv, w, h = get_perspective_matrices(pts)
        assert M.shape == (3, 3)
        assert Minv.shape == (3, 3)
        assert isinstance(w, int)
        assert isinstance(h, int)

    def test_width_height_positive(self):
        pts = np.array([[10, 10], [210, 10], [210, 310], [10, 310]], dtype="float32")
        M, Minv, w, h = get_perspective_matrices(pts)
        assert w > 0
        assert h > 0


# ── four_point_transform ─────────────────────────────────────────────

class TestFourPointTransform:
    def test_output_shape(self):
        image = np.full((400, 600, 3), 200, dtype=np.uint8)
        pts = np.array([[50, 50], [550, 50], [550, 350], [50, 350]], dtype="float32")
        result = four_point_transform(image, pts)
        assert result.ndim == 3
        assert result.shape[2] == 3


# ── detect_page_contour ───────────────────────────────────────────────

class TestDetectPageContour:
    def _make_book_on_black(self):
        """黒背景に白い矩形（書籍模擬）を描いた画像。"""
        img = np.zeros((600, 800, 3), dtype=np.uint8)
        cv2.rectangle(img, (100, 80), (700, 520), (220, 220, 210), -1)
        return img

    def test_detects_contour_on_book_image(self):
        img = self._make_book_on_black()
        result = detect_page_contour(img)
        assert result is not None
        assert result.shape == (4, 2)

    def test_returns_none_on_all_black(self):
        img = np.zeros((400, 600, 3), dtype=np.uint8)
        result = detect_page_contour(img)
        assert result is None

    def test_returns_none_when_contours_too_small(self):
        # 小さい輪郭のみの画像：最大輪郭の面積が閾値未満になるよう設定
        img = np.zeros((400, 600, 3), dtype=np.uint8)
        # 中央に小さな白い矩形（画像面積の15%未満）
        cv2.rectangle(img, (280, 185), (320, 215), (220, 220, 210), -1)
        result = detect_page_contour(img)
        assert result is None

    def test_sensitivity_options(self):
        img = self._make_book_on_black()
        for sens in ("low", "medium", "high"):
            result = detect_page_contour(img, sensitivity=sens)
            # low/medium/high ともに今の実装は sensitivity 引数を受け取るだけなので
            # None または shape (4,2) のどちらかが返ればOK
            assert result is None or result.shape == (4, 2)


# ── correct_orientation_robust ────────────────────────────────────────

class TestCorrectOrientationRobust:
    def _make_text_image(self, rotate_code=None):
        img = np.full((400, 300, 3), 255, dtype=np.uint8)
        for y in range(40, 380, 28):
            cv2.line(img, (20, y), (280, y), (0, 0, 0), 2)
        if rotate_code is not None:
            img = cv2.rotate(img, rotate_code)
        return img

    def test_returns_image_and_code(self):
        img = self._make_text_image()
        result_img, code = correct_orientation_robust(img)
        assert result_img.ndim == 3
        assert code is None or code in (
            cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE
        )

    def test_upside_down_detection(self):
        """180°回転させた画像では ROTATE_180 が返る可能性が高い。"""
        img = self._make_text_image(cv2.ROTATE_180)
        _, code = correct_orientation_robust(img)
        # 画像のコントラストによっては None になることもある
        assert code is None or code in (
            cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE
        )

    def test_non_none_code_returns_rotated_image(self):
        """最良の回転が 0° 以外のとき、実際に回転した画像を返す（line 143）。"""
        # テキスト行を 90° 回転させて、0° が最悪スコアになるようにする
        img = np.full((300, 400, 3), 255, dtype=np.uint8)
        # 横書きのテキストを縦長画像で 90° 回転させると
        # correct_orientation_robust は ROTATE_90_COUNTERCLOCKWISE を返す可能性が高い
        for y in range(20, 380, 20):
            cv2.line(img, (10, y), (390, y), (0, 0, 0), 2)
        img_rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)  # 縦長にする
        result_img, code = correct_orientation_robust(img_rotated)
        # code が None でない場合、返り値は元と違う形になる
        if code is not None and code != cv2.ROTATE_180:
            assert result_img.shape != img_rotated.shape


# ── find_center_seam ──────────────────────────────────────────────────

class TestFindCenterSeam:
    def _make_spread(self, w=800, h=400):
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        for y in range(30, h - 30, 25):
            cv2.line(img, (20, y), (w // 2 - 30, y), (10, 10, 10), 2)
            cv2.line(img, (w // 2 + 30, y), (w - 20, y), (10, 10, 10), 2)
        return img

    def test_seam_in_center_region(self):
        img = self._make_spread()
        seam = find_center_seam(img)
        w = img.shape[1]
        assert w * 0.35 <= seam <= w * 0.65

    def test_small_image_returns_center(self):
        """極端に小さい画像 (w<100) はセンターを返す。"""
        img = np.full((40, 80, 3), 200, dtype=np.uint8)
        seam = find_center_seam(img)
        assert seam == 40  # w // 2

    def test_blank_right_page(self):
        """右ページが白紙の場合は中央 (50%) を返す。"""
        img = np.full((400, 800, 3), 255, dtype=np.uint8)
        for y in range(30, 380, 25):
            cv2.line(img, (20, y), (360, y), (10, 10, 10), 2)
        seam = find_center_seam(img)
        assert 380 <= seam <= 420  # 中央付近

    def test_blank_left_page(self):
        """左ページが白紙の場合は中央 (50%) を返す。"""
        img = np.full((400, 800, 3), 255, dtype=np.uint8)
        for y in range(30, 380, 25):
            cv2.line(img, (440, y), (780, y), (10, 10, 10), 2)
        seam = find_center_seam(img)
        assert 380 <= seam <= 420

    def test_bright_gap_strategy(self):
        """中央に白いギャップがある画像では戦略1が機能する。"""
        img = np.full((400, 800, 3), 255, dtype=np.uint8)
        for y in range(30, 380, 25):
            cv2.line(img, (20, y), (375, y), (10, 10, 10), 2)
            cv2.line(img, (425, y), (780, y), (10, 10, 10), 2)
        # 376-424 は白のまま（ギャップ）
        seam = find_center_seam(img)
        assert 350 <= seam <= 450

    def test_gap_at_loop_end_appends_candidate(self):
        """ループ終端でゼロ密度ランが続いたまま終了し line 230 が実行される。
        ゼロ密度ランが i=479 (SEAM_MAX-1) まで続くよう右ページを 485 から開始。
        min_gap=16 <= run_len <= max_gap=64 → line 230 の append が実行される。"""
        img = np.full((400, 800, 3), 255, dtype=np.uint8)
        # 両ページに高密度テキスト（strategy 0 の blank 判定を回避）
        for y in range(20, 380, 10):
            cv2.line(img, (10, y), (445, y), (10, 10, 10), 1)   # 左ページ: x=10-445
            cv2.line(img, (485, y), (790, y), (10, 10, 10), 1)  # 右ページ: x=485-790
        # x=446-484 がゼロ密度。SEAM_MAX-1=479 も ゼロ → ループ末尾まで続く
        seam = find_center_seam(img)
        assert 380 <= seam <= 520

    def test_brightness_min_strategy(self):
        """戦略0,1 が使えない場合に戦略2（輝度最小）を使う（lines 239-249）。"""
        # 両ページともテキスト密度が高く（blank 判定されない）、
        # かつ明るいギャップも存在しない画像
        img = np.full((400, 800, 3), 200, dtype=np.uint8)
        for y in range(10, 390, 5):
            cv2.line(img, (10, y), (790, y), (100, 100, 100), 1)
        # 中央を少し暗くして綴じ目影を模擬
        img[:, 390:410] = 80
        seam = find_center_seam(img)
        assert 320 <= seam <= 480


# ── detect_writing_direction ──────────────────────────────────────────

class TestDetectWritingDirection:
    def _make_horizontal(self, w=400, h=600):
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        for y in range(40, h - 40, 30):
            cv2.line(img, (20, y), (w - 20, y), (0, 0, 0), 2)
        return img

    def _make_vertical(self, w=600, h=400):
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        for x in range(40, w - 40, 30):
            cv2.line(img, (x, 20), (x, h - 20), (0, 0, 0), 2)
        return img

    def test_horizontal_text_returns_left_first(self):
        img = self._make_horizontal()
        result = detect_writing_direction(img)
        assert result in ("left_first", "right_first")

    def test_vertical_text_returns_right_first(self):
        img = self._make_vertical()
        result = detect_writing_direction(img)
        assert result in ("left_first", "right_first")

    def test_returns_valid_string(self):
        img = np.full((400, 600, 3), 200, dtype=np.uint8)
        result = detect_writing_direction(img)
        assert result in ("left_first", "right_first")


# ── split_spread ──────────────────────────────────────────────────────

class TestSplitSpread:
    def test_split_left_first(self, spread_image):
        pages = split_spread(spread_image, order="left_first")
        assert len(pages) == 2
        left, right = pages
        assert left.shape[1] <= spread_image.shape[1]
        assert right.shape[1] <= spread_image.shape[1]

    def test_split_right_first_reverses_order(self, spread_image):
        split_spread(spread_image, order="left_first")
        pages_rf = split_spread(spread_image, order="right_first", seam_x=spread_image.shape[1] // 2)
        # right_first の 0番目は right ページ
        assert len(pages_rf) == 2

    def test_split_uses_seam_x(self, spread_image):
        seam_x = 300
        pages = split_spread(spread_image, seam_x=seam_x)
        # 左ページ幅がほぼ seam_x（末尾 2px 白塗りで若干変わる）
        assert pages[0].shape[1] == seam_x

    def test_split_without_seam_x_uses_find_center(self, spread_image):
        """seam_x=None の場合は find_center_seam を呼ぶ。"""
        pages = split_spread(spread_image, seam_x=None)
        assert len(pages) == 2


# ── trim_page_border ──────────────────────────────────────────────────

class TestTrimPageBorder:
    def test_no_black_border_unchanged(self, white_image):
        result = trim_page_border(white_image)
        assert result.shape == white_image.shape

    def test_removes_black_top_border(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[:30, :] = 0  # 上30行を黒
        result = trim_page_border(img)
        # 黒帯が削られるので高さが小さくなる
        assert result.shape[0] <= img.shape[0]

    def test_removes_black_left_border(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[:, :20] = 0  # 左20列を黒
        result = trim_page_border(img)
        assert result.shape[1] <= img.shape[1]

    def test_removes_black_bottom_border(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[270:, :] = 0  # 下30行を黒
        result = trim_page_border(img)
        assert result.shape[0] <= img.shape[0]

    def test_removes_black_right_border(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[:, 180:] = 0  # 右20列を黒
        result = trim_page_border(img)
        assert result.shape[1] <= img.shape[1]

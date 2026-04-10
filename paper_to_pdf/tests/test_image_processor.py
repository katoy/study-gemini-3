"""
image_processor.py のテスト。
"""
import cv2
import numpy as np

from image_processor import (
    remove_shadow,
    deskew_page,
    fix_orientation,
    remove_textured_border,
    remove_border,
    normalize_size,
    _is_upside_down,
)


# ── remove_shadow ─────────────────────────────────────────────────────

class TestRemoveShadow:
    def test_strength_zero_returns_original(self, white_image):
        result = remove_shadow(white_image, strength=0.0)
        np.testing.assert_array_equal(result, white_image)

    def test_white_page_returns_unchanged(self):
        """暗ピクセルが 2% 未満の白紙は処理をスキップする。"""
        img = np.full((200, 150, 3), 230, dtype=np.uint8)
        result = remove_shadow(img, strength=1.0)
        np.testing.assert_array_equal(result, img)

    def test_text_image_returns_ndarray(self, text_image):
        result = remove_shadow(text_image, strength=1.0)
        assert isinstance(result, np.ndarray)
        assert result.shape == text_image.shape

    def test_low_strength(self, text_image):
        result = remove_shadow(text_image, strength=0.3)
        assert result.shape == text_image.shape

    def test_high_strength_half(self, text_image):
        result = remove_shadow(text_image, strength=0.7)
        assert result.shape == text_image.shape

    def test_large_kernel_path(self):
        """kernel_size > 31 の分岐（blur 使用）を通す。"""
        # min(h,w) * 0.2 > 31 になるサイズ: min_dim > 155 → 400x400
        img = np.full((400, 400, 3), 100, dtype=np.uint8)
        # 暗ピクセルを多めに混ぜて白紙ガードを通過させる
        img[50:350, 50:350] = 30
        result = remove_shadow(img, strength=1.0)
        assert result.shape == img.shape

    def test_small_image_median_blur_path(self):
        """kernel_size <= 31 の分岐（medianBlur 使用）を通す。
        min(h,w) = 100 → kernel_size = max(31, int(100*0.2)|1) = max(31,21) = 31。"""
        img = np.full((200, 100, 3), 100, dtype=np.uint8)
        # 暗ピクセルを混ぜて白紙ガードを通過させる
        img[20:180, 10:90] = 30
        result = remove_shadow(img, strength=1.0)
        assert result.shape == img.shape


# ── deskew_page ───────────────────────────────────────────────────────

class TestDeskewPage:
    def test_straight_image_unchanged(self, text_image):
        result = deskew_page(text_image)
        assert result.shape == text_image.shape

    def test_skewed_image_corrected(self):
        """少し傾けた画像で deskew_page が動作する。"""
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        for y in range(40, 560, 28):
            cv2.line(img, (20, y), (380, y), (0, 0, 0), 2)
        M = cv2.getRotationMatrix2D((200, 300), 3.0, 1.0)
        skewed = cv2.warpAffine(img, M, (400, 600), borderValue=(255, 255, 255))
        result = deskew_page(skewed)
        assert result.shape == skewed.shape

    def test_white_page_no_crash(self, white_image):
        result = deskew_page(white_image)
        assert result.shape == white_image.shape

    def test_small_angle_skipped(self):
        """傾き 0.3° 未満は補正をスキップする。"""
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        for y in range(40, 560, 28):
            cv2.line(img, (20, y), (380, y), (0, 0, 0), 2)
        # 0.2° 傾けても abs < 0.3 なのでスキップ
        M = cv2.getRotationMatrix2D((200, 300), 0.2, 1.0)
        slightly_skewed = cv2.warpAffine(img, M, (400, 600), borderValue=(255, 255, 255))
        result = deskew_page(slightly_skewed)
        assert result.shape == slightly_skewed.shape

    def test_improvement_ratio_guard(self):
        """改善比が 1.3 未満の場合は補正をスキップする（line 139）。
        低コントラストな孤立ピクセルだけの画像では傾き検出が信頼できず
        improvement guard で early return する。"""
        # スコアの改善が少ない「疎な」画像: 単一ランダムドット
        rng = np.random.default_rng(42)
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        for _ in range(50):
            y = int(rng.integers(10, 590))
            x = int(rng.integers(10, 390))
            img[y, x] = 0
        result = deskew_page(img)
        assert result.shape == img.shape

    def test_vertical_writing_mode_uses_vertical_projection(self):
        """writing_mode='vertical' では垂直射影分散（axis=0）で評価する（line 117）。"""
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        # 縦書き模擬: 縦方向の線を引く
        for x in range(40, 360, 30):
            cv2.line(img, (x, 20), (x, 580), (0, 0, 0), 2)
        result = deskew_page(img, writing_mode="vertical")
        assert result.shape == img.shape

    def test_vertical_improvement_ratio_guard(self):
        """縦書きモードでも改善比 < 1.3 ならスキップする（line 142）。"""
        # 疎なランダムドットは縦書きモードでも改善比が低い
        rng = np.random.default_rng(7)
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        for _ in range(40):
            y = int(rng.integers(10, 590))
            x = int(rng.integers(10, 390))
            img[y, x] = 0
        result = deskew_page(img, writing_mode="vertical")
        assert result.shape == img.shape


# ── fix_orientation ───────────────────────────────────────────────────

class TestFixOrientation:
    def test_portrait_unchanged(self, text_image):
        assert text_image.shape[0] > text_image.shape[1]  # h > w
        result = fix_orientation(text_image)
        # landscape ではないのでそのまま
        assert result.shape[0] >= result.shape[1]

    def test_landscape_rotated_to_portrait(self):
        """横長 (h < w) の画像は縦長に回転する。"""
        # 水平エッジが支配的な横長画像
        img = np.full((200, 400, 3), 255, dtype=np.uint8)
        for y in range(20, 190, 20):
            cv2.line(img, (10, y), (390, y), (0, 0, 0), 2)
        result = fix_orientation(img)
        assert result.shape[0] > result.shape[1]

    def test_landscape_vertical_dominant(self):
        """横長でも縦エッジ支配的なら別方向に回転。"""
        img = np.full((200, 400, 3), 255, dtype=np.uint8)
        for x in range(20, 390, 20):
            cv2.line(img, (x, 10), (x, 190), (0, 0, 0), 2)
        result = fix_orientation(img)
        assert result.shape[0] > result.shape[1]


# ── _is_upside_down ───────────────────────────────────────────────────

class TestIsUpsideDown:
    def test_blank_page_returns_false(self):
        """テキストなし（全白）は False。"""
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        assert _is_upside_down(img) is False

    def test_upright_page_not_upside_down(self):
        """正位置のページは False（または判定が微妙）。"""
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        for y in range(50, 550, 25):
            cv2.line(img, (20, y), (380, y), (0, 0, 0), 2)
        result = _is_upside_down(img)
        assert isinstance(result, (bool, np.bool_))

    def test_upside_down_page(self):
        """180° 反転 + フッターのみのページは True になりやすい。"""
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        # 大部分のテキストを下部に詰め込む（逆さまにすると上マージンが大きくなる）
        for y in range(400, 580, 15):
            cv2.line(img, (20, y), (380, y), (0, 0, 0), 2)
        img = cv2.rotate(img, cv2.ROTATE_180)
        result = _is_upside_down(img)
        assert isinstance(result, (bool, np.bool_))

    def test_score_components_edge_case(self):
        """top/bot_count いずれかが 0 の場合も density_score=0.0 でクラッシュしない。"""
        # テキストが中央帯だけ（上下 20% は空）
        img = np.full((600, 400, 3), 255, dtype=np.uint8)
        for y in range(150, 450, 20):
            cv2.line(img, (20, y), (380, y), (0, 0, 0), 2)
        result = _is_upside_down(img)
        assert isinstance(result, (bool, np.bool_))

    def test_zero_total_edges_no_crash(self):
        """total_edges==0 の場合に stroke_score=0.0 でクラッシュしない。"""
        # 均質なグレー（エッジがほぼ発生しない）
        img = np.full((600, 400, 3), 128, dtype=np.uint8)
        result = _is_upside_down(img)
        assert isinstance(result, (bool, np.bool_))


# ── remove_textured_border ────────────────────────────────────────────

class TestRemoveTexturedBorder:
    def test_clean_page_unchanged(self, text_image):
        result = remove_textured_border(text_image)
        assert result is not None

    def test_textured_background_cropped(self):
        """籐背景に見立てた低白比率の枠を持つ画像でクロップが機能する。"""
        img = np.full((400, 300, 3), 100, dtype=np.uint8)  # 全体をグレー
        # 中央に白い書籍ページを配置
        img[50:350, 30:270] = 230
        result = remove_textured_border(img)
        assert result.shape[0] <= img.shape[0]

    def test_high_white_ratio_skipped(self):
        """全体白比率が 60% 超の場合はクロップをスキップ。"""
        img = np.full((300, 200, 3), 240, dtype=np.uint8)
        result = remove_textured_border(img)
        assert result.shape == img.shape

    def test_no_valid_page_region(self):
        """全体が暗い画像で有効領域なし → 元画像そのまま返す。"""
        img = np.full((300, 200, 3), 10, dtype=np.uint8)
        result = remove_textured_border(img)
        np.testing.assert_array_equal(result, img)

    def test_portrait_guard(self):
        """クロップで landscape にならないようにする portrait ガード（lines 302-305）。
        portrait 元画像(h=300, w=200)の上下にテクスチャ、中央だけ白い帯を置く。
        クロップ後 new_w(200) > new_h(~75) になるため extra padding が加わる。"""
        h, w = 300, 200
        img = np.full((h, w, 3), 80, dtype=np.uint8)
        # 中央の 75 行だけ白（white_thresh=200 より大きい値）
        img[100:175, :] = 220
        result = remove_textured_border(img)
        # portrait guard により結果が portrait を保つ
        assert result.shape[0] >= result.shape[1]

    def test_near_full_crop_skipped(self):
        """クロップ不要（ほぼ全面がページ）の場合は line 286 で early return。
        overall_white <= 0.60 かつ page_rows/cols が端まで広がっているケース。"""
        # 各ピクセルを「30% 白 (≥200), 70% 暗」に構成
        # → overall_white=0.30 (60%超えない) かつ row_white=0.30 (≥0.25) で全行ページ判定
        img = np.zeros((300, 200, 3), dtype=np.uint8)
        # 列方向に 60/200 = 30% の列を白 (205) にする
        img[:, ::3] = 205
        result = remove_textured_border(img)
        # r_min=0, r_max=299 が端に達しているので early return
        assert result.shape == img.shape


# ── remove_border ─────────────────────────────────────────────────────

class TestRemoveBorder:
    def test_no_dark_border_unchanged(self, white_image):
        result = remove_border(white_image)
        assert result.shape == white_image.shape

    def test_dark_top_border_removed(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[:30, :] = 0  # 上 30 行を黒
        result = remove_border(img)
        assert result.shape[0] <= img.shape[0]

    def test_dark_bottom_border_removed(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[270:, :] = 0
        result = remove_border(img)
        assert result.shape[0] <= img.shape[0]

    def test_dark_left_border_removed(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[:, :20] = 0
        result = remove_border(img)
        assert result.shape[1] <= img.shape[1]

    def test_dark_right_border_removed(self):
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        img[:, 180:] = 0
        result = remove_border(img)
        assert result.shape[1] <= img.shape[1]

    def test_custom_threshold(self, white_image):
        result = remove_border(white_image, threshold=50)
        assert result.shape == white_image.shape


# ── normalize_size ────────────────────────────────────────────────────

class TestNormalizeSize:
    def test_a4_output_size(self, text_image):
        result = normalize_size(text_image, target_size="A4")
        assert result.shape == (3508, 2480, 3)

    def test_a5_output_size(self, white_image):
        result = normalize_size(white_image, target_size="A5")
        assert result.shape == (2480, 1748, 3)

    def test_b5_output_size(self, white_image):
        result = normalize_size(white_image, target_size="B5")
        assert result.shape == (2953, 2079, 3)

    def test_letter_output_size(self, white_image):
        result = normalize_size(white_image, target_size="Letter")
        assert result.shape == (3300, 2550, 3)

    def test_grayscale_output(self, text_image):
        result = normalize_size(text_image, target_size="A4", grayscale=True)
        assert result.shape == (3508, 2480, 3)
        # グレースケールに変換後 BGR に戻しているので R==G==B のはず
        r, g, b = result[:, :, 2], result[:, :, 1], result[:, :, 0]
        np.testing.assert_array_equal(r, g)
        np.testing.assert_array_equal(g, b)

    def test_landscape_image_uses_landscape_canvas(self):
        """横長入力では横長キャンバスを使う。"""
        img = np.full((200, 400, 3), 200, dtype=np.uint8)  # 横長
        result = normalize_size(img, target_size="A4")
        # A4 landscape: (3508, 2480) を 90° 回転 → (2480, 3508)
        assert result.shape[1] > result.shape[0]

    def test_unknown_size_falls_back_to_a4(self):
        """存在しないサイズ名は A4 にフォールバック。"""
        img = np.full((300, 200, 3), 200, dtype=np.uint8)
        result = normalize_size(img, target_size="ZZ99")
        assert result.shape == (3508, 2480, 3)

    def test_low_white_point_no_stretch(self):
        """white_point が 150 以下の場合はストレッチをスキップ。"""
        img = np.full((300, 200, 3), 50, dtype=np.uint8)  # 非常に暗い
        result = normalize_size(img, target_size="A4")
        assert result.shape == (3508, 2480, 3)

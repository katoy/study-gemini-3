"""
page_detector.py
================
黒背景上の書籍スキャンに最適化された、境界検出・向き補正・ページ分割モジュール。
"""

from __future__ import annotations

import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 座標・透視変換
# ──────────────────────────────────────────────

def order_points(pts: np.ndarray) -> np.ndarray:
    """4点を [左上, 右上, 右下, 左下] の順に整列する。"""
    pts = pts.reshape(4, 2)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    return np.array([tl, tr, br, bl], dtype="float32")

def get_perspective_matrices(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, int]:
    """透視変換行列 M と逆変換行列 Minv を取得する。"""
    rect = order_points(pts)
    tl, tr, br, bl = rect
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    Minv = cv2.getPerspectiveTransform(dst, rect)
    return M, Minv, width, height

def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    M, _, bw, bh = get_perspective_matrices(pts)
    return cv2.warpPerspective(image, M, (bw, bh))

# ──────────────────────────────────────────────
# 境界検出 (黒背景・エッジマージン最適化)
# ──────────────────────────────────────────────

def detect_page_contour(image: np.ndarray, sensitivity: str = "medium") -> np.ndarray | None:
    """画像の端を無視し、内側の白い書籍領域を正確に抽出する。"""
    h, w = image.shape[:2]
    scale = 800.0 / max(h, w)
    small = cv2.resize(image, (int(w * scale), int(h * scale)))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    
    # 1. 【重要】外周マージンの黒塗り
    # 画像の端 5% 範囲を強制的に背景とする。
    # 「もっと画像の隅から離れた範囲で探す」ための物理的制限。
    h_s, w_s = gray.shape
    m_h, m_w = int(h_s * 0.05), int(w_s * 0.05)
    cv2.rectangle(gray, (0, 0), (w_s, m_h), 0, -1)           # Top
    cv2.rectangle(gray, (0, h_s - m_h), (w_s, h_s), 0, -1)   # Bottom
    cv2.rectangle(gray, (0, 0), (m_w, h_s), 0, -1)           # Left
    cv2.rectangle(gray, (w_s - m_w, 0), (w_s, h_s), 0, -1)   # Right
    
    # 2. 強力なぼかしと厳格な二値化
    blur = cv2.GaussianBlur(gray, (11, 11), 0)
    # 大津の手法に加え、輝度 70 未満を背景として強制カット
    _, thresh_otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, thresh_fixed = cv2.threshold(blur, 70, 255, cv2.THRESH_BINARY)
    thresh = cv2.bitwise_and(thresh_otsu, thresh_fixed)
    
    # 3. クロージング処理で穴を埋める
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    mask = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    # 4. 輪郭抽出
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    
    # 5. 中心に近く、面積が十分な輪郭を選択
    img_center = np.array([w_s / 2, h_s / 2])
    best_cnt = None
    max_score = -1
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < (h_s * w_s * 0.15):
            continue
        
        # 中心のモーメントを計算
        M = cv2.moments(cnt)
        if M['m00'] <= 1e-6:  # pragma: no cover  # 浮動小数点誤差で area > 0 でも発生し得る
            continue
        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])
        
        # スコア = 面積 / 中心からの距離 (中心に近い大きな島を優先)
        dist = np.linalg.norm(np.array([cx, cy]) - img_center)
        score = area / (1.0 + dist)
        
        if score > max_score:
            max_score = score
            best_cnt = cnt
            
    if best_cnt is None:
        return None
    
    # 6. 凸包から四隅の頂点を抽出
    hull = cv2.convexHull(best_cnt).reshape(-1, 2)
    s = hull.sum(axis=1)
    diff = np.diff(hull, axis=1)
    
    tl = hull[np.argmin(s)]
    br = hull[np.argmax(s)]
    tr = hull[np.argmin(diff)]
    bl = hull[np.argmax(diff)]
    
    pts = np.array([tl, tr, br, bl], dtype="float32")
    
    # 7. セーフティ・インセット (0.2% だけ追い込む — 大きすぎると文字見切れ)
    center = np.mean(pts, axis=0)
    for i in range(4):
        pts[i] = center + (pts[i] - center) * 0.998
    
    return (pts / scale).astype("float32")

# ──────────────────────────────────────────────
# 向き・綴じ目・順序
# ──────────────────────────────────────────────

def correct_orientation_robust(image: np.ndarray) -> tuple[np.ndarray, int | None]:
    gray: np.ndarray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    def get_max_var(img: np.ndarray) -> float:
        return float(max(np.var(np.mean(img, axis=1)), np.var(np.mean(img, axis=0))))
    scores: list[float] = []
    codes: list[int | None] = [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE]
    curr: np.ndarray = th
    for i in range(4):
        scores.append(get_max_var(curr))
        if i < 3:
            curr = cv2.rotate(curr, cv2.ROTATE_90_CLOCKWISE)
    best_idx: int = int(np.argmax(scores))
    code: int | None = codes[best_idx]
    if code is not None:
        return cv2.rotate(image, code), code
    return image, None

def find_center_seam(warped_image: np.ndarray) -> int:
    """
    見開き画像から綴じ目 (Binding/Gutter) の水平位置を推定する。

    以下の 3 つの独立した戦略を優先順位順に試行する (多層防御):

    戦略 0 (片側空白検出):
    - 左右のページ（中央 30% ずつ）のテキスト密度（輝度 < 128 の比率）を比較する。
    - 一方の密度が閾値 (0.008) 未満で、かつもう一方が 5 倍以上の密度を持つ場合、
      白紙ページとみなす。この場合、物理的な綴じ目は中央 (50%) にあると仮定する。

    戦略 1 (明るいギャップ検出):
    - 中央付近 (40-60%) の列ごとのテキスト密度を走査し、密度がほぼゼロ (0.002 未満) の
      垂直な「隙間」を探す。
    - 製本時の白いマージンやスパインが露出しているケースに有効。
    - 複数の候補がある場合、画像中央 (50%) に最も近いものを選択する。

    戦略 2 (輝度最小値/影検出):
    - 垂直方向に強いブラーをかけ、行方向の平均輝度プロファイルを生成する。
    - 綴じ目付近には物理的な「谷」による影（暗部）が生じるため、輝度の最小点を探索する。
    - 中心引力ペナルティ (Gaussian-like penalty) を付与することで、
      ページ端の影や大きな図版による暗部への誤吸着を防ぎ、中央付近の最小値を優先する。

    Returns:
        綴じ目の x 座標 (ピクセル)
    """
    h, w = warped_image.shape[:2]
    if w < 100 or h < 50:  # 極端に小さい画像はセンターを返す
        logger.debug("find_center_seam: image too small (%dx%d), using center", w, h)
        return w // 2
    gray = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY)
    # 綴じ目の探索範囲: 40%〜60% に限定（端への誤検出を防ぐ）
    SEAM_MIN = int(w * 0.40)
    SEAM_MAX = int(w * 0.60)
    center = w // 2
    s, e = SEAM_MIN, SEAM_MAX

    # ── 戦略0: 片側空白 (一方のページが白紙) ─────────────────
    text = (gray < 128).astype(np.float32)
    col_density = np.mean(text, axis=0)

    # センター付近を避けた外側領域で密度計測。
    far_left_density  = float(np.mean(col_density[int(w * 0.05) : int(w * 0.35)]))
    far_right_density = float(np.mean(col_density[int(w * 0.65) : int(w * 0.95)]))
    logger.debug(
        "find_center_seam: far_left=%.4f far_right=%.4f",
        far_left_density, far_right_density,
    )

    blank_thresh = 0.008
    # テキスト密度が薄いページ（目次・扉等）にも対応するため、コンテンツ側の最小閾値を低めに設定
    content_thresh = 0.003

    # 右ページが空白で左ページにコンテンツがある場合
    if far_right_density < blank_thresh and far_left_density > far_right_density * 5 and far_left_density > content_thresh:
        # 片側空白の場合は物理的な綴じ目は見開き中央（50%）にあるので center を返す
        logger.debug("find_center_seam: blank-right x=%d (%.1f%%)", center, center / w * 100)
        return center

    # 左ページが空白で右ページにコンテンツがある場合
    if far_left_density < blank_thresh and far_right_density > far_left_density * 5 and far_right_density > content_thresh:
        # 片側空白の場合は物理的な綴じ目は見開き中央（50%）にあるので center を返す
        logger.debug("find_center_seam: blank-left x=%d (%.1f%%)", center, center / w * 100)
        return center

    # ── 戦略1: 明るいギャップ (ゼロ密度ブロック) ──────────────
    # 40-60% の範囲内で候補を全収集し、50% に最も近いものを選ぶ
    min_gap = int(w * 0.02)
    max_gap = int(w * 0.08)

    zero_mask = col_density < 0.002
    run_start, run_len = 0, 0
    gap_candidates = []
    for i in range(s, e):
        if zero_mask[i]:
            if run_len == 0:
                run_start = i
            run_len += 1
        else:
            if min_gap <= run_len <= max_gap:
                gap_candidates.append(run_start + run_len // 2)
            run_len = 0
    if min_gap <= run_len <= max_gap:
        gap_candidates.append(run_start + run_len // 2)

    if gap_candidates:
        cx = min(gap_candidates, key=lambda x: abs(x - center))
        logger.debug("find_center_seam: bright gap x=%d (%.1f%%)", cx, cx / w * 100)
        return cx

    # ── 戦略2: 輝度最小値 (暗い製本影) ───────────────────────
    # 40-60% の範囲で輝度スコアを計算し、50% に最も近い極小点を選ぶ
    v_blur = cv2.blur(gray, (1, h // 4))
    brightness_profile = np.mean(v_blur, axis=0).astype(np.float32)
    sigma = max(20, w // 80)
    k = sigma * 6 + 1
    smoothed_b = cv2.GaussianBlur(brightness_profile.reshape(1, -1), (k, 1), sigma)[0]
    x = np.arange(w)
    center_penalty = ((x - w / 2) / (w / 4)) ** 2 * 1000
    score = smoothed_b + center_penalty
    seam_x = SEAM_MIN + int(np.argmin(score[SEAM_MIN:SEAM_MAX]))
    logger.debug("find_center_seam: brightness-min x=%d (%.1f%%)", seam_x, seam_x / w * 100)
    return seam_x

def detect_writing_direction(image: np.ndarray) -> str:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8)
    line_len = max(10, min(gray.shape) // 50)
    h_lines = cv2.morphologyEx(th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (line_len, 1)))
    v_lines = cv2.morphologyEx(th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, line_len)))
    h_score, v_score = np.count_nonzero(h_lines), np.count_nonzero(v_lines)
    if h_score > v_score * 1.2:
        return "left_first"
    if v_score > h_score * 1.2:
        return "right_first"
    return "right_first" if np.count_nonzero(th[:, int(th.shape[1]*0.6):]) > np.count_nonzero(th[:, :int(th.shape[1]*0.4)]) * 1.2 else "left_first"

def split_spread(image: np.ndarray, order: str = "left_first", seam_x: int | None = None) -> list[np.ndarray]:
    if seam_x is None:
        seam_x = find_center_seam(image)
    logger.debug("split_spread: seam_x=%d (%.1f%%) order=%s", seam_x, seam_x / image.shape[1] * 100, order)
    left_page, r = image[:, :seam_x].copy(), image[:, seam_x:].copy()
    m = 2  # seam 際の製本影を 2px だけ白塗り
    left_page[:, -m:] = 255
    r[:, :m] = 255
    pages = [left_page, r]
    if order == "right_first":
        pages.reverse()
    return pages

def trim_page_border(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    nb = (gray < 50)
    ir, ic = np.mean(nb, axis=1) > 0.80, np.mean(nb, axis=0) > 0.80
    t, b, left_col, r = 0, h-1, 0, w-1
    while t < h//4 and ir[t]:
        t += 1
    while b > 3*h//4 and ir[b]:
        b -= 1
    while left_col < w//4 and ic[left_col]:
        left_col += 1
    while r > 3*w//4 and ic[r]:
        r -= 1
    return image[t:b+1, left_col:r+1]


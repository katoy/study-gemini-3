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
    """4点を [左上, 右上, 右下, 左下] の順に整列する。

    アルゴリズム:
        x+y が最小の点 = 左上、最大 = 右下
        y-x が最小の点 = 右上（大x・小y）、最大 = 左下（小x・大y）
    同じ点が複数コーナーに割り当てられた場合は重心からの角度で再整列する。
    """
    pts = pts.reshape(4, 2).astype("float32")
    s    = pts.sum(axis=1)           # x + y
    diff = pts[:, 1] - pts[:, 0]    # y - x

    idx_tl = np.argmin(s)
    idx_br = np.argmax(s)
    idx_tr = np.argmin(diff)
    idx_bl = np.argmax(diff)

    # 4点が重複なく選ばれているか確認（縮退四角形などへの防御）
    if len({idx_tl, idx_br, idx_tr, idx_bl}) == 4:
        return np.array([pts[idx_tl], pts[idx_tr], pts[idx_br], pts[idx_bl]], dtype="float32")

    # 縮退ケース: 重心からの角度でソートして時計回りに整列
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    order  = np.argsort(angles)   # 反時計回り (-π → π)
    pts_ccw = pts[order]
    # sum 最小点を左上に回転させる
    s_ccw   = pts_ccw.sum(axis=1)
    start   = int(np.argmin(s_ccw))
    pts_ccw = np.roll(pts_ccw, -start, axis=0)
    # 反時計回り [tl, bl, br, tr] → [tl, tr, br, bl] に変換
    tl, bl, br, tr = pts_ccw
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
        # m00 は contourArea と同値であり、面積フィルタを通過した輪郭では通常ゼロにならない。
        # ただし浮動小数点実装の差異で稀に発生し得るため、ゼロ除算を防ぐ。
        M = cv2.moments(cnt)
        if M['m00'] <= 1e-6:  # pragma: no cover
            logger.warning("cv2.moments で m00 がゼロになりました (area=%.1f)。輪郭をスキップします。", area)
            continue
        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])
        if not (0 <= cx < w_s and 0 <= cy < h_s):  # pragma: no cover
            continue
        
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

def _seam_strategy_blank_page(col_density: np.ndarray, w: int, center: int) -> int | None:
    """戦略0: 片側空白（一方のページが白紙）。

    左右それぞれの外側 30% 領域のテキスト密度を比較し、
    一方が極端に疎な場合は物理的な綴じ目を中央 (50%) と仮定して返す。
    該当しない場合は None を返す。
    """
    far_left  = float(np.mean(col_density[int(w * 0.05) : int(w * 0.35)]))
    far_right = float(np.mean(col_density[int(w * 0.65) : int(w * 0.95)]))
    logger.debug("find_center_seam: far_left=%.4f far_right=%.4f", far_left, far_right)

    blank_thresh   = 0.008
    content_thresh = 0.003  # 目次・扉等の薄いページにも対応

    if far_right < blank_thresh and far_left > far_right * 5 and far_left > content_thresh:
        logger.debug("find_center_seam: blank-right x=%d (%.1f%%)", center, center / w * 100)
        return center
    if far_left < blank_thresh and far_right > far_left * 5 and far_right > content_thresh:
        logger.debug("find_center_seam: blank-left x=%d (%.1f%%)", center, center / w * 100)
        return center
    return None


def _seam_strategy_bright_gap(col_density: np.ndarray, w: int, center: int,
                               seam_min: int, seam_max: int) -> int | None:
    """戦略1: 明るいギャップ（ゼロ密度ブロック）。

    中央付近 (seam_min〜seam_max) で密度がほぼゼロの連続領域を探し、
    中央に最も近い候補を返す。見つからない場合は None を返す。
    """
    min_gap = int(w * 0.02)
    max_gap = int(w * 0.08)
    zero_mask = col_density < 0.002

    run_start, run_len = 0, 0
    candidates: list[int] = []
    for i in range(seam_min, seam_max):
        if zero_mask[i]:
            if run_len == 0:
                run_start = i
            run_len += 1
        else:
            if min_gap <= run_len <= max_gap:
                candidates.append(run_start + run_len // 2)
            run_len = 0
    if min_gap <= run_len <= max_gap:
        candidates.append(run_start + run_len // 2)

    if candidates:
        cx = min(candidates, key=lambda x: abs(x - center))
        logger.debug("find_center_seam: bright gap x=%d (%.1f%%)", cx, cx / w * 100)
        return cx
    return None


def _seam_strategy_brightness_min(gray: np.ndarray, w: int, h: int,
                                   seam_min: int, seam_max: int) -> int:
    """戦略2: 輝度最小値（暗い製本影）。

    垂直ブラー後の輝度プロファイルから中心引力ペナルティ付きの最小点を返す。
    常に値を返す（最後の砦）。
    """
    v_blur = cv2.blur(gray, (1, h // 4))
    profile = np.mean(v_blur, axis=0).astype(np.float32)
    sigma = max(20, w // 80)
    k = sigma * 6 + 1
    smoothed = cv2.GaussianBlur(profile.reshape(1, -1), (k, 1), sigma)[0]
    x = np.arange(w)
    penalty = ((x - w / 2) / (w / 4)) ** 2 * 1000
    score = smoothed + penalty
    seam_x = seam_min + int(np.argmin(score[seam_min:seam_max]))
    logger.debug("find_center_seam: brightness-min x=%d (%.1f%%)", seam_x, seam_x / w * 100)
    return seam_x


def find_center_seam(warped_image: np.ndarray) -> int:
    """
    見開き画像から綴じ目 (Binding/Gutter) の水平位置を推定する。

    3 つの独立した戦略を優先順位順に試行する (多層防御):
      戦略0: 片側空白検出 (_seam_strategy_blank_page)
      戦略1: 明るいギャップ検出 (_seam_strategy_bright_gap)
      戦略2: 輝度最小値/影検出 (_seam_strategy_brightness_min)

    Returns:
        綴じ目の x 座標 (ピクセル)
    """
    h, w = warped_image.shape[:2]
    if w < 100 or h < 50:
        logger.debug("find_center_seam: image too small (%dx%d), using center", w, h)
        return w // 2

    gray = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY)
    seam_min = int(w * 0.40)
    seam_max = int(w * 0.60)
    center   = w // 2

    col_density = np.mean((gray < 128).astype(np.float32), axis=0)

    result = _seam_strategy_blank_page(col_density, w, center)
    if result is not None:
        return result

    result = _seam_strategy_bright_gap(col_density, w, center, seam_min, seam_max)
    if result is not None:
        return result

    return _seam_strategy_brightness_min(gray, w, h, seam_min, seam_max)

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
    right_score = np.count_nonzero(th[:, int(th.shape[1] * 0.6):])
    left_score  = np.count_nonzero(th[:, :int(th.shape[1] * 0.4)])
    return "right_first" if right_score > left_score * 1.2 else "left_first"

def split_spread(image: np.ndarray, order: str = "left_first", seam_x: int | None = None) -> list[np.ndarray]:
    if seam_x is None:
        seam_x = find_center_seam(image)
    logger.debug("split_spread: seam_x=%d (%.1f%%) order=%s", seam_x, seam_x / image.shape[1] * 100, order)
    left_page, r = image[:, :seam_x].copy(), image[:, seam_x:].copy()
    m = max(2, int(image.shape[1] * 0.0005))  # 画像幅の 0.05%（最低 2px）
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


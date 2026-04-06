"""
page_detector.py
================
ページ境界検出、透視変換、および見開き分割を行うモジュール。
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
    """
    4点を [左上, 右上, 右下, 左下] の順に整列する。

    従来の sum/diff 法は軸平行に近い矩形で誤割り当てが発生するため、
    y ソート後に上下の組をそれぞれ x でソートする方式を採用する。
    """
    # y でソート → 上2点 / 下2点
    sorted_by_y = pts[np.argsort(pts[:, 1])]
    top = sorted_by_y[:2]
    bot = sorted_by_y[2:]

    # 上2点: x が小さい方が TL, 大きい方が TR
    tl = top[np.argmin(top[:, 0])]
    tr = top[np.argmax(top[:, 0])]

    # 下2点: x が小さい方が BL, 大きい方が BR
    bl = bot[np.argmin(bot[:, 0])]
    br = bot[np.argmax(bot[:, 0])]

    return np.array([tl, tr, br, bl], dtype="float32")

def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """
    4点座標に基づき透視変換を実行する。
    """
    rect = order_points(pts)
    tl, tr, br, bl = rect

    # 元のサイズを計算
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))

    dst = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1]
    ], dtype="float32")

    # 変換行列の作成と適用
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (width, height))

    return warped

# ──────────────────────────────────────────────
# ページ輪郭検出 (内部実装)
# ──────────────────────────────────────────────

def _contour_to_quad(hull: np.ndarray, scale: float) -> np.ndarray | None:
    """
    輪郭の凸包から4点の四角形を推定する。
    近似精度を段階的に緩めて4点を探し、見つからなければ最小外接矩形を使う。
    """
    peri = cv2.arcLength(hull, True)
    for eps in [0.01, 0.02, 0.04, 0.08]:
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            return (approx.reshape(4, 2) / scale).astype("float32")
    rect = cv2.minAreaRect(hull)
    box = cv2.boxPoints(rect)
    return (box / scale).astype("float32")


def _best_rect_contour(contours: list, img_area: int) -> np.ndarray | None:
    """
    輪郭リストから「面積が大きく矩形に近い」最良輪郭を返す。
    img_area の 10% 未満の輪郭は除外。
    """
    best_cnt, max_score = None, -1
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.1:
            continue
        rect = cv2.minAreaRect(cnt)
        rect_area = rect[1][0] * rect[1][1]
        if rect_area == 0:
            continue
        score = area * (area / rect_area)  # 面積 × 矩形度
        if score > max_score:
            max_score = score
            best_cnt = cnt
    return best_cnt


def _detect_by_book_region(small: np.ndarray, scale: float) -> np.ndarray | None:
    """
    背景認識 → 書籍領域認識 → 綴じ目認識 → ページ枠決定 の3段階アプローチ。

    Step 1 — 背景認識（局所テクスチャ + 輝度マスク）:
      局所標準偏差で各ピクセルの「テクスチャ量」を計算する。
      籐・机などのテクスチャ背景は局所標準偏差が高く (≥ 38)、
      書籍ページの白領域（文字なし）は低い。
      「低テクスチャ OR 高輝度（≥ 200）」の組み合わせで書籍候補マスクを作る。

    Step 2 — 書籍領域認識（モルフォロジー + コンター検出）:
      大カーネル CLOSE でページ白領域を連結させ、輪郭検出で最大矩形領域を得る。
      バウンディングボックスではなくコンターを使うことで、
      全面に広がる領域でも正確な境界が得られる。

    Step 3 — 中央綴じ目認識:
      書籍領域内の中央 1/3 ROI で列方向平均輝度の最小値を綴じ目候補としてログ出力。

    Step 4 — ページ枠決定:
      輪郭の凸包を4点四角形として返す（呼び出し側が分割する）。
    """
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray_u8 = gray.astype(np.uint8)
    h, w = gray_u8.shape

    # ── Step 1: 局所テクスチャ計算 + 書籍候補マスク ──
    # E[X^2] - E[X]^2 = Var[X] → sqrt = std
    K = max(9, w // 30) | 1
    local_mean = cv2.blur(gray, (K, K))
    local_sq   = cv2.blur(gray ** 2, (K, K))
    local_std  = np.sqrt(np.maximum(local_sq - local_mean ** 2, 0.0))

    # 低テクスチャ（書籍の白地）: std < 38
    # 高輝度（白ページ確実）: gray >= 200
    # どちらかを満たせば書籍ページ候補
    _TEX_THRESH = 38
    low_tex  = (local_std < _TEX_THRESH).astype(np.uint8) * 255
    bright   = (gray_u8 >= 200).astype(np.uint8) * 255
    page_mask = cv2.bitwise_or(low_tex, bright)

    # ── Step 2: モルフォロジーで書籍領域を塊として連結 ──
    kernel_size = max(w // 18, 5)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(page_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    opened = cv2.morphologyEx(closed,    cv2.MORPH_OPEN,  kernel, iterations=1)

    # 外周の背景テクスチャがページ領域に混入しないよう、エロードで境界を縮小
    # 画像幅の 2% 相当だけ内側に収める
    erode_k = max(w // 25, 5)
    erode_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (erode_k, erode_k))
    eroded = cv2.erode(opened, erode_kernel, iterations=2)

    # 輪郭検出で最大矩形領域を取得
    contours, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    img_area = h * w
    large = [c for c in contours if cv2.contourArea(c) > img_area * 0.15]
    if not large:
        return None
    best = max(large, key=cv2.contourArea)
    pts = _contour_to_quad(cv2.convexHull(best), scale)
    if pts is None:
        return None

    # ── Step 3: 中央綴じ目をログに記録 ──
    ordered = pts.astype(int)
    bx = int(ordered[:, 0].min() * scale)
    by = int(ordered[:, 1].min() * scale)
    bw = int((ordered[:, 0].max() - ordered[:, 0].min()) * scale)
    bh = int((ordered[:, 1].max() - ordered[:, 1].min()) * scale)
    roi_x0 = bx + bw // 3
    roi_x1 = bx + 2 * bw // 3
    if roi_x1 > roi_x0 and by + bh <= h and bx + bw <= w:
        roi_g = gray_u8[by:by + bh, roi_x0:roi_x1]
        if roi_g.size > 0:
            col_mean = roi_g.mean(axis=0)
            seam_x = roi_x0 + int(np.argmin(col_mean))
            logger.debug(
                "_detect_by_book_region: 書籍領域=(%d,%d,%d,%d), 中央綴じ目候補x=%d (%.1f%%)",
                bx, by, bw, bh, seam_x, seam_x / w * 100,
            )

    return pts


def _detect_by_edge_and_profile(small: np.ndarray, scale: float) -> np.ndarray | None:
    """
    白比率プロファイル + Canny エッジ密度急落で書籍の物理的境界を精密検出する。

    Step 1 — 白比率プロファイルで書籍内部の確実領域を特定:
      行/列ごとの白ピクセル比率 (輝度≥190) を計算し、
      内側から外側へスキャンして白比率が閾値を下回る位置を粗い境界とする。

    Step 2 — Canny エッジ密度の急落で物理境界を精密化:
      籐テクスチャ領域: Canny エッジ密度が高い
      書籍ページ領域: Canny エッジ密度が低い
      → 「エッジ密度が高い外部領域から低い内部領域への急落位置」= 物理的書籍境界

    Step 3 — 両シグナルを組み合わせて最終境界を決定:
      白比率スキャン境界の近傍 (±10行/列) でエッジ密度急落が最大の位置を採用。
    """
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # ── Step 1: 白比率プロファイルで粗い境界を計算 ──
    row_white = np.mean(gray >= 190, axis=1)   # (h,)
    col_white = np.mean(gray >= 190, axis=0)   # (w,)

    _INNER_THRESH = 0.40  # 確実にページ内部と判定する閾値
    _OUTER_THRESH = 0.35  # 外側スキャン時にページ境界と判定する閾値

    inner_rows = np.where(row_white >= _INNER_THRESH)[0]
    inner_cols = np.where(col_white >= _INNER_THRESH)[0]

    if len(inner_rows) < h * 0.15 or len(inner_cols) < w * 0.15:
        logger.debug("_detect_by_edge_and_profile: 内側領域不足")
        return None

    r_top_inner  = int(inner_rows.min())
    r_bot_inner  = int(inner_rows.max())
    c_left_inner = int(inner_cols.min())
    c_right_inner= int(inner_cols.max())

    def _white_scan_boundary(profile, inner_pos, go_low):
        """
        内側確定位置から外側へスキャンし、白比率が OUTER_THRESH を下回る直前を境界とする。
        go_low=True: 上/左境界（内側→0方向へスキャン）
        go_low=False: 下/右境界（内側→末尾方向へスキャン）
        """
        if go_low:
            boundary = inner_pos
            for i in range(inner_pos, -1, -1):
                if profile[i] < _OUTER_THRESH:
                    boundary = i + 1
                    break
            return max(0, boundary)
        else:
            boundary = inner_pos
            n = len(profile)
            for i in range(inner_pos, n):
                if profile[i] < _OUTER_THRESH:
                    boundary = i
                    break
            return min(n - 1, boundary)

    r_top_white  = _white_scan_boundary(row_white, r_top_inner,  go_low=True)
    r_bot_white  = _white_scan_boundary(row_white, r_bot_inner,  go_low=False)
    c_left_white = _white_scan_boundary(col_white, c_left_inner, go_low=True)
    c_right_white= _white_scan_boundary(col_white, c_right_inner,go_low=False)

    # ── Step 2: Canny エッジ密度急落で物理境界を精密化 ──
    blur  = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 30, 100)

    row_edge = edges.sum(axis=1).astype(np.float32)
    col_edge = edges.sum(axis=0).astype(np.float32)
    row_edge = cv2.GaussianBlur(row_edge.reshape(-1, 1), (1, 11), 0).flatten()
    col_edge = cv2.GaussianBlur(col_edge.reshape(1, -1), (11, 1), 0).flatten()

    # エッジ密度の負の勾配（急落 = 外→内の遷移）
    row_drop = -np.diff(row_edge, prepend=row_edge[0])  # 正値 = 急落
    col_drop = -np.diff(col_edge, prepend=col_edge[0])

    _REFINE = 10  # 白比率境界から±10行/列を精密化探索範囲とする

    def _refine_by_edge_drop(drop_profile, white_boundary, go_low, size):
        """
        白比率境界の近傍でエッジ密度急落が最大の位置を返す。
        急落が微弱（ページ内部の変動と区別がつかない）場合は白比率境界をそのまま返す。
        """
        if go_low:
            lo = max(0, white_boundary - _REFINE)
            hi = min(size - 1, white_boundary + _REFINE)
        else:
            lo = max(0, white_boundary - _REFINE)
            hi = min(size - 1, white_boundary + _REFINE)
        if lo >= hi:
            return white_boundary
        seg = drop_profile[lo:hi + 1]
        peak = float(seg.max())
        # 急落が微弱なら白比率境界を採用
        baseline = float(np.abs(drop_profile).mean())
        if peak < baseline * 1.5:
            return white_boundary
        return lo + int(np.argmax(seg))

    r_top   = _refine_by_edge_drop(row_drop, r_top_white,   go_low=True,  size=h)
    r_bot   = _refine_by_edge_drop(row_drop, r_bot_white,   go_low=False, size=h)
    c_left  = _refine_by_edge_drop(col_drop, c_left_white,  go_low=True,  size=w)
    c_right = _refine_by_edge_drop(col_drop, c_right_white, go_low=False, size=w)

    # ── Step 3: 左右半分ごとに独立して top/bot を求め台形クワッドを返す ──
    # 書籍が傾いている場合、上辺・下辺は水平ではなくなる。
    # 左半分と右半分の列範囲でそれぞれ白比率プロファイルを計算し、
    # 独立した top/bot 境界を求めることで台形輪郭を近似する。

    # 端の代表バンド: 左右それぞれ端の10%列を使う（境界精度向上）
    edge_band = max(w // 10, 5)

    def _row_profile_band(col_lo, col_hi):
        return np.mean(gray[:, col_lo:col_hi] >= 190, axis=1)

    def _scan_boundary_top(rw):
        inner = np.where(rw >= _INNER_THRESH)[0]
        if len(inner) == 0:
            return r_top
        ip = int(inner.min())
        b = ip
        for i in range(ip, -1, -1):
            if rw[i] < _OUTER_THRESH:
                b = i + 1
                break
        return max(0, b)

    def _scan_boundary_bot(rw):
        """
        下辺境界を「籐側から内側へ」高い閾値でスキャンして求める。
        最後尾から走査し、白比率が _INNER_THRESH を超える行 = ページ底辺とする。
        これにより遷移帯（白比率が中間）を確実に除外する。
        """
        for i in range(h - 1, -1, -1):
            if rw[i] >= _INNER_THRESH:
                return i
        return r_bot

    # 左端バンドと右端バンドのみで評価（端のみが書籍境界に近い）
    rw_left  = _row_profile_band(0,            edge_band)
    rw_right = _row_profile_band(w - edge_band, w)

    r_bl_raw = _scan_boundary_bot(rw_left)
    r_br_raw = _scan_boundary_bot(rw_right)

    # 上辺は左右差が小さいため全体プロファイルから求めた r_top_white を使用
    r_tl = _refine_by_edge_drop(row_drop, r_top_white, go_low=True,  size=h)
    r_tr = r_tl  # 上辺は水平とみなす

    # 下辺は左右で独立に求め、エッジ急落で精密化
    r_bl = _refine_by_edge_drop(row_drop, r_bl_raw, go_low=False, size=h)
    r_br = _refine_by_edge_drop(row_drop, r_br_raw, go_low=False, size=h)

    # 左右の col 境界は全行プロファイルから（傾きが小さいため単一値で十分）
    c_left_final  = c_left
    c_right_final = c_right

    logger.debug(
        "_detect_by_edge_and_profile: TL=(%d,%d) TR=(%d,%d) BR=(%d,%d) BL=(%d,%d)",
        c_left_final, r_tl, c_right_final, r_tr,
        c_right_final, r_br, c_left_final, r_bl,
    )

    # 面積チェック（台形の概算面積）
    avg_h = ((r_bl + r_br) // 2) - ((r_tl + r_tr) // 2)
    avg_w = c_right_final - c_left_final
    if avg_h * avg_w < h * w * 0.15:
        return None

    pts = np.array([
        [c_left_final  / scale, r_tl / scale],   # TL
        [c_right_final / scale, r_tr / scale],   # TR
        [c_right_final / scale, r_br / scale],   # BR
        [c_left_final  / scale, r_bl / scale],   # BL
    ], dtype="float32")
    return pts


def _detect_by_adaptive_thresh(small: np.ndarray, scale: float) -> np.ndarray | None:
    """適応的二値化による輪郭検出（暗い背景向け）。"""
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    img_area = small.shape[0] * small.shape[1]
    best = _best_rect_contour(contours, img_area)
    if best is None:
        return None
    return _contour_to_quad(cv2.convexHull(best), scale)


def _detect_by_brightness(small: np.ndarray, scale: float) -> np.ndarray | None:
    """
    輝度ベースのページ検出（明るい背景・均一照明向けフォールバック）。
    大津法でページ（明るい）と背景を分離し、最大輝度領域を4点で近似する。
    """
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 小さな穴を埋める
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    img_area = small.shape[0] * small.shape[1]
    # 明るい面積が大きい輪郭を探す (閾値を緩めに 0.2)
    large = [c for c in contours if cv2.contourArea(c) > img_area * 0.2]
    if not large:
        return None
    best = max(large, key=cv2.contourArea)
    return _contour_to_quad(cv2.convexHull(best), scale)


def _detect_by_canny(small: np.ndarray, scale: float) -> np.ndarray | None:
    """
    Canny エッジ + 輪郭検出によるページ検出（コントラストが低い場合向け）。
    """
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 30, 100)

    # エッジを太らせて輪郭を繋げる
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    img_area = small.shape[0] * small.shape[1]
    best = _best_rect_contour(contours, img_area)
    if best is None:
        return None
    return _contour_to_quad(cv2.convexHull(best), scale)


def _detect_by_white_profile(small: np.ndarray, scale: float) -> np.ndarray | None:
    """
    行・列の白ピクセル比率プロファイルからページ境界を推定する。

    書籍ページは白い（輝度≥190）ピクセルが多い。背景（机・テクスチャ）は
    暗いかカラーで白比率が低い。この差を使って外周の非ページ部分を除去し、
    ページの矩形境界を推定する。

    既存3手法が失敗する典型ケース:
      - 分割後ページの片端に暗い背景が残っている（下端 white_ratio 1.6% 等）
      - ページ自体が画像面積の99%以上を占めて _is_valid_quad に棄却されるケース
    """
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 各行・列の白ピクセル比率
    row_white = np.mean(gray >= 190, axis=1)   # shape: (h,)
    col_white = np.mean(gray >= 190, axis=0)   # shape: (w,)

    # ページ行・列の候補 (25%以上が白)
    _WHITE_THRESH = 0.25
    page_rows = np.where(row_white >= _WHITE_THRESH)[0]
    page_cols = np.where(col_white >= _WHITE_THRESH)[0]

    if len(page_rows) < h * 0.2 or len(page_cols) < w * 0.2:
        return None

    r_min, r_max = int(page_rows.min()), int(page_rows.max())
    c_min, c_max = int(page_cols.min()), int(page_cols.max())

    # ページ領域が画像全体の 15% 以上を占める場合のみ有効
    page_area = (r_max - r_min) * (c_max - c_min)
    if page_area < h * w * 0.15:
        return None

    pts = np.array([
        [c_min / scale, r_min / scale],
        [c_max / scale, r_min / scale],
        [c_max / scale, r_max / scale],
        [c_min / scale, r_max / scale],
    ], dtype="float32")
    return pts


def _detect_by_saturation(small: np.ndarray, scale: float) -> np.ndarray | None:
    """
    HSV 彩度ベースのページ検出。

    書籍ページ（白/グレー）は低彩度。机・籐・カバーなどの背景は
    彩度が高い傾向がある。低彩度かつ高輝度な領域をページとして検出する。
    """
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = cv2.split(hsv)
    h, w = s_ch.shape

    # 低彩度 (S < 50) かつ 高輝度 (V > 140) → ページ候補
    page_mask = ((s_ch < 50) & (v_ch > 140)).astype(np.uint8) * 255

    # ノイズ除去・穴埋め
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, w // 30), max(3, h // 30)))
    cleaned = cv2.morphologyEx(page_mask, cv2.MORPH_CLOSE, kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    img_area = h * w
    large = [c for c in contours if cv2.contourArea(c) > img_area * 0.15]
    if not large:
        return None
    best = max(large, key=cv2.contourArea)
    return _contour_to_quad(cv2.convexHull(best), scale)


def _is_valid_quad(pts: np.ndarray | None, image_shape: tuple) -> bool:
    """
    検出された四角形を 2 段階で検証する。
      1. 面積比: 画像の 25〜99.5% を占めるか
      2. 縦横比整合性: portrait 画像に landscape クォッドが来た場合（またはその逆）は棄却
         (軸平行に近い矩形で order_points が誤割り当てした場合の安全弁)
    """
    if pts is None:
        return False
    img_h, img_w = image_shape[:2]
    img_area = img_h * img_w
    ordered = order_points(pts)
    # Shoelace formula
    x = ordered[:, 0]
    y = ordered[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    ratio = area / img_area
    if not (0.25 < ratio < 0.998):
        return False

    # クォッドの辺長から縦横比を推定
    tl, tr, br, bl = ordered
    quad_w = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    quad_h = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2

    # portrait 画像なのに landscape クォッド → 棄却
    if img_h > img_w * 1.1 and quad_w > quad_h * 1.2:
        logger.debug("_is_valid_quad: portrait image but landscape quad → rejected")
        return False
    # landscape 画像なのに portrait クォッド → 棄却
    if img_w > img_h * 1.1 and quad_h > quad_w * 1.2:
        logger.debug("_is_valid_quad: landscape image but portrait quad → rejected")
        return False

    return True


def _detect_page_area(image: np.ndarray) -> np.ndarray | None:
    """
    画像からページと思われる最大の矩形領域を検出する。

    5段階の検出戦略を順番に試し、最初に有効な四角形を返す:
      1. 適応的二値化（暗い背景に強い）
      2. 輝度ベース (大津法)（明るい均一背景に強い）
      3. Canny エッジ（低コントラストに強い）
      4. 白ピクセルプロファイル（片端が暗い分割後ページに強い）
      5. HSV彩度（テクスチャ背景とページを色差で分離）
    """
    h, w = image.shape[:2]
    scale = 600 / h
    small = cv2.resize(image, (int(w * scale), 600))

    for method, detector in [
        ("edge_and_profile", _detect_by_edge_and_profile),
        ("white_profile",    _detect_by_white_profile),
        ("book_region",      _detect_by_book_region),
        ("adaptive_thresh",  _detect_by_adaptive_thresh),
        ("brightness",       _detect_by_brightness),
        ("canny",            _detect_by_canny),
        ("saturation",       _detect_by_saturation),
    ]:
        pts = detector(small, scale)
        if _is_valid_quad(pts, image.shape):
            logger.debug("ページ検出成功: method=%s", method)
            return pts
        logger.debug("ページ検出失敗: method=%s, pts=%s", method, pts)

    logger.warning("全検出手法が失敗しました。フォールバックなし。")
    return None

def detect_page_contour(image: np.ndarray, sensitivity: str = "medium") -> np.ndarray | None:
    """
    書籍ページの輪郭を検出し、四隅の座標を返す。
    """
    # 以前の _detect_by_edges / _detect_by_brightness を統合した新エンジンを使用
    return _detect_page_area(image)


def detect_page_contour_ai(image: np.ndarray) -> np.ndarray | None:
    """
    AI (Segmentation モデル) を用いて書籍ページの境界を検出する。
    将来のアップデートで U-Net / DeepLabV3+ 等のモデル推論を実装予定。
    現在は既存の検出器を最高感度で呼び出すフォールバックとして機能。
    """
    logger.warning("AI ページ境界検出は現在準備中です。既存の検出器(high)にフォールバックします。")
    return detect_page_contour(image, sensitivity="high")

# ──────────────────────────────────────────────
# ページ外縁トリミング
# ──────────────────────────────────────────────

def trim_page_border(image: np.ndarray) -> np.ndarray:
    """
    透視変換後の画像から外縁の不要領域を2段階で除去する。

    Step 1 — 黒縁除去:
      外周から「ほぼ全ピクセル (>95%) が真っ黒 (<15)」な行/列を除去する。
      透視変換後に生じる黒い三角形領域が対象。

    Step 2 — テクスチャ背景除去:
      外周から「白ピクセル比率 (輝度 >= 200) が 25% 未満」な行/列を除去する。
      籐・机などの撮影背景テクスチャはページより暗く白比率が低いため
      書籍ページ本体に到達するまで外縁を削る。
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # ── Step 1: 黒縁除去 ──
    nearly_black  = (gray < 15)
    is_border_row = np.mean(nearly_black, axis=1) > 0.95
    is_border_col = np.mean(nearly_black, axis=0) > 0.95

    top = 0
    while top < h // 4 and is_border_row[top]:
        top += 1
    bottom = h - 1
    while bottom > 3 * h // 4 and is_border_row[bottom]:
        bottom -= 1
    left = 0
    while left < w // 4 and is_border_col[left]:
        left += 1
    right = w - 1
    while right > 3 * w // 4 and is_border_col[right]:
        right -= 1

    trimmed = image[top:bottom + 1, left:right + 1]
    if top or bottom < h - 1 or left or right < w - 1:
        logger.debug("trim_page_border step1: (%d,%d) -> (%d,%d)",
                     w, h, trimmed.shape[1], trimmed.shape[0])

    # ── Step 2: テクスチャ背景除去 ──
    # 白比率 (輝度 >= 200) が 25% 未満の外周行/列を除去する。
    # 籐・机などの背景テクスチャは暗く白比率が低いため、
    # 書籍ページ本体に到達するまで外縁を削る。
    th, tw = trimmed.shape[:2]
    tgray = cv2.cvtColor(trimmed, cv2.COLOR_BGR2GRAY)
    _WHITE_MIN = 0.25
    row_white = np.mean(tgray >= 200, axis=1)   # (th,)
    col_white = np.mean(tgray >= 200, axis=0)   # (tw,)

    t2, b2, l2, r2 = 0, th - 1, 0, tw - 1
    while t2 < th // 4 and row_white[t2] < _WHITE_MIN:
        t2 += 1
    while b2 > 3 * th // 4 and row_white[b2] < _WHITE_MIN:
        b2 -= 1
    while l2 < tw // 4 and col_white[l2] < _WHITE_MIN:
        l2 += 1
    while r2 > 3 * tw // 4 and col_white[r2] < _WHITE_MIN:
        r2 -= 1

    if t2 or b2 < th - 1 or l2 or r2 < tw - 1:
        logger.debug("trim_page_border step2: (%d,%d) -> (%d,%d)",
                     tw, th, r2 - l2 + 1, b2 - t2 + 1)
        trimmed = trimmed[t2:b2 + 1, l2:r2 + 1]

    return trimmed

# ──────────────────────────────────────────────
# 書字方向検出 (縦書き / 横書き)
# ──────────────────────────────────────────────

def detect_writing_direction(image: np.ndarray) -> str:
    """
    見開き画像の書字方向を形態学的解析で推定する。

    アルゴリズム:
      1. CLAHE でコントラスト強調後、適応的二値化でテキスト領域を抽出
      2. 横長カーネルで水平方向にテキストを連結 → 横書き行の面積合計
      3. 縦長カーネルで垂直方向にテキストを連結 → 縦書き列の面積合計
      4. 面積スコアで比較（単純なカウントより頑健）

    Returns:
      "right_first" : 縦書き (右開き — 右ページが先)
      "left_first"  : 横書き (左開き — 左ページが先)
    """
    h_img, w_img = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # CLAHE でコントラスト強調 (籐背景・不均一照明に強くなる)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    # 適応的二値化（Otsu より不均一照明に強い）
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 8
    )

    # テキスト密度が極端に低い場合はデフォルト (縦書き) を返す
    text_density = np.count_nonzero(binary) / (h_img * w_img)
    if text_density < 0.01:
        logger.debug("テキスト密度が低いため、デフォルト (right_first) を使用します。")
        return "right_first"

    # ノイズ除去: 孤立した小さな点を除去
    kernel_clean = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_clean)

    # 推定文字サイズ: 短辺の 1/40 (例: 1500px → 37px)
    char_est = max(10, min(h_img, w_img) // 40)
    min_span = char_est * 3  # 有効な行/列として認める最小スパン

    # 横書き: 水平方向に文字を連結して行を検出 (面積で重み付け)
    h_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (char_est * 3, max(3, char_est // 4))
    )
    h_closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, h_kernel)
    h_cnts, _ = cv2.findContours(h_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h_score = sum(
        cv2.contourArea(c) for c in h_cnts if cv2.boundingRect(c)[2] > min_span
    )

    # 縦書き: 垂直方向に文字を連結して列を検出 (面積で重み付け)
    v_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, char_est // 4), char_est * 3)
    )
    v_closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, v_kernel)
    v_cnts, _ = cv2.findContours(v_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    v_score = sum(
        cv2.contourArea(c) for c in v_cnts if cv2.boundingRect(c)[3] > min_span
    )

    logger.debug(
        "書字方向推定: h_score=%.0f, v_score=%.0f → %s",
        h_score, v_score,
        "縦書き (right_first)" if v_score >= h_score else "横書き (left_first)",
    )

    return "right_first" if v_score >= h_score else "left_first"


def detect_page_order_by_numbers(image: np.ndarray) -> tuple[str, float]:
    """
    見開き画像の下端コーナーにあるページ番号の桁数（幅）を比較して
    ページ順を推定する。

    ヒューリスティック:
      - ページ番号は見開きの左端 / 右端の下部に孤立した小クラスタとして現れる
      - 桁数が少ない（幅が狭い）クラスタは若いページ番号 → そちらが先頭に近い
      - 左コーナーの方が幅が狭い → 左ページが先 (left_first / 横書き)
      - 右コーナーの方が幅が狭い → 右ページが先 (right_first / 縦書き)

    Returns:
      (order, confidence)  confidence=0.0 は判断不能を意味する。
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 下部 12% × 外側 15% のコーナーストリップを抽出
    strip_h = max(20, int(h * 0.12))
    corner_w = max(20, int(w * 0.15))
    left_corner  = gray[h - strip_h:, :corner_w]
    right_corner = gray[h - strip_h:, w - corner_w:]

    def _text_width(region: np.ndarray) -> float:
        """領域内の孤立テキスト塊の合計水平幅を返す。"""
        _, binary = cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # 文字を1塊にまとめる小さなクローズ
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
        cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = region.shape[0] * region.shape[1] * 0.002  # 領域の 0.2% 以上
        widths = [cv2.boundingRect(c)[2] for c in cnts if cv2.contourArea(c) > min_area]
        return float(sum(widths)) if widths else 0.0

    lw = _text_width(left_corner)
    rw = _text_width(right_corner)
    logger.debug(
        "detect_page_order_by_numbers: left_w=%.1f, right_w=%.1f", lw, rw
    )

    total = lw + rw
    if total < 1.0:
        return ("right_first", 0.0)  # 判断不能

    confidence = abs(lw - rw) / total
    if lw < rw:
        return ("left_first", confidence)   # 左コーナーが短い → 横書き
    else:
        return ("right_first", confidence)  # 右コーナーが短い → 縦書き

# ──────────────────────────────────────────────
# 見開き分割
# ──────────────────────────────────────────────

def find_center_seam(image: np.ndarray) -> int:
    """
    見開き画像の中央にある「綴じ目（影の線）」を検出する。
    
    アルゴリズム:
      1. 中央付近の輝度勾配（水平方向の微分）と輝度値を計算。
      2. 垂直方向に連続する「暗い線」に高いスコアを与える。
    """
    h, w = image.shape[:2]
    s, e = w // 3, 2 * w // 3
    roi = cv2.cvtColor(image[:, s:e], cv2.COLOR_BGR2GRAY)
    
    # 垂直方向の影を強調するために、縦方向に平滑化
    # (本の綴じ目は縦に長い影になる)
    v_blur = cv2.blur(roi, (1, h // 10))
    
    # 列ごとの平均輝度 (暗いほど綴じ目の可能性)
    col_intensity = v_blur.mean(axis=0)
    
    # 輝度の変化（エッジ）も考慮
    # 綴じ目の両脇は少し明るくなることが多い
    grad_x = cv2.Sobel(v_blur, cv2.CV_32F, 1, 0, ksize=3)
    col_grad = np.abs(grad_x).mean(axis=0)
    
    # スコア計算: 低輝度かつエッジが集中している場所
    # (255 - intensity) で暗いほど高スコア
    score = (255 - col_intensity) * 1.5 + col_grad
    
    # ガウシアンでノイズ除去
    smooth_k = max(11, (e - s) // 20) | 1
    score = cv2.GaussianBlur(score.reshape(1, -1), (smooth_k, 1), 0).flatten()
    
    best_rel = np.argmax(score)
    return s + best_rel

def center_seam_confidence(image: np.ndarray) -> float:
    """
    縦の綴じ目（垂直スプレッドの中心線）の「確からしさ」スコアを返す。

    戻り値:
      スコアが高いほど綴じ目が存在する可能性が高い。
      典型的に 200 以上なら分割対象と判断できる。
    """
    h, w = image.shape[:2]
    s, e = w // 3, 2 * w // 3
    roi = cv2.cvtColor(image[:, s:e], cv2.COLOR_BGR2GRAY)

    v_blur    = cv2.blur(roi, (1, max(3, h // 10)))
    col_intens = v_blur.mean(axis=0)
    grad_x    = cv2.Sobel(v_blur, cv2.CV_32F, 1, 0, ksize=3)
    col_grad  = np.abs(grad_x).mean(axis=0)

    score = (255 - col_intens) * 1.5 + col_grad
    smooth_k = max(11, (e - s) // 20) | 1
    score = cv2.GaussianBlur(score.reshape(1, -1), (smooth_k, 1), 0).flatten()
    return float(score.max())


def find_horizontal_seam(image: np.ndarray) -> int:
    """
    Portrait spread の横の綴じ目（水平分割線）を検出する。

    アルゴリズム: 暗線 + 勾配スコア（find_center_seam の水平版）
      書籍の見開きをカメラ90°傾けて撮影すると、綴じ目（背表紙の影）は
      画像内で水平方向の暗いバンドとして現れる。

      スコア = (255 - 行平均輝度) * 1.5 + 行方向の平均勾配
      中央1/3の範囲内でスコアが最も高い行を綴じ目と判定する。

      後処理として、得点最大行の近傍でコンテンツ量（白比率）が均等になる
      位置にファインチューニングする。

    制約: 結果を 30%〜70% の範囲にクランプ
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h, w = gray.shape

    # 中央1/3を探索範囲とする
    s, e = h // 3, 2 * h // 3
    roi = gray[s:e, :]

    # 水平方向にぼかして縦筋ノイズを除去し、行ごとの純粋な輝度を得る
    blur_w = max(w // 10, 5) | 1
    h_blur = cv2.blur(roi, (blur_w, 1))

    # 行ごとの平均輝度（暗いほど綴じ目の可能性）
    row_intensity = h_blur.mean(axis=1)

    # 輝度の変化（綴じ目の両脇は少し明るくなることが多い）
    grad_y = cv2.Sobel(h_blur.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    row_grad = np.abs(grad_y).mean(axis=1)

    # スコア計算: 低輝度かつエッジが集中している場所
    score = (255 - row_intensity) * 1.5 + row_grad

    # ガウシアンでノイズ除去
    smooth_k = max(11, (e - s) // 20) | 1
    score_smooth = cv2.GaussianBlur(
        score.reshape(-1, 1).astype(np.float32), (1, smooth_k), 0
    ).flatten()

    best_rel = int(np.argmax(score_smooth))
    seam_y = s + best_rel

    # 30%〜70% にクランプ（撮影ずれへの安全弁）
    lo, hi = int(h * 0.30), int(h * 0.70)
    seam_y = max(lo, min(hi, seam_y))

    logger.debug(
        "find_horizontal_seam: darkest row (score peak) at y=%d (%.1f%% of h=%d)",
        seam_y, seam_y / h * 100, h,
    )
    return seam_y


def split_spread(image: np.ndarray, page_order: str = "left_first") -> list[np.ndarray]:
    """
    見開き画像を左右のページに分割する（物理的分離）。
    """
    h, w = image.shape[:2]
    
    # 中心線を特定
    seam_x = find_center_seam(image)
    logger.info(f"Detected center seam at x={seam_x} ({seam_x/w*100:.1f}%)")
    
    # 物理的に分割
    left_img  = image[:, :seam_x].copy()
    right_img = image[:, seam_x:].copy()

    # 綴じ目側の内側エッジに残る影・ノイズをホワイトアウト
    # 幅の約 1% をホワイトマージンとして塗りつぶす
    margin = max(4, int(w * 0.01))
    left_img[:, -margin:] = 255
    right_img[:, :margin] = 255

    pages = [left_img, right_img]
    if page_order == "right_first":
        pages.reverse()
        
    return pages

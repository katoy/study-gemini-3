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
    """4点を [左上, 右上, 右下, 左下] の順に整列する。"""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """4点座標に基づき透視変換を実行する。"""
    rect = order_points(pts)
    tl, tr, br, bl = rect
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (width, height))

# ──────────────────────────────────────────────
# ページ輪郭検出 (内部実装)
# ──────────────────────────────────────────────

def _detect_by_edges(image: np.ndarray, sensitivity: str = "medium") -> np.ndarray | None:
    """
    Canny エッジ検出ベースのページ輪郭検出（強化版）。
    """
    params = {"low": (100, 250), "medium": (50, 200), "high": (20, 100)}
    low_t, high_t = params.get(sensitivity, (50, 200))

    h, w = image.shape[:2]
    scale = 800 / h
    resized = cv2.resize(image, (int(w * scale), 800))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    
    # ノイズ除去とエッジ抽出
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, low_t, high_t)
    
    # エッジを太く繋げる
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edged = cv2.dilate(edged, kernel, iterations=1)

    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

    img_area = resized.shape[0] * resized.shape[1]
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.1: 
            continue
            
        # 凸包を取得して形状を安定させる
        hull = cv2.convexHull(cnt)
        peri = cv2.arcLength(hull, True)
        
        # 近似精度を段階的に下げて 4点を探す
        for eps in [0.01, 0.02, 0.03, 0.05, 0.08]:
            approx = cv2.approxPolyDP(hull, eps * peri, True)
            if len(approx) == 4:
                return (approx.reshape(4, 2) / scale).astype("float32")
            
        # 4点にならない場合は最小外接矩形を採用
        rect = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rect)
        return (box / scale).astype("float32")

    return None


def _detect_by_brightness(image: np.ndarray) -> np.ndarray | None:
    """
    輝度ベースのページ輪郭検出（強化版）。
    """
    h, w = image.shape[:2]
    scale = 800 / h
    small = cv2.resize(image, (int(w * scale), 800))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # Otsu 二値化でページ（明るい部分）を抽出
    otsu_thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 閾値を少し下げて、ページ端を巻き込まないようにする
    thresh_val = max(otsu_thresh * 0.8, 40)
    _, mask = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)

    # 収縮処理を最小限に
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < (800 * int(w * scale)) * 0.15:
        return None

    hull = cv2.convexHull(largest)
    peri = cv2.arcLength(hull, True)
    
    # 近似精度を段階的に下げて 4点を探す
    for eps in [0.01, 0.02, 0.03, 0.05, 0.08]:
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            return (approx.reshape(4, 2) / scale).astype("float32")

    rect = cv2.minAreaRect(hull)
    box = cv2.boxPoints(rect) / scale
    return box.astype("float32")


def detect_page_contour(image: np.ndarray, sensitivity: str = "medium") -> np.ndarray | None:
    """
    書籍ページの四角い輪郭を検出する。

    エッジ検出を優先し、失敗した場合は輝度ベース検出にフォールバックする。
    """
    contour = _detect_by_edges(image, sensitivity)
    if contour is not None:
        return contour

    logger.debug("エッジ検出失敗。輝度ベース検出にフォールバックします。")
    return _detect_by_brightness(image)


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
    透視変換後の画像から暗い外縁 (写真背景の残留部分) を除去する。
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 輝度が極端に低い (20未満) ピクセルを背景候補とする
    threshold = 20
    bright = gray > threshold
    
    # 1行または1列の「ほとんど」が明るい（ページ）部分を探す
    # ページなら 80% 程度は明るいはず
    rows = np.mean(bright, axis=1) > 0.8
    cols = np.mean(bright, axis=0) > 0.8

    if not rows.any() or not cols.any():
        return image

    r_min, r_max = int(np.where(rows)[0][0]),  int(np.where(rows)[0][-1])
    c_min, c_max = int(np.where(cols)[0][0]),  int(np.where(cols)[0][-1])

    # ほとんど削る必要がない場合はそのまま返す
    if r_min < h * 0.01 and r_max > h * 0.99 and c_min < w * 0.01 and c_max > w * 0.99:
        return image

    trimmed = image[r_min:r_max+1, c_min:c_max+1]
    logger.debug("trim_page_border: (%d,%d) -> (%d,%d)", w, h, trimmed.shape[1], trimmed.shape[0])
    return trimmed

# ──────────────────────────────────────────────
# 書字方向検出 (縦書き / 横書き)
# ──────────────────────────────────────────────

def detect_writing_direction(image: np.ndarray) -> str:
    """
    見開き画像の書字方向を形態学的解析で推定する。

    アルゴリズム:
      1. 2値化でテキスト領域を抽出
      2. 横長カーネルで水平方向にテキストを連結 → 横書き行の数を数える
      3. 縦長カーネルで垂直方向にテキストを連結 → 縦書き列の数を数える
      4. どちらの行/列が多いかで方向を判定

    Returns:
      "right_first" : 縦書き (右開き — 右ページが先)
      "left_first"  : 横書き (左開き — 左ページが先)
    """
    h_img, w_img = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # テキスト密度が極端に低い場合はデフォルト (縦書き) を返す
    text_density = np.count_nonzero(binary) / (h_img * w_img)
    if text_density < 0.01:
        logger.debug("テキスト密度が低いため、デフォルト (right_first) を使用します。")
        return "right_first"

    # 推定文字サイズ: 短辺の 1/40 (例: 1500px → 37px)
    char_est = max(10, min(h_img, w_img) // 40)
    min_span = char_est * 4  # 有効な行/列として認める最小スパン

    # 横書き: 水平方向に文字を連結して行を検出
    h_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (char_est * 2, max(3, char_est // 4))
    )
    h_closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, h_kernel)
    h_cnts, _ = cv2.findContours(h_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h_line_count = sum(
        1 for c in h_cnts if cv2.boundingRect(c)[2] > min_span
    )

    # 縦書き: 垂直方向に文字を連結して列を検出
    v_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, char_est // 4), char_est * 2)
    )
    v_closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, v_kernel)
    v_cnts, _ = cv2.findContours(v_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    v_line_count = sum(
        1 for c in v_cnts if cv2.boundingRect(c)[3] > min_span
    )

    logger.debug(
        "書字方向推定: horizontal_rows=%d, vertical_cols=%d → %s",
        h_line_count, v_line_count,
        "縦書き (right_first)" if v_line_count >= h_line_count else "横書き (left_first)",
    )

    return "right_first" if v_line_count >= h_line_count else "left_first"

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

def split_spread(image: np.ndarray, page_order: str = "left_first") -> list[np.ndarray]:
    """
    見開き画像を左右のページに分割する（物理的分離）。
    """
    h, w = image.shape[:2]
    
    # 中心線を特定
    seam_x = find_center_seam(image)
    logger.info(f"Detected center seam at x={seam_x} ({seam_x/w*100:.1f}%)")
    
    # 物理的に分割
    left_img = image[:, :seam_x]
    right_img = image[:, seam_x:]
    
    pages = [left_img, right_img]
    if page_order == "right_first":
        pages.reverse()
        
    return pages

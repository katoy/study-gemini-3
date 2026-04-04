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
# ページ輪郭検出
# ──────────────────────────────────────────────

def detect_page_contour(image: np.ndarray, sensitivity: str = "medium") -> np.ndarray | None:
    """書籍ページの四角い輪郭を検出する。"""
    params = {"low": (100, 250), "medium": (50, 200), "high": (20, 100)}
    low_t, high_t = params.get(sensitivity, (50, 200))

    h, w = image.shape[:2]
    scale = 800 / h
    resized = cv2.resize(image, (int(w * scale), 800))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    edged = cv2.Canny(cv2.GaussianBlur(gray, (7, 7), 0), low_t, high_t)
    edged = cv2.dilate(edged, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))

    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

    img_area = resized.shape[0] * resized.shape[1]
    for cnt in contours:
        if cv2.contourArea(cnt) < img_area * 0.2:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4:
            return (approx.reshape(4, 2) / scale).astype("float32")

    return None


def detect_page_contour_ai(image: np.ndarray) -> np.ndarray | None:
    """
    AI (Segmentation モデル) を用いて書籍ページの境界を検出する。
    将来のアップデートで U-Net / DeepLabV3+ 等のモデル推論を実装予定。
    現在は既存の検出器を最高感度で呼び出すフォールバックとして機能。
    """
    logger.warning("AI ページ境界検出は現在準備中です。既存の検出器(high)にフォールバックします。")
    return detect_page_contour(image, sensitivity="high")

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

def split_spread(image: np.ndarray, page_order: str = "left_first") -> list[np.ndarray]:
    """見開き画像を左右に分割する。"""
    h, w = image.shape[:2]
    mid = w // 2
    margin = max(1, int(w * 0.02))
    strip = cv2.cvtColor(image[:, mid-margin:mid+margin], cv2.COLOR_BGR2GRAY)
    best_col = mid - margin + int(np.argmin(np.var(strip, axis=0)))

    left, right = image[:, :best_col], image[:, best_col:]
    return [right, left] if page_order == "right_first" else [left, right]

"""
page_detector.py
================
ページ境界検出、透視変換、および見開き分割を行うモジュール。
"""

from __future__ import annotations

import cv2
import numpy as np
from typing import Optional, List, Tuple

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

def detect_page_contour(image: np.ndarray, sensitivity: str = "medium") -> Optional[np.ndarray]:
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
    for c in contours:
        if cv2.contourArea(c) < img_area * 0.1: continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            return (approx.reshape(4, 2) / scale).astype("float32")
    return None

# ──────────────────────────────────────────────
# 見開き分割
# ──────────────────────────────────────────────

def split_spread(image: np.ndarray, page_order: str = "left_first") -> List[np.ndarray]:
    """見開き画像を左右に分割する。"""
    h, w = image.shape[:2]
    mid = w // 2
    margin = max(1, int(w * 0.02))
    strip = cv2.cvtColor(image[:, mid-margin:mid+margin], cv2.COLOR_BGR2GRAY)
    best_col = mid - margin + int(np.argmin(np.var(strip, axis=0)))

    left, right = image[:, :best_col], image[:, best_col:]
    return [right, left] if page_order == "right_first" else [left, right]

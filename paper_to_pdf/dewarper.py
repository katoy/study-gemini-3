"""
dewarper.py
===========
書籍ページの湾曲補正モジュール。
"""

from __future__ import annotations

import logging
import cv2
import numpy as np
from utils.device import get_device
from utils.image import extract_line_profiles

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 補正コアロジック
# ──────────────────────────────────────────────

def _is_image_broken(original: np.ndarray, processed: np.ndarray) -> bool:
    """補正後の画像が異常（白紙化など）になっていないかチェックする。"""
    mean = np.mean(processed)
    if mean > 250 or mean < 5:
        return True
    return False

def _advanced_polynomial_dewarp(image: np.ndarray, is_vertical: bool = False) -> np.ndarray:
    """
    複数行の曲率を統合し、反復的に平坦化を行う。
    """
    curr_img = image.copy()
    
    # 縦書き対応
    if is_vertical:
        curr_img = cv2.rotate(curr_img, cv2.ROTATE_90_CLOCKWISE)

    # 3回の反復補正で精度を追い込む
    for iteration in range(3):
        h, w = curr_img.shape[:2]
        gray = cv2.cvtColor(curr_img, cv2.COLOR_BGR2GRAY)
        
        # 共通ユーティリティで行プロファイルを抽出
        pts_np, weights_np, _ = extract_line_profiles(gray, target_h=500, margin_v=0.10, margin_h=0.05)
                
        if len(pts_np) < 200:
            break
            
        # 重み付き最小二乗法で 3次多項式フィッティング
        z = np.polyfit(pts_np[:, 0], pts_np[:, 1], 3, w=weights_np)
        
        x_f = np.arange(w, dtype=np.float32)
        target = np.polyval(z, x_f)
        
        # 補正限界の適用
        limit = h * 0.35
        target = np.clip(target, -limit, limit)
        curv_pct = (np.max(target) - np.min(target)) / h * 100.0
        
        if curv_pct < 0.2: # 十分に平坦
            break
            
        if curv_pct < 65.0:
            mx, my = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
            # 補正適用
            my = (my + target.astype(np.float32) * 0.95).astype(np.float32)
            my = np.clip(my, 0, h - 1)
            
            res = cv2.remap(curr_img, mx, my, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
            
            if not _is_image_broken(curr_img, res):
                curr_img = res
                logger.debug("polynomial: iter %d (Curve=%.1f%%)", iteration+1, curv_pct)
            else:
                break

    if is_vertical:
        curr_img = cv2.rotate(curr_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        
    return curr_img

class Dewarper:
    def __init__(self, mode="dewarpnet", is_vertical: bool = False):
        self.mode = mode
        self.is_vertical = is_vertical
        self._effective_mode = "polynomial" # 現状は多項式補正を推奨

    def load_model(self, progress_cb=None):
        return True

    def dewarp(self, image_bgr):
        try:
            return _advanced_polynomial_dewarp(image_bgr, is_vertical=self.is_vertical)
        except Exception as e:
            logger.error(f"Dewarp failed: {e}")
            return image_bgr

    def unload_model(self):
        pass

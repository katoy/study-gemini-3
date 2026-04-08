"""
dewarper.py
===========
書籍ページの湾曲補正モジュール（高精度整列版）。
"""

from __future__ import annotations

import logging
import cv2
import numpy as np
from utils.device import get_device

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 補正コアロジック
# ──────────────────────────────────────────────

def _is_image_broken(original: np.ndarray, processed: np.ndarray) -> bool:
    """補正後の画像が異常（白紙化など）になっていないかチェックする。"""
    # 完全に真っ白か真っ黒になった場合を検出
    mean = np.mean(processed)
    if mean > 250 or mean < 5:
        return True
    return False

def _advanced_polynomial_dewarp(image: np.ndarray, is_vertical: bool = False) -> np.ndarray:
    """
    複数行の曲率を統合し、反復的に平坦化を行う。
    3回反復することで、文字列の並びをほぼ完璧な水平に整列させる。
    """
    curr_img = image.copy()
    
    # 縦書き対応: 90度回転
    if is_vertical:
        curr_img = cv2.rotate(curr_img, cv2.ROTATE_90_CLOCKWISE)

    # 1. 3回の反復補正で精度を追い込む
    for iteration in range(3):
        h, w = curr_img.shape[:2]
        gray = cv2.cvtColor(curr_img, cv2.COLOR_BGR2GRAY)
        scale = 500.0 / h # 若干解像度を上げて精度向上
        small = cv2.resize(gray, (int(w * scale), 500))
        
        # テキスト行（水平エッジ）の抽出
        # ガウシアンブラーで細かいノイズを除去し、行のうねりを強調
        blur = cv2.GaussianBlur(small, (0, 7), 2)
        grad = np.abs(cv2.Sobel(blur, cv2.CV_64F, 0, 1, ksize=3))
        grad = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        _, m = cv2.threshold(grad, 50, 255, cv2.THRESH_BINARY)
        
        # ノイズカット: 四方の端を無視
        sh, sw = m.shape[:2]
        m[:int(sh * 0.10), :] = 0
        m[int(sh * 0.90):, :] = 0
        m[:, :int(sw * 0.05)] = 0
        m[:, int(sw * 0.95):] = 0
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (sw // 12, 1))
        mask = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        all_pts = []
        all_weights = []
        for c in cnts:
            br = cv2.boundingRect(c)
            # 行の長さ (width)
            line_w = br[2]
            if line_w < sw * 0.2: continue
            
            cp = c.reshape(-1, 2).astype(np.float32)
            ux = np.unique(cp[:, 0])
            if len(ux) < 30: continue
            
            uy = np.array([np.mean(cp[cp[:, 0] == val, 1]) for val in ux])
            uy_norm = uy - np.mean(uy)
            
            # 行が長いほど、信頼できる情報として重みを高くする (WLS)
            weight = (line_w / sw) ** 2
            for xv, yv in zip(ux, uy_norm):
                all_pts.append((xv / scale, yv / scale))
                all_weights.append(weight)
                
        if len(all_pts) < 200:
            break
            
        pts_np = np.array(all_pts)
        weights_np = np.array(all_weights)
        
        # 重み付き最小二乗法で 3次多項式フィッティング
        z = np.polyfit(pts_np[:, 0], pts_np[:, 1], 3, w=weights_np)
        
        x_f = np.arange(w, dtype=np.float32)
        target = np.polyval(z, x_f)
        
        # 補正限界を 35% まで緩和し、深い歪みに対応
        limit = h * 0.35
        target = np.clip(target, -limit, limit)
        
        curv_pct = (np.max(target) - np.min(target)) / h * 100.0
        
        # 0.2% 未満なら整列完了とみなす
        if curv_pct < 0.2:
            break
            
        if curv_pct < 65.0:
            mx, my = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
            # ほぼ 100% 補正 (0.95倍) で追い込む
            my = (my + target.astype(np.float32) * 0.95).astype(np.float32)
            my = np.clip(my, 0, h - 1)
            
            res = cv2.remap(curr_img, mx, my, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
            
            if not _is_image_broken(curr_img, res):
                curr_img = res
                logger.info("polynomial: iter %d heavy (Curve=%.1f%%)", iteration+1, curv_pct)
            else:
                break

    if is_vertical:
        curr_img = cv2.rotate(curr_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        
    return curr_img

class Dewarper:
    def __init__(self, mode="dewarpnet", is_vertical: bool = False):
        self.mode = mode
        self.is_vertical = is_vertical
        self._effective_mode = "polynomial" # 多項式補正をメインに据える

    def load_model(self, progress_cb=None):
        # AI モデル (DewarpNet) を使用する場合はここでロード可能だが、
        # 現在はより安定した多項式補正のみを使用
        return True

    def dewarp(self, image_bgr):
        try:
            return _advanced_polynomial_dewarp(image_bgr, is_vertical=self.is_vertical)
        except Exception as e:
            logger.error(f"Dewarp failed: {e}")
            return image_bgr

    def unload_model(self):
        pass

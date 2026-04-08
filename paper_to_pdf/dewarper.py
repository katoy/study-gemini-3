"""
dewarper.py
===========
書籍ページの湾曲補正モジュール。
"""

from __future__ import annotations

import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    import torch
    import torch.nn as nn

from utils.device import get_device
from utils.paths import CACHE_DIR

logger = logging.getLogger(__name__)

_WC_MODEL_PATH = CACHE_DIR / "unetnc_doc3d.pkl"
_BM_MODEL_PATH = CACHE_DIR / "dnetccnl_doc3d.pkl"
_WC_INPUT_SIZE = (256, 256)
_BM_INPUT_SIZE = (128, 128)

# ──────────────────────────────────────────────
# 補正コアロジック
# ──────────────────────────────────────────────

def _advanced_polynomial_dewarp(image: np.ndarray) -> np.ndarray:
    """
    複数行の曲率を統合し、反復的に平坦化を行う高度な多項式補正。
    """
    h, w = image.shape[:2]
    curr_img = image.copy()
    
    # 1. 反復補正
    for iteration in range(3):
        gray = cv2.cvtColor(curr_img, cv2.COLOR_BGR2GRAY)
        scale = 400.0 / h
        small = cv2.resize(gray, (int(w * scale), 400))
        
        # エッジ抽出
        grad = cv2.normalize(np.abs(cv2.Sobel(small, cv2.CV_64F, 0, 1, ksize=3)), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        _, m = cv2.threshold(grad, 40, 255, cv2.THRESH_BINARY)
        
        sw, sh = small.shape[1], 400
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (sw // 10, 1))
        mask = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        all_pts = []
        for c in cnts:
            if cv2.boundingRect(c)[2] < sw * 0.15: continue
            cp = c.reshape(-1, 2).astype(np.float32)
            ux = np.unique(cp[:, 0])
            if len(ux) < 15: continue
            # 行ごとの正規化
            uy = np.array([np.mean(cp[cp[:, 0] == val, 1]) for val in ux])
            uy_norm = uy - np.mean(uy)
            for xv, yv in zip(ux, uy_norm):
                all_pts.append((xv / scale, yv / scale))
        
        if len(all_pts) < 50: break
        
        pts_np = np.array(all_pts)
        xs, ys = pts_np[:, 0], pts_np[:, 1]
        z = np.polyfit(xs, ys, 3)
        
        a, b, c, d = z
        x_f = np.arange(w, dtype=np.float32)
        target = a*(x_f**3) + b*(x_f**2) + c*x_f + d
        curv_pct = (np.max(target) - np.min(target)) / h * 100.0
        
        if curv_pct < 0.5 or curv_pct > 50.0: break
        
        slope = 3*a*(x_f**2) + 2*b*x_f + c
        stretch = np.sqrt(1 + slope**2)
        if np.max(stretch) > 2.0: break

        my, mx = np.indices((h, w), dtype=np.float32)
        my = ((my - h/2.0) * stretch + h/2.0 + (target - np.median(target))).astype(np.float32)
        curr_img = cv2.remap(curr_img, mx, my, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
        logger.info("polynomial: 補正適用 [%d回目] (Curve=%.1f%%)", iteration+1, curv_pct)
        if curv_pct < 1.0: break

    return curr_img

# ──────────────────────────────────────────────
# 推論ラッパー
# ──────────────────────────────────────────────

def _dewarpnet_inference(wc_model, bm_model, image_bgr, device) -> np.ndarray:
    import torch
    import torch.nn.functional as F
    h_orig, w_orig = image_bgr.shape[:2]
    img_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    wc_inp = cv2.resize(img_rgb, (256, 256))
    wc_inp = torch.from_numpy(wc_inp.transpose(2, 0, 1)).unsqueeze(0).to(device)
    with torch.no_grad():
        pred_wc = torch.nn.Hardtanh(0, 1.0)(wc_model(wc_inp))
        bm = bm_model(F.interpolate(pred_wc, (128, 128), mode="bilinear", align_corners=True))
    bm_np = F.interpolate(bm, (h_orig, w_orig), mode="bilinear", align_corners=True).squeeze(0).permute(1, 2, 0).cpu().numpy()
    bm_norm = bm_np * 0.5 + 0.5
    return cv2.remap(image_bgr, (bm_norm[:,:,0]*w_orig).astype(np.float32), (bm_norm[:,:,1]*h_orig).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

class Dewarper:
    def __init__(self, mode="dewarpnet"):
        self.mode = mode; self._effective_mode = mode
        self._device = self._wc_model = self._bm_model = None

    def load_model(self, progress_cb=None):
        if self.mode == "none": return True
        self._device = get_device()
        try:
            if self.mode == "dewarpnet":
                from utils.dewarpnet_arch import UnetGenerator, DnetCCNL, convert_state_dict
                if not _WC_MODEL_PATH.exists(): self._effective_mode = "polynomial"; return False
                wc = UnetGenerator(3, 3, 7); wc.load_state_dict(convert_state_dict(torch.load(str(_WC_MODEL_PATH), map_location=self._device, weights_only=False)["model_state"]))
                wc.eval(); self._wc_model = wc.to(self._device)
                bm = DnetCCNL(128, 3, 2, 32); bm.load_state_dict(convert_state_dict(torch.load(str(_BM_MODEL_PATH), map_location=self._device, weights_only=False)["model_state"]))
                bm.eval(); self._bm_model = bm.to(self._device)
                return True
            return True
        except Exception: self._effective_mode = "polynomial"; return False

    def dewarp(self, image_bgr):
        if self._effective_mode == "none": return image_bgr
        res = image_bgr
        if self._effective_mode == "dewarpnet" and self._wc_model is not None:
            try: res = _dewarpnet_inference(self._wc_model, self._bm_model, image_bgr, self._device)
            except Exception: pass
        return _advanced_polynomial_dewarp(res)

    def unload_model(self):
        self._wc_model = self._bm_model = None

"""
dewarper.py
===========
書籍ページの湾曲補正モジュール。
"""

from __future__ import annotations

import logging
import cv2
import numpy as np
import torch
import torch.nn.functional as F

from utils.device import get_device
from utils.download import download_file
from utils.image import extract_line_profiles
from utils.paths import CACHE_DIR
from utils.dewarpnet_arch import UnetGenerator, DnetCCNL, convert_state_dict

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# AI 補正 (DewarpNet)
# ──────────────────────────────────────────────

class _DewarpNetInferencer:
    """
    DewarpNet による AI 湾曲補正の推論エンジン。
    """
    _URLS = {
        "wc": "https://huggingface.co/datasets/docdewarper/dewarpnet_weights/resolve/main/unetnc_doc3d.pkl",
        "bm": "https://huggingface.co/datasets/docdewarper/dewarpnet_weights/resolve/main/dnetccnl_doc3d.pkl"
    }
    _SHA256 = {
        "wc": "3afe0c49be517fab5408afda77ac03eef99844aab3f90efb7f68c8ffab2f4383",
        "bm": "23a149d1e9ad132e0bd8d156d7c4c1be5ff00bfc797403c743bdf29d99555133",
    }

    def __init__(self):
        self.device = get_device()
        self.wc_model = UnetGenerator(input_nc=3, output_nc=3, num_downs=7, ngf=64)
        self.bm_model = DnetCCNL(img_size=128, in_channels=3, out_channels=2, filters=32)
        self._load_models()

    def _load_models(self):  # pragma: no cover
        for key, model in [("wc", self.wc_model), ("bm", self.bm_model)]:
            path = CACHE_DIR / f"dewarpnet_{key}.pkl"
            if not path.exists():
                download_file(self._URLS[key], path, expected_sha256=self._SHA256[key])
            state = torch.load(str(path), map_location="cpu", weights_only=True)
            if "model_state_dict" in state:
                state = state["model_state_dict"]
            elif "model_state" in state:
                state = state["model_state"]
            model.load_state_dict(convert_state_dict(state))
            model.to(self.device).eval()

    def dewarp(self, image_bgr: np.ndarray) -> np.ndarray:
        h, w = image_bgr.shape[:2]
        img_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        img_t = cv2.resize(img_rgb, (256, 256)).astype(np.float32) / 255.0
        img_t = torch.from_numpy(img_t).permute(2, 0, 1).unsqueeze(0).to(self.device)
        with torch.no_grad():
            wc = self.wc_model(img_t)
            bm = self.bm_model(wc)
            bm = F.interpolate(bm, size=(h, w), mode="bilinear", align_corners=True)
            bm = bm[0].permute(1, 2, 0).cpu().numpy()
        mx = (bm[:, :, 0] + 1.0) * (w - 1) / 2.0
        my = (bm[:, :, 1] + 1.0) * (h - 1) / 2.0
        result = cv2.remap(image_bgr, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LANCZOS4)
        if _is_result_invalid(image_bgr, result):
            logger.warning("DewarpNet の出力が異常なため元画像を返します。")
            return image_bgr
        return result

# ──────────────────────────────────────────────
# 多項式補正 (Polynomial)
# ──────────────────────────────────────────────

def _is_result_invalid(original: np.ndarray, processed: np.ndarray) -> bool:
    """
    補正結果が無効かどうかを判定する。

    判定基準:
      1. 平均輝度が極端 (> 250 or < 5): 全白・全黒
      2. コンテンツ消失: 元画像に暗ピクセル(< 100)が十分あるにもかかわらず
         処理後に 90% 以上が消えた場合 → テキスト破壊とみなす
    """
    mean = np.mean(processed)
    if mean > 250 or mean < 5:
        return True

    # コンテンツ保持チェック: 元画像に有意なテキストがある場合のみ評価
    orig_gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    proc_gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
    orig_dark = float(np.mean(orig_gray < 100))
    proc_dark = float(np.mean(proc_gray < 100))
    # 元画像の暗ピクセルが 1% 以上あるのに、処理後に 90% 以上消えた → 無効
    if orig_dark > 0.01 and proc_dark < orig_dark * 0.1:
        return True

    return False

def _advanced_polynomial_dewarp(image: np.ndarray, is_vertical: bool = False) -> np.ndarray:
    curr_img = image.copy()
    if is_vertical:
        curr_img = cv2.rotate(curr_img, cv2.ROTATE_90_CLOCKWISE)
    for iteration in range(3):
        h, w = curr_img.shape[:2]
        pts_np, weights_np, _ = extract_line_profiles(cv2.cvtColor(curr_img, cv2.COLOR_BGR2GRAY), target_h=500, margin_h=0.15)
        if len(pts_np) < 200:
            break
        z = np.polyfit(pts_np[:, 0], pts_np[:, 1], 3, w=weights_np)
        target = np.polyval(z, np.arange(w, dtype=np.float32))
        target = np.clip(target, -h*0.35, h*0.35)
        curv_pct = (np.max(target) - np.min(target)) / h * 100.0
        if curv_pct < 0.2:
            break
        if curv_pct < 35.0:
            mx, my = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
            my = np.clip(my + target.astype(np.float32) * 0.95, 0, h - 1).astype(np.float32)
            res = cv2.remap(curr_img, mx, my, cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
            if not _is_result_invalid(curr_img, res):
                curr_img = res
                logger.debug("poly iter %d", iteration)
            else:
                break
    if is_vertical:
        curr_img = cv2.rotate(curr_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return curr_img

# ──────────────────────────────────────────────
# メインクラス
# ──────────────────────────────────────────────

class Dewarper:
    def __init__(self, mode="dewarpnet", is_vertical: bool = False):
        self.mode = mode
        self.is_vertical = is_vertical
        self._ai_inferencer = None

    def load_model(self, progress_cb=None):
        if self.mode == "dewarpnet":
            try:
                self._ai_inferencer = _DewarpNetInferencer()
            except Exception as e:
                logger.warning("DewarpNet のロードに失敗しました: %s。polynomial にフォールバックします。", e)
                self.mode = "polynomial"
        return True

    def dewarp(self, image_bgr: np.ndarray) -> np.ndarray:
        if self.mode == "dewarpnet" and self._ai_inferencer:
            try:
                return self._ai_inferencer.dewarp(image_bgr)
            except Exception as e:
                logger.warning("DewarpNet 推論失敗: %s。polynomial にフォールバックします。", e)
                return _advanced_polynomial_dewarp(image_bgr, self.is_vertical)
        try:
            return _advanced_polynomial_dewarp(image_bgr, self.is_vertical)
        except Exception as e:
            logger.warning("polynomial dewarp 失敗: %s。元画像を返します。", e)
            return image_bgr

    def unload_model(self):
        self._ai_inferencer = None

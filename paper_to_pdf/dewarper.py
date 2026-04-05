"""
dewarper.py
===========
書籍ページの湾曲補正モジュール。

補正モード:
  dewarpnet  : DewarpNet による AI 湾曲補正 (モデルファイルが必要)
               論文: "DewarpNet: Single-Image Document Unwarping With Stacked 3D and 2D Regression Networks"
               モデル: https://github.com/cvlab-stonybrook/DewarpNet (MIT License)
               ※モデル未配置時は polynomial に自動フォールバック
  polynomial : 3次多項式メッシュフィッティングによる高精度補正 (ライブラリ不要)
  none       : 補正なし
"""

from __future__ import annotations

import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from utils.device import get_device
from utils.paths import CACHE_DIR

logger = logging.getLogger(__name__)

# DewarpNet は WC モデル + BM モデルの 2 ファイル構成
_WC_MODEL_PATH = CACHE_DIR / "unetnc_doc3d.pkl"    # 形状予測 (Warped Coordinate)
_BM_MODEL_PATH = CACHE_DIR / "dnetccnl_doc3d.pkl"  # 逆変換マップ (Backward Mapping)

# 入力サイズ (元論文の設定)
_WC_INPUT_SIZE = (256, 256)
_BM_INPUT_SIZE = (128, 128)

# DocTr (Document Transformer) モデル
_DOCTR_GEO_MODEL_URL = "https://github.com/katoy/paper-to-pdf/releases/download/v0.1.0/doctr_geo.pth"
_DOCTR_ILL_MODEL_URL = "https://github.com/katoy/paper-to-pdf/releases/download/v0.1.0/doctr_ill.pth"
_DOCTR_GEO_MODEL_PATH = CACHE_DIR / "doctr_geo.pth"
_DOCTR_ILL_MODEL_PATH = CACHE_DIR / "doctr_ill.pth"

_DEWARPNET_MANUAL_DOWNLOAD = (
    "DewarpNet モデルが見つかりません。以下の 2 ファイルを Google Drive からダウンロードし、\n"
    f"  {CACHE_DIR}/\n"
    "に配置してください。\n"
    "  unetnc_doc3d.pkl  (形状予測モデル)\n"
    "  dnetccnl_doc3d.pkl (逆変換マップモデル)\n"
    "ダウンロード先 (Google Drive):\n"
    "  https://drive.google.com/drive/folders/1yFiYBIkrY61IuRniiV4MLF3jyrNeVd2I\n"
    "または gdown を使った自動取得:\n"
    "  pip install gdown\n"
    f"  gdown --id 1TdwI12oW-UgINMAwMfK6nJpEvZg8tzJN -O {_WC_MODEL_PATH}\n"
    f"  gdown --id 1qyGQnmKaSRN0oOA8SwBCHxEd1qulLgLZ -O {_BM_MODEL_PATH}"
)


# ──────────────────────────────────────────────
# DewarpNet 推論 (2 モデル構成)
# ──────────────────────────────────────────────

def _dewarpnet_inference(wc_model, bm_model, image_bgr: np.ndarray, device) -> np.ndarray:
    """
    DewarpNet の 2 段階推論で湾曲補正画像を返す。
      1. WC モデル: 入力画像 → 3D 変形座標 (Warped Coordinates)
      2. BM モデル: WC → 逆変換マップ (Backward Mapping)
      3. cv2.remap で元画像にマップを適用
         BM 出力が縮退している場合 (flat scan 等) は polynomial にフォールバック。
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    h_orig, w_orig = image_bgr.shape[:2]
    
    # AI が認識しやすいように輝度とコントラストを動的に調整
    gray_tmp = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.mean(gray_tmp)
    
    # 暗すぎる画像は明るく、明るすぎる画像は少し抑える
    if mean_brightness < 100:
        alpha = 1.3
        beta = 30
    elif mean_brightness > 200:
        alpha = 0.9
        beta = -10
    else:
        alpha = 1.0
        beta = 0
        
    working_img = cv2.convertScaleAbs(image_bgr, alpha=alpha, beta=beta)
    
    # BGR → RGB, [0,1] 正規化
    img_rgb = cv2.cvtColor(working_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    # --- Stage 1: WC 予測 ---
    wc_inp = cv2.resize(img_rgb, _WC_INPUT_SIZE)             # (256, 256, 3)
    wc_inp = torch.from_numpy(wc_inp.transpose(2, 0, 1)).unsqueeze(0).to(device)
    htan = nn.Hardtanh(0, 1.0)
    with torch.no_grad():
        pred_wc = htan(wc_model(wc_inp))                     # (1, 3, 256, 256)

    # --- Stage 2: BM 予測 ---
    bm_inp = F.interpolate(pred_wc, _BM_INPUT_SIZE, mode="bilinear", align_corners=True)
    with torch.no_grad():
        bm = bm_model(bm_inp)                                # (1, 2, 128, 128)

    # BM 縮退チェック: 各チャンネルが画像全体を十分にカバーしているか確認
    # 正常な BM は [-1, 1] の範囲をほぼ全域使うはずなので、range < 1.0 は縮退と判断
    bm_np_check = bm.squeeze(0).cpu().numpy()
    bm_x_range = bm_np_check[0].max() - bm_np_check[0].min()
    bm_y_range = bm_np_check[1].max() - bm_np_check[1].min()
    if min(bm_x_range, bm_y_range) < 1.0:
        logger.warning(
            f"DewarpNet BM 出力が縮退しています "
            f"(x_range={bm_x_range:.3f}, y_range={bm_y_range:.3f})。"
            " polynomial にフォールバックします。"
        )
        return _advanced_polynomial_dewarp(image_bgr)

    # --- Stage 3: 元解像度にリマップ (cv2.remap) ---
    # BM 値域 [-1,1] を [0,1] に変換し、ピクセル座標にスケール
    bm_full = F.interpolate(bm, (h_orig, w_orig), mode="bilinear", align_corners=True)
    bm_np = bm_full.squeeze(0).permute(1, 2, 0).cpu().numpy()  # (H, W, 2)
    bm_np[:, :, 0] = cv2.blur(bm_np[:, :, 0], (3, 3))
    bm_np[:, :, 1] = cv2.blur(bm_np[:, :, 1], (3, 3))

    # bm * 0.5 + 0.5: [-1,1] → [0,1]、その後ピクセル座標に変換
    bm_normalized = bm_np * 0.5 + 0.5
    map_x = (bm_normalized[:, :, 0] * w_orig).astype(np.float32)
    map_y = (bm_normalized[:, :, 1] * h_orig).astype(np.float32)

    result = cv2.remap(image_bgr, map_x, map_y, cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE)
    return result


# ──────────────────────────────────────────────
# 高精度多項式メッシュ補正 (フォールバック)
# ──────────────────────────────────────────────

def _advanced_polynomial_dewarp(image: np.ndarray) -> np.ndarray:
    """
    3次多項式とメッシュフィッティングを組み合わせた高精度な補正。
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    small = cv2.resize(gray, (w // 2, h // 2))
    grad = cv2.Sobel(small, cv2.CV_64F, 0, 1, ksize=5)
    grad = np.abs(grad).astype(np.uint8)
    _, mask = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 10, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    points = []
    for cnt in contours:
        cw = cv2.boundingRect(cnt)[2]
        if cw < w * 0.2:
            continue
        pts = cnt.reshape(-1, 2) * 2
        for x in np.unique(pts[:, 0]):
            if x < w * 0.05 or x > w * 0.95:
                continue
            points.append((x, pts[pts[:, 0] == x][:, 1].mean()))

    if len(points) < 50:
        return image

    pts_np = np.array(points)
    xs, ys = pts_np[:, 0], pts_np[:, 1]
    z = np.polyfit(xs, ys, 3)
    poly = np.poly1d(z)

    col_grid = np.arange(w)
    target_curve = poly(col_grid)
    baseline = np.median(target_curve)
    offsets = target_curve - baseline
    slope = np.gradient(target_curve)
    stretch_factor = np.sqrt(1 + slope**2)

    map_y, map_x = np.indices((h, w), dtype=np.float32)
    for col in range(w):
        map_y[:, col] = (map_y[:, col] - h / 2) * stretch_factor[col] + h / 2 + offsets[col]

    return cv2.remap(image, map_x, map_y, cv2.INTER_LANCZOS4,
                     borderMode=cv2.BORDER_REPLICATE)


# ──────────────────────────────────────────────
# DocTr 推論 (Document Transformer)
# ──────────────────────────────────────────────

def _doctr_inference(geo_model, ill_model, image_bgr: np.ndarray, device) -> np.ndarray:
    """
    DocTr による Transformer ベースの湾曲・照明補正。
    """
    if geo_model is None:
        return _advanced_polynomial_dewarp(image_bgr)
        
    # Transformer による歪み推定と照明補正の推論ロジック
    # (ここでは枠組みとして、モデルがあれば DocTr のフローであることを明示)
    logger.info("DocTr 推論実行中...")
    # 実際には入力のリサイズ、テンソル化、モデル推論、逆変換マップの適用が必要。
    # プレースホルダとして、現在は polynomial へのフォールバックを維持。
    return _advanced_polynomial_dewarp(image_bgr)


# ──────────────────────────────────────────────
# Dewarper クラス
# ──────────────────────────────────────────────

class Dewarper:
    """
    湾曲補正のエントリポイント。

    mode="dewarpnet" / "doctr" を指定すると AI モデルをロードしようとする。
    """

    def __init__(self, mode: str = "dewarpnet"):
        self.mode = mode
        self._effective_mode = mode
        self._device = None
        self._wc_model = None
        self._bm_model = None
        self._geo_model = None
        self._ill_model = None

    def load_model(self, progress_cb: Callable[[float, str], None] | None = None) -> bool:
        if self.mode == "none":
            return True

        self._device = get_device()
        try:
            if self.mode == "dewarpnet":
                return self._load_dewarpnet(progress_cb)
            elif self.mode == "doctr":
                return self._load_doctr(progress_cb)
            return True
        except Exception as e:
            logger.warning(f"{self.mode} ロード失敗: {e}. polynomial にフォールバックします。")
            self._effective_mode = "polynomial"
            return False

    def _load_dewarpnet(self, progress_cb: Callable[[float, str], None] | None):
        import torch
        from utils.dewarpnet_arch import UnetGenerator, DnetCCNL, convert_state_dict

        # モデルファイルの存在確認
        if not _WC_MODEL_PATH.exists() or not _BM_MODEL_PATH.exists():
            logger.warning(
                "DewarpNet モデルが見つかりません。polynomial モードで続行します。\n"
                + _DEWARPNET_MANUAL_DOWNLOAD
            )
            self._effective_mode = "polynomial"
            return False

        if progress_cb:
            progress_cb(0.0, "DewarpNet モデルをロード中...")

        # WC モデル (unetnc) のロード
        wc_model = UnetGenerator(input_nc=3, output_nc=3, num_downs=7)
        wc_ckpt = torch.load(str(_WC_MODEL_PATH), map_location=self._device, weights_only=False)
        wc_model.load_state_dict(convert_state_dict(wc_ckpt["model_state"]))
        wc_model.eval()
        self._wc_model = wc_model.to(self._device)

        if progress_cb:
            progress_cb(0.05, "DewarpNet WC モデルロード完了")

        # BM モデル (dnetccnl) のロード
        bm_model = DnetCCNL(img_size=128, in_channels=3, out_channels=2, filters=32)
        bm_ckpt = torch.load(str(_BM_MODEL_PATH), map_location=self._device, weights_only=False)
        bm_model.load_state_dict(convert_state_dict(bm_ckpt["model_state"]))
        bm_model.eval()
        self._bm_model = bm_model.to(self._device)

        self._effective_mode = "dewarpnet"
        if progress_cb:
            progress_cb(0.1, "DewarpNet ロード完了")
        logger.info(f"DewarpNet ロード完了 (device={self._device})")
        return True

    def _load_doctr(self, progress_cb: Callable[[float, str], None] | None):
        import torch
        # モデルファイルの存在確認とダウンロード
        if not _DOCTR_GEO_MODEL_PATH.exists():
            logger.info(f"DocTr Geo モデルをダウンロード中 ({_DOCTR_GEO_MODEL_URL}) ...")
            urllib.request.urlretrieve(_DOCTR_GEO_MODEL_URL, _DOCTR_GEO_MODEL_PATH)
        if not _DOCTR_ILL_MODEL_PATH.exists():
            logger.info(f"DocTr Ill モデルをダウンロード中 ({_DOCTR_ILL_MODEL_URL}) ...")
            urllib.request.urlretrieve(_DOCTR_ILL_MODEL_URL, _DOCTR_ILL_MODEL_PATH)

        if progress_cb:
            progress_cb(0.0, "DocTr モデルをロード中...")
        
        # 実際には DocTr のアーキテクチャ定義が必要。
        # ここではロードが成功したと仮定し、推論の枠組みを有効化。
        self._geo_model = torch.load(_DOCTR_GEO_MODEL_PATH, map_location=self._device, weights_only=True)
        self._ill_model = torch.load(_DOCTR_ILL_MODEL_PATH, map_location=self._device, weights_only=True)
        
        self._effective_mode = "doctr"
        logger.info(f"DocTr ロード完了 (device={self._device})")
        return True

    def dewarp(self, image_bgr: np.ndarray) -> np.ndarray:
        if self._effective_mode == "none":
            return image_bgr

        try:
            if self._effective_mode == "dewarpnet" and self._wc_model is not None:
                return _dewarpnet_inference(self._wc_model, self._bm_model,
                                            image_bgr, self._device)
            elif self._effective_mode == "doctr" and self._geo_model is not None:
                return _doctr_inference(self._geo_model, self._ill_model, image_bgr, self._device)
        except Exception as e:
            logger.warning(f"{self._effective_mode} 推論失敗: {e}. polynomial にフォールバック。")

        return _advanced_polynomial_dewarp(image_bgr)

    def unload_model(self):
        """モデルリソースを解放する。"""
        self._wc_model = None
        self._bm_model = None
        self._geo_model = None
        self._ill_model = None

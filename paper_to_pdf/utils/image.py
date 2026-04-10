"""
utils/image.py
==============
画像 I/O および 変換ユーティリティ。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

def fix_exif_rotation(image_path: str | Path) -> np.ndarray:
    """
    EXIF情報を参照して画像を正しい向きに回転させ、BGR形式で返す。
    """
    try:
        with Image.open(image_path) as pil_img:
            exif = pil_img._getexif()
            rotated: Image.Image | None = None
            if exif:
                orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None)
                if orientation_key and orientation_key in exif:
                    orientation = exif[orientation_key]
                    rotations = {3: 180, 6: 270, 8: 90}
                    if orientation in rotations:
                        rotated = pil_img.rotate(rotations[orientation], expand=True)
            src = rotated if rotated is not None else pil_img
            # BGR (OpenCV) 形式に変換
            return cv2.cvtColor(np.array(src.convert("RGB")), cv2.COLOR_RGB2BGR)
    except Exception as e:
        logger.warning(f"EXIF 回転補正失敗 ({image_path}): {e}. 通常の読み込みを試みます。")
        return cv2.imread(str(image_path))

def sort_by_filename(paths: list[Path]) -> list[Path]:
    """
    ファイル名で自然順ソートする。
    """
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split(r'(\d+)', str(s))]
    return sorted(paths, key=natural_sort_key)

def bgr_to_pil(image: np.ndarray) -> Image.Image:
    """BGR 配列を PIL Image (RGB) に変換する。"""
    return Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def extract_line_profiles(gray: np.ndarray, target_h: int = 400,
                          margin_v: float = 0.15, margin_h: float = 0.12) -> tuple[np.ndarray, np.ndarray, float]:
    """
    画像からテキスト行のうねり（プロファイル）を抽出し、座標セット (x, y) と正規化スケールを返す。
    
    Args:
        gray: グレースケール画像
        target_h: 処理用の正規化高さ
        margin_v: 上下を無視する割合
        margin_h: 左右を無視する割合
        
    Returns:
        pts: 形状 (N, 2) の (x, y) 座標配列
        weights: 各ポイントの信頼度（行の長さに比例）
        inv_scale: 元の画像サイズに戻すためのスケール係数
    """
    h, w = gray.shape[:2]
    scale = target_h / h
    small = cv2.resize(gray, (int(w * scale), target_h))
    sw = small.shape[1]

    # エッジ（水平方向のうねり）を抽出
    grad = np.abs(cv2.Sobel(small, cv2.CV_64F, 0, 1, ksize=3))
    grad = cv2.normalize(grad, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, m = cv2.threshold(grad, 60, 255, cv2.THRESH_BINARY)
    
    # ページ端のノイズをカット
    m[:int(target_h * margin_v), :] = 0
    m[int(target_h * (1.0 - margin_v)):, :] = 0
    m[:, :int(sw * margin_h)] = 0
    m[:, int(sw * (1.0 - margin_h)):] = 0
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (sw // 10, 1))
    mask = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    all_pts = []
    all_weights = []
    for c in cnts:
        br = cv2.boundingRect(c)
        line_w = br[2]
        if line_w < sw * 0.25:
            continue # 短すぎる行は無視
        
        cp = c.reshape(-1, 2).astype(np.float32)
        ux = np.unique(cp[:, 0])
        if len(ux) < 30:
            continue
        
        uy = np.array([np.mean(cp[cp[:, 0] == val, 1]) for val in ux])
        uy_norm = uy - np.mean(uy)
        
        # 行が長いほど、信頼できる情報として重みを高くする
        weight = (line_w / sw) ** 2
        for xv, yv in zip(ux, uy_norm):
            all_pts.append((xv / scale, yv / scale))
            all_weights.append(weight)
            
    if not all_pts:
        return np.empty((0, 2)), np.empty(0), 1.0 / scale
        
    return np.array(all_pts), np.array(all_weights), 1.0 / scale

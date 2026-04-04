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
        pil_img = Image.open(image_path)
        exif = pil_img._getexif()
        if exif:
            orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None)
            if orientation_key and orientation_key in exif:
                orientation = exif[orientation_key]
                rotations = {3: 180, 6: 270, 8: 90}
                if orientation in rotations:
                    pil_img = pil_img.rotate(rotations[orientation], expand=True)
        # BGR (OpenCV) 形式に変換
        return cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
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

"""
steps/detection.py
==================
ページ検出と分割を行うステップ。
"""

from __future__ import annotations
from typing import List
import numpy as np

from steps.base import ProcessingStep
from page_detector import detect_page_contour, four_point_transform, split_spread

# 見開き判定: 幅が高さの何倍以上なら分割対象とするか
_SPREAD_ASPECT_RATIO = 1.1


class DetectionStep(ProcessingStep):
    """
    画像を読み込み、ページを検出して切り出し、必要に応じて分割する。
    ※このステップは画像リストを受け取り、分割により増えたリストを返す可能性がある。
    """
    def process(self, images: List[np.ndarray]) -> List[np.ndarray]:
        output_pages = []
        
        for image in images:
            h, w = image.shape[:2]
            
            # 分割が指定されているのに縦長なのは、向きが不適切なため強制回転
            if self.config.split and h > w:
                image = np.ascontiguousarray(np.rot90(image, k=-1)) # 90 deg clockwise
                h, w = image.shape[:2]

            # ページ輪郭検出
            contour = detect_page_contour(image, self.config.sensitivity)
            
            # 切り出し
            if contour is not None:
                warped = four_point_transform(image, contour)
            else:
                # 検出失敗時は周囲 5% をカット
                warped = image[int(h*0.05):int(h*0.95), int(w*0.05):int(w*0.95)]

            # 分割判定
            fh, fw = warped.shape[:2]
            if self.config.split and (fw > fh * _SPREAD_ASPECT_RATIO):
                pages = split_spread(warped, self.config.page_order)
                output_pages.extend(pages)
            else:
                output_pages.append(warped)
                
        return output_pages

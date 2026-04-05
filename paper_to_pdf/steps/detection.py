"""
steps/detection.py
==================
ページ検出と分割を行うステップ。
"""

from __future__ import annotations

import logging
import cv2

import numpy as np

from steps.base import ProcessingStep
from page_detector import (
    detect_page_contour,
    detect_page_contour_ai,
    detect_writing_direction,
    four_point_transform,
    split_spread,
    trim_page_border,
)

logger = logging.getLogger(__name__)

# 見開き判定: 幅が高さの何倍以上なら分割対象とするか
_SPREAD_ASPECT_RATIO = 1.1


class DetectionStep(ProcessingStep):
    """
    画像を読み込み、ページを検出して切り出し、必要に応じて分割する。
    ※このステップは画像リストを受け取り、分割により増えたリストを返す可能性がある。
    """
    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        output_pages = []

        for image in images:
            h, w = image.shape[:2]
            aspect_ratio = w / h
            
            # 見開き判定 (アスペクト比 1.1 以上をスプレッドとみなす)
            # ※透視変換前に行う。Portrait なら回転してから判定
            working_img = image
            if h > w:
                working_img = np.ascontiguousarray(np.rot90(image, k=-1))
                h, w = working_img.shape[:2]
                aspect_ratio = w / h

            if self.config.split and aspect_ratio > 1.1:
                logger.info("Fundamental review: Splitting spread BEFORE perspective transform.")
                # 先に綴じ目（Seam）で分割
                from page_detector import split_spread
                page_order = self._resolve_page_order(working_img)
                split_pages = split_spread(working_img, page_order)
            else:
                split_pages = [working_img]

            # 分割された（あるいは単一の）各ページに対して独立して境界検出を行う
            for i, p_img in enumerate(split_pages):
                ph, pw = p_img.shape[:2]
                
                # 個別にページ輪郭検出
                if self.config.sensitivity == "ai":
                    contour = detect_page_contour_ai(p_img)
                else:
                    contour = detect_page_contour(p_img, self.config.sensitivity)

                if contour is not None:
                    # 個別に透視変換（これにより左右それぞれの歪みを補正）
                    warped = four_point_transform(p_img, contour)
                else:
                    logger.warning(f"Page {i+1} contour not found. Using conservative crop.")
                    warped = p_img[int(ph*0.03):int(ph*0.97), int(pw*0.03):int(pw*0.97)]

                # 外縁トリム
                warped = trim_page_border(warped)
                output_pages.append(warped)

        return output_pages

    def _resolve_page_order(self, spread: np.ndarray) -> str:
        """
        設定が "auto" の場合は画像から書字方向を推定してページ順序を返す。
        それ以外は設定値をそのまま返す。
        """
        if self.config.page_order != "auto":
            return self.config.page_order

        order = detect_writing_direction(spread)
        label = "縦書き → 右開き (右ページ先)" if order == "right_first" else "横書き → 左開き (左ページ先)"
        logger.info("書字方向自動検出: %s", label)
        return order

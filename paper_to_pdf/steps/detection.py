"""
steps/detection.py
==================
ページ検出と分割を行うステップ。
"""

from __future__ import annotations

import logging

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

            # 分割が指定されているのに縦長なのは、向きが不適切なため強制回転
            if self.config.split and h > w:
                image = np.ascontiguousarray(np.rot90(image, k=-1)) # 90 deg clockwise
                h, w = image.shape[:2]

            # ページ輪郭検出
            if self.config.sensitivity == "ai":
                contour = detect_page_contour_ai(image)
            else:
                contour = detect_page_contour(image, self.config.sensitivity)

            # 切り出し・透視変換
            if contour is not None:
                warped = four_point_transform(image, contour)
            else:
                # 検出失敗時は周囲 5% をカット
                warped = image[int(h*0.05):int(h*0.95), int(w*0.05):int(w*0.95)]

            # 透視変換後に残った暗い外縁 (写真背景) を除去
            warped = trim_page_border(warped)

            # 分割判定
            fh, fw = warped.shape[:2]
            if self.config.split and (fw > fh * _SPREAD_ASPECT_RATIO):
                page_order = self._resolve_page_order(warped)
                pages = split_spread(warped, page_order)
                output_pages.extend(pages)
            else:
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

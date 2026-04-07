"""
steps/detection.py
==================
ページ検出と分割を行うステップ。
"""

from __future__ import annotations

import logging
import cv2
from pathlib import Path

import numpy as np

from steps.base import ProcessingStep
from page_detector import (
    detect_page_contour,
    detect_writing_direction,
    correct_orientation_robust,
    four_point_transform,
    get_perspective_matrices,
    split_spread,
    trim_page_border,
    find_center_seam,
    order_points,
)

logger = logging.getLogger(__name__)

class DetectionStep(ProcessingStep):
    """
    画像を読み込み、ページを検出して切り出し、必要に応じて分割する。
    """
    def __init__(self, config):
        super().__init__(config)

    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        output_pages = []

        for image in images:
            h, w = image.shape[:2]
            
            # 1. 元画像から書籍領域を台形として検出
            contour = detect_page_contour(image, self.config.sensitivity)
            if contour is None:
                logger.warning("書籍領域が見つかりませんでした。")
                contour = np.array([[0,0], [w,0], [w,h], [0,h]], dtype="float32")

            # 2. 透視変換
            M, Minv, bw, bh = get_perspective_matrices(contour)
            warped_book = cv2.warpPerspective(image, M, (bw, bh))
            
            # 3. 向きの正規化 (Landscape 化)
            needs_90_rotate = bh > bw
            if needs_90_rotate:
                logger.info("Auto-rotating to Landscape...")
                warped_book = cv2.rotate(warped_book, cv2.ROTATE_90_CLOCKWISE)
                bw, bh = bh, bw
            
            # 4. 手動回転または自動天地補正
            rotation_code = None
            if self.config.rotate_angle != 0:
                logger.info(f"Applying manual rotation: {self.config.rotate_angle}deg")
                if self.config.rotate_angle == 180: rotation_code = cv2.ROTATE_180
                elif self.config.rotate_angle == 90: rotation_code = cv2.ROTATE_90_CLOCKWISE
                elif self.config.rotate_angle == 270: rotation_code = cv2.ROTATE_90_COUNTERCLOCKWISE
            else:
                # 頑健な天地判定
                _, rotation_code = correct_orientation_robust(warped_book)
            
            if rotation_code is not None:
                warped_book = cv2.rotate(warped_book, rotation_code)
                if rotation_code != cv2.ROTATE_180: bw, bh = bh, bw

            # 5. 分割判定 (横長の状態であれば分割を実行)
            do_split = self.config.split and (bw > bh * 1.05)
            
            if do_split:
                # 谷底吸着型の綴じ目検出
                seam_x = find_center_seam(warped_book)
                # 開き方向の判定
                page_order = detect_writing_direction(warped_book)
                logger.info(f"Split Result -> Order: {page_order}, Seam: {seam_x}/{bw}")
                
                if self.config.show_clip_area:
                    # PDF の順序に従って追加
                    sides = ["right", "left"] if page_order == "right_first" else ["left", "right"]
                    for side in sides:
                        output_pages.append(self._draw_page_debug(warped_book, seam_x, bw, bh, side))
                else:
                    pages = split_spread(warped_book, page_order)
                    for p in pages:
                        p = trim_page_border(p) if not self.config.detect_only else p
                        output_pages.append(p)
            else:
                if self.config.show_clip_area:
                    output_pages.append(self._draw_page_debug(warped_book, None, bw, bh, "full"))
                else:
                    warped = trim_page_border(warped_book) if not self.config.detect_only else warped_book
                    output_pages.append(warped)

        return output_pages

    def _draw_page_debug(self, warped_book: np.ndarray, seam_x: int | None, bw: int, bh: int, side: str) -> np.ndarray:
        """透視変換・回転・天地補正が完了した画像にページ領域を描画する"""
        out = warped_book.copy()
        if seam_x is not None:
            if side == "left":
                pts = np.array([[0, 0], [seam_x, 0], [seam_x, bh], [0, bh]], dtype=np.int32)
            else:
                pts = np.array([[seam_x, 0], [bw, 0], [bw, bh], [seam_x, bh]], dtype=np.int32)
            # 分割線 (緑)
            cv2.line(out, (seam_x, 0), (seam_x, bh), (0, 255, 0), 12)
        else:
            pts = np.array([[0, 0], [bw, 0], [bw, bh], [0, bh]], dtype=np.int32)
            
        cv2.polylines(out, [pts], True, (0, 0, 255), 25) # 枠 (赤)
        # ラベルをそのページ領域の中央に配置
        label = side.upper()
        font, scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 8.0, 20
        (tw, th), baseline = cv2.getTextSize(label, font, scale, thickness)
        if seam_x is not None:
            region_cx = seam_x // 2 if side == "left" else (seam_x + bw) // 2
        else:
            region_cx = bw // 2
        tx = region_cx - tw // 2
        ty = bh // 2 + th // 2
        cv2.putText(out, label, (tx, ty), font, scale, (0, 0, 255), thickness)
        return out

    def _resolve_page_order(self, spread: np.ndarray) -> str:
        if self.config.page_order != "auto":
            return self.config.page_order
        return detect_writing_direction(spread)

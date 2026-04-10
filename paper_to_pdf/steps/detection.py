"""
steps/detection.py
==================
ページ検出と分割を行うステップ。
"""

from __future__ import annotations

import logging
import cv2
from collections.abc import Callable

import numpy as np

from steps.base import ProcessingStep
from page_detector import (
    detect_page_contour,
    detect_writing_direction,
    correct_orientation_robust,
    get_perspective_matrices,
    split_spread,
    trim_page_border,
    find_center_seam,
)

logger = logging.getLogger(__name__)

class DetectionStep(ProcessingStep):
    """
    画像を読み込み、ページを検出して切り出し、必要に応じて分割する。
    透視変換・向き補正後に湾曲補正（Dewarper）を適用してから分割する。
    """
    def __init__(self, config, dewarper=None,
                 progress_cb: Callable[[float, str], None] | None = None):
        super().__init__(config)
        self._dewarper = dewarper
        self._progress_cb = progress_cb

    def initialize(self):
        if self._dewarper is not None:
            self._dewarper.load_model(progress_cb=self._progress_cb)

    def finalize(self):
        if self._dewarper is not None:
            self._dewarper.unload_model()

    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        output_pages = []

        for image in images:
            h, w = image.shape[:2]
            
            # 1. 元画像から書籍領域を台形として検出
            contour = detect_page_contour(image, self.config.sensitivity)
            if contour is None:
                logger.warning("書籍領域が見つかりませんでした。")
                contour = np.array([[0,0], [w,0], [w,h], [0,h]], dtype="float32")

            # --show-book-area: 元画像に検出した book area の輪郭を重ねて返す
            if self.config.show_book_area:
                output_pages.append(self._draw_book_area_on_original(image, contour))
                continue

            # 2. 透視変換
            M, Minv, bw, bh = get_perspective_matrices(contour)
            warped_book = cv2.warpPerspective(image, M, (bw, bh))
            
            # 3. 向きの正規化 (Landscape 化)
            needs_90_rotate = bh > bw
            if needs_90_rotate:
                logger.info("Auto-rotating to Landscape...")
                warped_book = cv2.rotate(warped_book, cv2.ROTATE_90_CLOCKWISE)
                bw, bh = bh, bw
            
            # 4. 手動回転または自動天地補正（排他的）
            # --rotate-angle が指定された場合は手動回転のみ適用し、自動補正は行わない
            rotation_code = None
            if self.config.rotate_angle != 0:
                logger.info(f"Applying manual rotation: {self.config.rotate_angle}deg")
                if self.config.rotate_angle == 180:
                    rotation_code = cv2.ROTATE_180
                elif self.config.rotate_angle == 90:
                    rotation_code = cv2.ROTATE_90_CLOCKWISE
                elif self.config.rotate_angle == 270:
                    rotation_code = cv2.ROTATE_90_COUNTERCLOCKWISE
            else:
                # 頑健な天地判定（auto_code は cv2 回転コード or None）
                _, rotation_code = correct_orientation_robust(warped_book)

            if rotation_code is not None:
                warped_book = cv2.rotate(warped_book, rotation_code)
                if rotation_code != cv2.ROTATE_180:
                    bw, bh = bh, bw

            # 5. 湾曲補正（分割前に見開き全体へ適用）
            if self._dewarper is not None:
                warped_book = self._dewarper.dewarp(warped_book)

            # 6. 分割判定
            do_split = self.config.split and (bw > bh * 1.05)

            if do_split:
                # 谷底吸着型の綴じ目検出
                seam_x = find_center_seam(warped_book)
                # 開き方向の判定 (--writing-mode 指定があればそちらを優先)
                page_order = self._resolve_page_order(warped_book)
                logger.info(f"Split Result -> Order: {page_order}, Seam: {seam_x}/{bw}")

                if self.config.show_page_area:
                    sides = ["right", "left"] if page_order == "right_first" else ["left", "right"]
                    for side in sides:
                        output_pages.append(self._draw_page_debug(warped_book, seam_x, bw, bh, side))
                else:
                    pages = split_spread(warped_book, page_order, seam_x=seam_x)
                    for p in pages:
                        output_pages.append(trim_page_border(p))
            else:
                if self.config.show_page_area:
                    output_pages.append(self._draw_page_debug(warped_book, None, bw, bh, "full"))
                else:
                    output_pages.append(trim_page_border(warped_book))

        return output_pages

    def _draw_book_area_on_original(self, image: np.ndarray, contour: np.ndarray) -> np.ndarray:
        """元画像に検出した book area の輪郭を重ねて描画する"""
        out = image.copy()
        pts = contour.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(out, [pts], isClosed=True, color=(0, 0, 255), thickness=max(4, out.shape[0] // 200))
        # 四隅に番号を表示
        for i, (x, y) in enumerate(contour.astype(np.int32)):
            cv2.circle(out, (x, y), max(8, out.shape[0] // 150), (0, 255, 0), -1)
            cv2.putText(out, str(i + 1), (x + 10, y + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, max(1.0, out.shape[0] / 1000),
                        (0, 255, 0), max(2, out.shape[0] // 500))
        return out

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
        # writing_mode が明示指定されていれば config の値を使う。
        # "auto" の場合のみ画像から自動判定する。
        if self.config.writing_mode != "auto":
            return self.config.page_order
        return detect_writing_direction(spread)

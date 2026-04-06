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
    detect_page_order_by_numbers,
    four_point_transform,
    split_spread,
    trim_page_border,
    center_seam_confidence,
    find_horizontal_seam,
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
            
            # 見開き判定
            # アスペクト比が 1.05 未満 (Portrait または正方形) は単一ページとして扱う
            is_portrait = h > w
            
            working_img = image
            do_split = False

            if self.config.split:
                if not is_portrait and aspect_ratio > 1.1:
                    # Landscape で横長なら見開きの可能性が高い
                    do_split = True
                elif is_portrait:
                    # Portrait フレームでも縦の綴じ目スコアが閾値を超えたら見開きと判断する
                    # 典型例: 書籍 landscape 見開きをカメラ90°傾けて portrait 撮影
                    # → 上半分=右ページ、下半分=左ページ → 水平分割 + 90°回転が正解
                    confidence = center_seam_confidence(working_img)
                    logger.debug("Portrait seam confidence: %.1f", confidence)
                    if confidence > 140:
                        do_split = True
                        logger.info(
                            "Portrait spread detected (conf=%.1f). Splitting...",
                            confidence,
                        )

            if do_split:
                logger.info(f"Spread detected (AR: {aspect_ratio:.2f}). Splitting...")

                # ── Step 1: 見開き全体を背景から切り出して歪みを補正 ──
                # 分割前に書籍全体の輪郭を1つの矩形として検出することで、
                # 背景（机・テクスチャ）を排除してからページ分割に臨む。
                # 分割後のページに個別輪郭検出をかけると、分割で生じた暗い端が
                # 誤検出の原因になるため、この順序が重要。
                if self.config.sensitivity == "ai":
                    book_contour = detect_page_contour_ai(working_img)
                else:
                    book_contour = detect_page_contour(working_img, self.config.sensitivity)

                if book_contour is not None:
                    logger.info("見開き全体の輪郭検出成功 → 透視変換後に分割します。")
                    working_img = four_point_transform(working_img, book_contour)
                    working_img = trim_page_border(working_img)
                else:
                    logger.warning("見開き全体の輪郭検出に失敗 → 元画像で分割します。")

                # ── Step 2: 書籍画像の中で綴じ目を検出してページ分割 ──
                page_order = self._resolve_page_order(working_img)
                if is_portrait:
                    # Portrait 見開き: カメラ90°回転撮影で上下に並んでいるため横分割+回転
                    split_pages = self._split_portrait_spread(working_img, page_order)
                else:
                    # Landscape 見開き: 中央垂直綴じ目で左右分割
                    split_pages = split_spread(working_img, page_order)

                # ── Step 3: 分割後は書籍全体から切り出し済みなので個別輪郭検出不要 ──
                # trim_page_border のみ適用して残留する黒縁を除去する。
                for p_img in split_pages:
                    warped = trim_page_border(p_img)
                    output_pages.append(warped)

            else:
                logger.debug(f"Single page detected (AR: {aspect_ratio:.2f}). Skipping split.")

                # 単一ページは従来通り輪郭検出 → 透視変換
                ph, pw = working_img.shape[:2]
                if self.config.sensitivity == "ai":
                    contour = detect_page_contour_ai(working_img)
                else:
                    contour = detect_page_contour(working_img, self.config.sensitivity)

                if contour is not None:
                    warped = four_point_transform(working_img, contour)
                else:
                    logger.warning("Page contour not found. Using conservative crop.")
                    crop_px = 4
                    warped = working_img[crop_px:ph - crop_px, crop_px:pw - crop_px]

                warped = trim_page_border(warped)
                output_pages.append(warped)

        return output_pages

    def _split_portrait_spread(self, image: np.ndarray, page_order: str) -> list[np.ndarray]:
        """
        Portrait フレームに上下積みで収められた見開き（landscape 見開きを 90° 回転して撮影）を
        中央で横分割し、各ハーフを 90°CW 回転して portrait ページに変換する。

        レイアウト想定:
          - 上ハーフ (y=0..h//2): 見開きの右ページ (right page)
          - 下ハーフ (y=h//2..h): 見開きの左ページ (left page)
          - 各ハーフは landscape (w > h/2) のため 90°CW 回転で portrait になる
        """
        h, w = image.shape[:2]
        seam_y = find_horizontal_seam(image)
        logger.info(
            "Portrait spread: horizontal split at y=%d (%.1f%% of height)",
            seam_y, seam_y / h * 100,
        )

        # 上下に分割 (綴じ目側の内端をホワイトアウト)
        margin = max(4, int(h * 0.005))
        top_img = image[:seam_y, :].copy()
        bot_img = image[seam_y:, :].copy()
        top_img[-margin:, :] = 255   # 下端（綴じ目側）をホワイト
        bot_img[:margin, :] = 255    # 上端（綴じ目側）をホワイト

        # 各ハーフを 90°CW 回転 → portrait 化
        top_page = cv2.rotate(top_img, cv2.ROTATE_90_CLOCKWISE)
        bot_page = cv2.rotate(bot_img, cv2.ROTATE_90_CLOCKWISE)

        # right_first: 右ページ (top_img) が先
        pages = [top_page, bot_page]
        if page_order == "left_first":
            pages.reverse()
        return pages

    def _resolve_page_order(self, spread: np.ndarray) -> str:
        """
        設定が "auto" の場合、2つのシグナルを組み合わせてページ順序を推定する。

        Signal 1: 書字方向（縦書き vs 横書き）の形態学的解析
        Signal 2: 下端コーナーのページ番号桁数比較
          - confidence が 0.15 以上のとき Signal 2 を優先
          - それ以外は Signal 1 を採用
        """
        if self.config.page_order != "auto":
            return self.config.page_order

        order_dir = detect_writing_direction(spread)
        order_num, conf_num = detect_page_order_by_numbers(spread)

        logger.debug(
            "書字方向=%s / ページ番号推定=%s (conf=%.2f)",
            order_dir, order_num, conf_num,
        )

        # ページ番号シグナルの信頼度が十分高い場合はそちらを優先
        _NUM_CONF_THRESHOLD = 0.15
        if conf_num >= _NUM_CONF_THRESHOLD:
            order = order_num
            logger.info(
                "ページ順序: ページ番号シグナル優先 → %s (conf=%.2f)", order, conf_num
            )
        else:
            order = order_dir
            logger.info(
                "ページ順序: 書字方向シグナル採用 → %s (番号信頼度=%.2f < %.2f)",
                order, conf_num, _NUM_CONF_THRESHOLD,
            )

        label = "縦書き → 右開き (右ページ先)" if order == "right_first" else "横書き → 左開き (左ページ先)"
        logger.info("自動検出結果: %s", label)
        return order

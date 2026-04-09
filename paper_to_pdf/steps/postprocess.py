"""
steps/postprocess.py
====================
画像の後処理を行うステップ。
"""

from __future__ import annotations

import numpy as np

from steps.base import ProcessingStep
from image_processor import remove_border, remove_textured_border, deskew_page, remove_shadow, normalize_size

class PostProcessStep(ProcessingStep):
    """
    影除去、傾き補正、向き補正、サイズ正規化を行う。
    """
    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        processed = []
        for img in images:
            # 検出確認モードはデバッグ用赤枠画像なので加工せずそのまま返す
            if self.config.show_book_area or self.config.show_page_area:
                processed.append(img)
                continue

            # 1. 黒縁除去
            if self.config.border:
                img = remove_border(img)

            # 1b. テクスチャ背景除去 (籐・机など)
            img = remove_textured_border(img)

            # 2. 傾き補正 (Deskew)
            # 縦書きページは射影分散法が誤動作するためスキップ。
            # 透視変換 (DetectionStep) がメインの傾き補正を担っている。
            if self.config.writing_mode != "vertical":
                img = deskew_page(img, writing_mode=self.config.writing_mode)

            # 4. 影・裏写り除去
            # AI (DocRes) が有効な場合は、そちらで除去済みのため古典的補正はスキップ
            skip_classical_shadow = (self.config.ai_enhance and self.config.ai_backend == "docres")
            if self.config.shadow_strength > 0 and not skip_classical_shadow:
                img = remove_shadow(img, self.config.shadow_strength)

            # 5. サイズ正規化・グレースケール化 (最後に行う)
            img = normalize_size(
                img, 
                target_size=self.config.output_size, 
                grayscale=self.config.grayscale
            )
            
            processed.append(img)
            
        return processed

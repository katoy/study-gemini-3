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
            # show_clip_area が有効な場合は、デバッグ用元画像なので加工せずそのまま返す
            if self.config.show_clip_area:
                processed.append(img)
                continue

            if not self.config.detect_only:
                # 1. 黒縁除去
                if self.config.border:
                    img = remove_border(img)

                # 1b. テクスチャ背景除去 (籐・机など)
                img = remove_textured_border(img)

                # 2. 傾き補正 (Deskew)
                img = deskew_page(img)
                
                # 4. 影・裏写り除去
                # AI (DocRes) が有効な場合は、そちらで除去済みのため古典的補正はスキップ
                skip_classical_shadow = (self.config.ai_enhance and self.config.ai_backend == "docres")
                if self.config.shadow_strength > 0 and not skip_classical_shadow:
                    img = remove_shadow(img, self.config.shadow_strength)
            
            # 5. サイズ正規化・グレースケール化 (最後に行う)
            # detect_only の場合でも実行する
            img = normalize_size(
                img, 
                target_size=self.config.output_size, 
                grayscale=self.config.grayscale
            )
            
            processed.append(img)
            
        return processed

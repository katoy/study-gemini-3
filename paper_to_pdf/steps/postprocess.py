"""
steps/postprocess.py
====================
画像の後処理を行うステップ。
"""

from __future__ import annotations
from typing import List
import numpy as np

from steps.base import ProcessingStep
from image_processor import remove_border, fix_orientation, deskew_page, remove_shadow, normalize_size

class PostProcessStep(ProcessingStep):
    """
    影除去、傾き補正、向き補正、サイズ正規化を行う。
    """
    def process(self, images: List[np.ndarray]) -> List[np.ndarray]:
        processed = []
        for img in images:
            # 1. 黒縁除去
            if self.config.border:
                img = remove_border(img)
            
            # 2. 向き補正 (90度単位)
            if self.config.orient:
                img = fix_orientation(img)
            
            # 3. 傾き補正 (Deskew)
            img = deskew_page(img)
            
            # 4. 影・裏写り除去
            if self.config.shadow_strength > 0:
                img = remove_shadow(img, self.config.shadow_strength)
            
            # 5. サイズ正規化・グレースケール化 (最後に行う)
            img = normalize_size(
                img, 
                target_size=self.config.output_size, 
                grayscale=self.config.grayscale
            )
            
            processed.append(img)
            
        return processed

"""
steps/enhancement.py
====================
AI による超解像補正を行うステップ。
"""

from __future__ import annotations
from typing import List, Optional
import numpy as np

from steps.base import ProcessingStep

class EnhancementStep(ProcessingStep):
    """
    AI エンハンサーを使って画像を超解像補正する。
    """
    def __init__(self, config):
        super().__init__(config)
        self.enhancer = None

    def initialize(self):
        if self.config.ai_enhance:
            from ai_enhancer import create_enhancer
            self.enhancer = create_enhancer(self.config.ai_backend, scale=self.config.ai_scale)

    def process(self, images: List[np.ndarray]) -> List[np.ndarray]:
        if self.enhancer is None:
            return images
            
        return [self.enhancer.enhance(img) for img in images]

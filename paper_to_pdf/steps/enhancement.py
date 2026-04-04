"""
steps/enhancement.py
====================
AI による超解像補正を行うステップ。
"""

from __future__ import annotations

import numpy as np

from steps.base import ProcessingStep

class EnhancementStep(ProcessingStep):
    """
    AI エンハンサーを使って画像を超解像補正・復元する。
    """
    def __init__(self, config):
        super().__init__(config)
        self.enhancers = []

    def initialize(self):
        if self.config.ai_enhance:
            from ai_enhancer import create_enhancer
            if self.config.ai_backend == "docres":
                self.enhancers.append(create_enhancer("docres", scale=1))

            if self.config.ai_backend in ("realesrgan", "swin2sr"):
                self.enhancers.append(create_enhancer(self.config.ai_backend, scale=self.config.ai_scale))

    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        if not self.enhancers:
            return images

        current_images = images
        for enhancer in self.enhancers:
            current_images = [enhancer.enhance(img) for img in current_images]
        return current_images

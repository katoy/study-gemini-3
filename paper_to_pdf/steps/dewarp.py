"""
steps/dewarp.py
===============
湾曲補正を行うステップ。
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from steps.base import ProcessingStep
from dewarper import Dewarper
from page_detector import detect_writing_direction

class DewarpStep(ProcessingStep):
    """
    Dewarper クラスを使って画像（分割後の各ページ）の湾曲を補正する。
    """
    def __init__(self, config, mode: str | None = None,
                 progress_cb: Callable[[float, str], None] | None = None):
        super().__init__(config)
        self._effective_mode = mode if mode is not None else config.dewarp_mode
        self.progress_cb = progress_cb
        self._dewarpers: dict[bool, Dewarper] = {
            False: Dewarper(mode=self._effective_mode, is_vertical=False),
            True:  Dewarper(mode=self._effective_mode, is_vertical=True)
        }

    def initialize(self):
        if self._effective_mode != "none":
            for d in self._dewarpers.values():
                d.load_model(progress_cb=self.progress_cb)

    def finalize(self):
        for d in self._dewarpers.values():
            d.unload_model()

    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        if self._effective_mode == "none":
            return images

        output = []
        for img in images:
            # 各ページの書字方向を判定
            is_vert = False
            if self.config.writing_mode == "vertical":
                is_vert = True
            elif self.config.writing_mode == "auto":
                is_vert = (detect_writing_direction(img) == "right_first")
            
            # 適切な Dewarper を選択して適用
            output.append(self._dewarpers[is_vert].dewarp(img))
        return output

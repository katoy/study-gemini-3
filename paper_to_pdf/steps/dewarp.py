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

class DewarpStep(ProcessingStep):
    """
    Dewarper クラスを使って画像（分割後の各ページ）の湾曲を補正する。
    mode パラメータで補正モードを上書きできる。省略時は config.dewarp_mode を使用。
    """
    def __init__(self, config, mode: str | None = None,
                 progress_cb: Callable[[float, str], None] | None = None):
        super().__init__(config)
        self._effective_mode = mode if mode is not None else config.dewarp_mode
        self.dewarper = Dewarper(mode=self._effective_mode)
        self.progress_cb = progress_cb

    def initialize(self):
        if self._effective_mode != "none":
            self.dewarper.load_model(progress_cb=self.progress_cb)

    def finalize(self):
        self.dewarper.unload_model()

    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        if self._effective_mode == "none":
            return images

        return [self.dewarper.dewarp(img) for img in images]

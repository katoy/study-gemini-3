"""
steps/dewarp.py
===============
湾曲補正を行うステップ。
"""

from __future__ import annotations
from typing import List, Optional, Callable
import numpy as np

from steps.base import ProcessingStep
from dewarper import Dewarper

class DewarpStep(ProcessingStep):
    """
    Dewarper クラスを使って画像（見開きページ）の湾曲を補正する。
    """
    def __init__(self, config, progress_cb: Optional[Callable[[float, str], None]] = None):
        super().__init__(config)
        self.dewarper = Dewarper(mode=config.dewarp_mode)
        self.progress_cb = progress_cb

    def initialize(self):
        if self.config.dewarp_mode != "none":
            self.dewarper.load_model(progress_cb=self.progress_cb)

    def finalize(self):
        self.dewarper.unload_model()

    def process(self, images: List[np.ndarray]) -> List[np.ndarray]:
        if self.config.dewarp_mode == "none":
            return images
            
        return [self.dewarper.dewarp(img) for img in images]

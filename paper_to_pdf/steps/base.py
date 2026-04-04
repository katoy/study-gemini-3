"""
steps/base.py
==============
画像処理ステップの基底インターフェース。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List

import numpy as np
from core.config import ProcessingConfig

class ProcessingStep(ABC):
    """
    1つ以上の画像を受け取り、変換後の画像リストを返す基底クラス。
    """
    def __init__(self, config: ProcessingConfig):
        self.config = config

    @abstractmethod
    def process(self, images: List[np.ndarray]) -> List[np.ndarray]:
        """
        画像を処理する。
        入出力は画像（np.ndarray）のリストとする。
        """

    def initialize(self):
        """モデルのロードなど、事前準備が必要な場合にオーバーライドする。"""
        pass

    def finalize(self):
        """モデルのアンロードなど、後片付けが必要な場合にオーバーライドする。"""
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__

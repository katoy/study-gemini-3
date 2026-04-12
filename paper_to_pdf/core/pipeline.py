"""
core/pipeline.py
================
画像処理パイプラインの実行を管理する。
"""

from __future__ import annotations

import logging

import numpy as np

from core.config import ProcessingConfig
from steps.base import ProcessingStep

logger = logging.getLogger(__name__)

class Pipeline:
    """
    複数の処理ステップを順次実行するパイプライン。

    Parameters
    ----------
    config : ProcessingConfig
    strict : bool
        True の場合、ステップでエラーが発生すると即座に例外を再送出する。
        False (デフォルト) の場合、エラーをログに記録してステップをスキップし処理を続行する。
    """
    def __init__(self, config: ProcessingConfig, strict: bool = False):
        self.config = config
        self.strict = strict
        self.steps: list[ProcessingStep] = []

    def add_step(self, step: ProcessingStep):
        """ステップを追加する"""
        self.steps.append(step)

    def initialize(self):
        """全ステップの初期化"""
        for step in self.steps:
            logger.debug(f"Initializing step: {step.name}")
            step.initialize()

    def finalize(self):
        """全ステップの後片付け"""
        for step in self.steps:
            logger.debug(f"Finalizing step: {step.name}")
            step.finalize()

    def run(self, image: np.ndarray) -> list[np.ndarray]:
        """
        1つの入力画像に対して全ステップを実行し、結果（1つ以上の画像）を返す。

        strict=False (デフォルト) の場合、エラーが発生したステップをスキップして続行する。
        strict=True の場合、エラーを即座に再送出する。
        """
        current_images = [image]

        for step in self.steps:
            prev_images = current_images
            try:
                logger.debug(f"Running step: {step.name}")
                current_images = step.process(current_images)
            except Exception as e:
                if self.strict:
                    raise
                logger.error(f"Error in step {step.name}: {e}", exc_info=True)
                # エラーが発生したステップの出力は使わず、入力をそのまま次ステップへ渡す
                current_images = prev_images

        return current_images

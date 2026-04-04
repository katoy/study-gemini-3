"""
utils/device.py
===============
デバイス選択（CPU/GPU/MPS）を管理するユーティリティ。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def get_device():
    """
    利用可能な最適なデバイスを取得する。
    優先順位: MPS (Apple Silicon) > CUDA (NVIDIA GPU) > CPU
    常に torch.device を返す。PyTorch 未インストール時は torch.device("cpu")。
    """
    try:
        import torch
        if torch.backends.mps.is_available():
            device = torch.device("mps")
            logger.debug("MPS device detected and will be used.")
            return device
        if torch.cuda.is_available():
            device = torch.device("cuda")
            logger.debug("CUDA device detected and will be used.")
            return device
        return torch.device("cpu")
    except ImportError:
        logger.debug("PyTorch is not installed. Falling back to CPU.")
        import types
        # torch 未インストール時は文字列 "cpu" を返す (torch 非依存コードで安全に使用可能)
        return "cpu"

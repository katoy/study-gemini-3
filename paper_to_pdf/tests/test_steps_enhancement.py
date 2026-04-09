"""
steps/enhancement.py のテスト。
"""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from core.config import ProcessingConfig
from steps.enhancement import EnhancementStep


class TestEnhancementStep:
    def setup_method(self):
        self.cfg = ProcessingConfig(ai_enhance=False)

    def test_no_enhancer_returns_original(self, text_image):
        step = EnhancementStep(self.cfg)
        result = step.process([text_image])
        assert result == [text_image]

    def test_initialize_without_ai_no_enhancers(self):
        step = EnhancementStep(self.cfg)
        step.initialize()
        assert step.enhancers == []

    def test_initialize_with_realesrgan(self):
        cfg = ProcessingConfig(ai_enhance=True, ai_backend="realesrgan", ai_scale=2)
        step = EnhancementStep(cfg)
        mock_enhancer = MagicMock()
        mock_enhancer.enhance.side_effect = lambda x: x
        mock_create = MagicMock(return_value=mock_enhancer)
        import sys
        fake_ai = MagicMock()
        fake_ai.create_enhancer = mock_create
        with patch.dict(sys.modules, {"ai_enhancer": fake_ai}):
            step.initialize()
        assert len(step.enhancers) == 1

    def test_initialize_with_swin2sr(self):
        cfg = ProcessingConfig(ai_enhance=True, ai_backend="swin2sr", ai_scale=2)
        step = EnhancementStep(cfg)
        mock_enhancer = MagicMock()
        mock_enhancer.enhance.side_effect = lambda x: x
        mock_create = MagicMock(return_value=mock_enhancer)
        import sys
        fake_ai = MagicMock()
        fake_ai.create_enhancer = mock_create
        with patch.dict(sys.modules, {"ai_enhancer": fake_ai}):
            step.initialize()
        assert len(step.enhancers) == 1

    def test_initialize_with_docres(self):
        cfg = ProcessingConfig(ai_enhance=True, ai_backend="docres", ai_scale=1)
        step = EnhancementStep(cfg)
        mock_enhancer = MagicMock()
        mock_enhancer.enhance.side_effect = lambda x: x
        mock_create = MagicMock(return_value=mock_enhancer)
        import sys
        fake_ai = MagicMock()
        fake_ai.create_enhancer = mock_create
        with patch.dict(sys.modules, {"ai_enhancer": fake_ai}):
            step.initialize()
        assert len(step.enhancers) == 1

    def test_process_with_enhancer(self, text_image):
        cfg = ProcessingConfig(ai_enhance=True, ai_backend="realesrgan")
        step = EnhancementStep(cfg)
        mock_enhancer = MagicMock()
        mock_enhancer.enhance.side_effect = lambda x: x * 2  # 変換を模擬
        mock_enhancer.enhance.side_effect = lambda x: x
        step.enhancers = [mock_enhancer]
        result = step.process([text_image])
        assert len(result) == 1
        mock_enhancer.enhance.assert_called_once_with(text_image)

    def test_process_with_multiple_enhancers(self, text_image):
        cfg = ProcessingConfig(ai_enhance=True, ai_backend="realesrgan")
        step = EnhancementStep(cfg)
        mock_e1 = MagicMock()
        mock_e1.enhance.side_effect = lambda x: x
        mock_e2 = MagicMock()
        mock_e2.enhance.side_effect = lambda x: x
        step.enhancers = [mock_e1, mock_e2]
        result = step.process([text_image])
        assert len(result) == 1
        mock_e1.enhance.assert_called_once()
        mock_e2.enhance.assert_called_once()


def _mock_import_ai_enhancer(mock_create):
    """ai_enhancer をインポートしようとしたときにモックを返すヘルパー。"""
    import builtins
    real_import = builtins.__import__
    def _import(name, *args, **kwargs):
        if name == "ai_enhancer":
            mod = MagicMock()
            mod.create_enhancer = mock_create
            return mod
        return real_import(name, *args, **kwargs)
    return _import

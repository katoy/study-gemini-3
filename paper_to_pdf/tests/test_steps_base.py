"""
steps/base.py のテスト。
"""
import pytest

from core.config import ProcessingConfig
from steps.base import ProcessingStep


class ConcreteStep(ProcessingStep):
    """テスト用の具象実装。"""
    def process(self, images):
        return images


class TestProcessingStep:
    def setup_method(self):
        self.cfg = ProcessingConfig()
        self.step = ConcreteStep(self.cfg)

    def test_name_is_class_name(self):
        assert self.step.name == "ConcreteStep"

    def test_process_returns_images(self, white_image):
        result = self.step.process([white_image])
        assert result == [white_image]

    def test_initialize_does_nothing(self):
        self.step.initialize()  # 例外が出なければOK

    def test_finalize_does_nothing(self):
        self.step.finalize()  # 例外が出なければOK

    def test_abstract_class_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ProcessingStep(self.cfg)

    def test_config_stored(self):
        assert self.step.config is self.cfg

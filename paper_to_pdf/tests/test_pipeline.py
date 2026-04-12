"""
core/pipeline.py のテスト。
"""
from unittest.mock import MagicMock

from core.config import ProcessingConfig
from core.pipeline import Pipeline
from steps.base import ProcessingStep


class PassthroughStep(ProcessingStep):
    def __init__(self, config):
        super().__init__(config)
        self.called = False

    def process(self, images):
        self.called = True
        return images


class DoubleStep(ProcessingStep):
    """各画像を 2 枚に複製するステップ。"""
    def process(self, images):
        return images + images


class ErrorStep(ProcessingStep):
    """常に例外を発生させるステップ。"""
    def process(self, images):
        raise RuntimeError("Intentional error")


class TestPipeline:
    def setup_method(self):
        self.cfg = ProcessingConfig()
        self.pipeline = Pipeline(self.cfg)

    # ── add_step / steps ─────────────────────────────────────────────

    def test_add_step_appends(self):
        step = PassthroughStep(self.cfg)
        self.pipeline.add_step(step)
        assert step in self.pipeline.steps

    def test_empty_pipeline_returns_single_image(self, white_image):
        result = self.pipeline.run(white_image)
        assert len(result) == 1

    # ── initialize / finalize ────────────────────────────────────────

    def test_initialize_calls_each_step(self):
        mock_step = MagicMock(spec=ProcessingStep)
        mock_step.name = "MockStep"
        self.pipeline.steps = [mock_step]
        self.pipeline.initialize()
        mock_step.initialize.assert_called_once()

    def test_finalize_calls_each_step(self):
        mock_step = MagicMock(spec=ProcessingStep)
        mock_step.name = "MockStep"
        self.pipeline.steps = [mock_step]
        self.pipeline.finalize()
        mock_step.finalize.assert_called_once()

    # ── run ───────────────────────────────────────────────────────────

    def test_run_calls_each_step(self, white_image):
        step = PassthroughStep(self.cfg)
        self.pipeline.add_step(step)
        self.pipeline.run(white_image)
        assert step.called

    def test_run_passes_output_to_next_step(self, white_image):
        double = DoubleStep(self.cfg)
        passthrough = PassthroughStep(self.cfg)
        self.pipeline.add_step(double)
        self.pipeline.add_step(passthrough)
        result = self.pipeline.run(white_image)
        assert len(result) == 2  # DoubleStep が 2 枚に複製

    def test_run_recovers_from_step_error(self, white_image):
        """ステップでエラーが発生しても続行し、元の画像を返す。"""
        error_step = ErrorStep(self.cfg)
        self.pipeline.add_step(error_step)
        result = self.pipeline.run(white_image)
        assert len(result) == 1

    def test_run_error_step_uses_previous_images(self, white_image):
        """エラーステップ前の出力がエラー後に引き継がれる。"""
        double = DoubleStep(self.cfg)
        error_step = ErrorStep(self.cfg)
        passthrough = PassthroughStep(self.cfg)
        self.pipeline.add_step(double)
        self.pipeline.add_step(error_step)
        self.pipeline.add_step(passthrough)
        result = self.pipeline.run(white_image)
        # double が 2 枚にしたがエラーでロールバック → さらに passthrough → 2 枚
        assert len(result) == 2

    def test_run_multiple_steps_sequentially(self, white_image):
        for _ in range(3):
            self.pipeline.add_step(PassthroughStep(self.cfg))
        result = self.pipeline.run(white_image)
        assert len(result) == 1

    def test_config_stored(self):
        assert self.pipeline.config is self.cfg

    # ── strict モード ──────────────────────────────────────────────────

    def test_strict_false_by_default(self):
        assert self.pipeline.strict is False

    def test_strict_mode_raises_on_step_error(self, white_image):
        """strict=True の場合、ステップエラーが即座に再送出される。"""
        strict_pipeline = Pipeline(self.cfg, strict=True)
        strict_pipeline.add_step(ErrorStep(self.cfg))
        import pytest
        with pytest.raises(RuntimeError, match="Intentional error"):
            strict_pipeline.run(white_image)

    def test_strict_mode_does_not_swallow_error(self, white_image):
        """strict=True では後続ステップは実行されない。"""
        strict_pipeline = Pipeline(self.cfg, strict=True)
        passthrough = PassthroughStep(self.cfg)
        strict_pipeline.add_step(ErrorStep(self.cfg))
        strict_pipeline.add_step(passthrough)
        import pytest
        with pytest.raises(RuntimeError):
            strict_pipeline.run(white_image)
        assert not passthrough.called

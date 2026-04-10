"""
steps/dewarp.py のテスト。
"""
from unittest.mock import MagicMock, patch

from core.config import ProcessingConfig
from steps.dewarp import DewarpStep


def _make_mock_dewarper(mode="polynomial"):
    d = MagicMock()
    d.dewarp.side_effect = lambda x: x  # そのまま返す
    return d


class TestDewarpStep:
    def _make_step(self, dewarp_mode="polynomial", writing_mode="auto"):
        cfg = ProcessingConfig(dewarp_mode=dewarp_mode, writing_mode=writing_mode)
        # Dewarper のロードをモック
        with patch("steps.dewarp.Dewarper") as MockDewarper:
            MockDewarper.return_value = _make_mock_dewarper(dewarp_mode)
            step = DewarpStep(cfg, mode=dewarp_mode)
            step._dewarpers = {
                False: _make_mock_dewarper(dewarp_mode),
                True:  _make_mock_dewarper(dewarp_mode),
            }
        return step

    def test_mode_none_returns_original(self, text_image):
        cfg = ProcessingConfig(dewarp_mode="none")
        with patch("steps.dewarp.Dewarper"):
            step = DewarpStep(cfg, mode="none")
        result = step.process([text_image])
        assert result == [text_image]

    def test_process_with_polynomial(self, text_image):
        step = self._make_step(dewarp_mode="polynomial")
        result = step.process([text_image])
        assert len(result) == 1
        # Dewarper が呼ばれていること
        called = step._dewarpers[False].dewarp.called or step._dewarpers[True].dewarp.called
        assert called

    def test_writing_mode_vertical_uses_vert_dewarper(self, text_image):
        step = self._make_step(dewarp_mode="polynomial", writing_mode="vertical")
        result = step.process([text_image])
        assert len(result) == 1
        step._dewarpers[True].dewarp.assert_called_once_with(text_image)

    def test_writing_mode_horizontal_uses_horiz_dewarper(self, text_image):
        step = self._make_step(dewarp_mode="polynomial", writing_mode="horizontal")
        step.process([text_image])
        step._dewarpers[False].dewarp.assert_called_once_with(text_image)

    def test_writing_mode_auto_detects_direction(self, spread_image):
        step = self._make_step(dewarp_mode="polynomial", writing_mode="auto")
        result = step.process([spread_image])
        assert len(result) == 1

    def test_initialize_calls_load_model(self):
        cfg = ProcessingConfig(dewarp_mode="polynomial")
        with patch("steps.dewarp.Dewarper") as MockDewarper:
            mock_d = _make_mock_dewarper()
            MockDewarper.return_value = mock_d
            step = DewarpStep(cfg, mode="polynomial")
            step._dewarpers = {False: mock_d, True: _make_mock_dewarper()}
            step.initialize()
            mock_d.load_model.assert_called_once()

    def test_initialize_mode_none_skips_load(self):
        cfg = ProcessingConfig(dewarp_mode="none")
        with patch("steps.dewarp.Dewarper") as MockDewarper:
            mock_d = _make_mock_dewarper("none")
            MockDewarper.return_value = mock_d
            step = DewarpStep(cfg, mode="none")
            step._dewarpers = {False: mock_d, True: _make_mock_dewarper()}
            step.initialize()
            mock_d.load_model.assert_not_called()

    def test_finalize_calls_unload_model(self):
        cfg = ProcessingConfig(dewarp_mode="polynomial")
        with patch("steps.dewarp.Dewarper") as MockDewarper:
            mock_d1 = _make_mock_dewarper()
            mock_d2 = _make_mock_dewarper()
            MockDewarper.return_value = mock_d1
            step = DewarpStep(cfg, mode="polynomial")
            step._dewarpers = {False: mock_d1, True: mock_d2}
            step.finalize()
            mock_d1.unload_model.assert_called_once()
            mock_d2.unload_model.assert_called_once()

    def test_mode_override_over_config(self):
        cfg = ProcessingConfig(dewarp_mode="dewarpnet")
        with patch("steps.dewarp.Dewarper"):
            step = DewarpStep(cfg, mode="polynomial")
        assert step._effective_mode == "polynomial"

    def test_mode_none_uses_config(self):
        cfg = ProcessingConfig(dewarp_mode="polynomial")
        with patch("steps.dewarp.Dewarper"):
            step = DewarpStep(cfg, mode=None)
        assert step._effective_mode == "polynomial"

    def test_empty_list(self):
        step = self._make_step()
        result = step.process([])
        assert result == []

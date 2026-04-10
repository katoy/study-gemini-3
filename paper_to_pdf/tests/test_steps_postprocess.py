"""
steps/postprocess.py のテスト。
"""
import numpy as np
from unittest.mock import patch

from core.config import ProcessingConfig
from steps.postprocess import PostProcessStep


class TestPostProcessStep:
    def setup_method(self):
        self.cfg = ProcessingConfig()

    def _make_step(self, **kwargs):
        cfg = ProcessingConfig(**kwargs)
        return PostProcessStep(cfg)

    def test_processes_images(self, text_image):
        step = self._make_step()
        result = step.process([text_image])
        assert len(result) == 1
        assert result[0].ndim == 3

    def test_multiple_images(self, text_image, white_image):
        step = self._make_step()
        result = step.process([text_image, white_image])
        assert len(result) == 2

    def test_show_book_area_skips_processing(self, white_image):
        """show_book_area=True のとき画像をそのまま返す。"""
        step = self._make_step(show_book_area=True)
        result = step.process([white_image])
        assert len(result) == 1
        np.testing.assert_array_equal(result[0], white_image)

    def test_show_page_area_skips_processing(self, white_image):
        """show_page_area=True のとき画像をそのまま返す。"""
        step = self._make_step(show_page_area=True)
        result = step.process([white_image])
        np.testing.assert_array_equal(result[0], white_image)

    def test_border_false_skips_remove_border(self, text_image):
        step = self._make_step(border=False)
        result = step.process([text_image])
        assert len(result) == 1

    def test_shadow_strength_zero_skips_shadow(self, text_image):
        step = self._make_step(shadow_strength=0.0)
        result = step.process([text_image])
        assert len(result) == 1

    def test_docres_backend_skips_classical_shadow(self, text_image):
        step = self._make_step(ai_enhance=True, ai_backend="docres")
        result = step.process([text_image])
        assert len(result) == 1

    def test_grayscale_output(self, text_image):
        step = self._make_step(grayscale=True)
        result = step.process([text_image])
        assert len(result) == 1
        # グレースケール変換後は R==G==B のはず
        r, g, b = result[0][:, :, 2], result[0][:, :, 1], result[0][:, :, 0]
        np.testing.assert_array_equal(r, g)

    def test_vertical_writing_mode_skips_deskew(self, text_image):
        """writing_mode='vertical' のとき deskew_page をスキップする。"""
        step = self._make_step(writing_mode="vertical")
        with patch("steps.postprocess.deskew_page") as mock_deskew:
            step.process([text_image])
        mock_deskew.assert_not_called()

    def test_non_vertical_writing_mode_calls_deskew(self, text_image):
        """writing_mode が 'vertical' 以外のとき deskew_page を呼ぶ。"""
        for mode in ("auto", "horizontal"):
            step = self._make_step(writing_mode=mode)
            with patch("steps.postprocess.deskew_page", return_value=text_image) as mock_deskew:
                step.process([text_image])
            mock_deskew.assert_called_once()

    def test_empty_list(self):
        step = self._make_step()
        result = step.process([])
        assert result == []

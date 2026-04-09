"""
core/config.py のテスト。
"""
import pytest
from core.config import ProcessingConfig, OUTPUT_SIZES


class TestOutputSizes:
    def test_contains_standard_sizes(self):
        for key in ("A4", "A5", "B5", "Letter"):
            assert key in OUTPUT_SIZES

    def test_sizes_are_portrait(self):
        for name, (w, h) in OUTPUT_SIZES.items():
            assert w < h, f"{name}: 幅({w}) < 高さ({h}) であるべき"


class TestProcessingConfigDefaults:
    def test_default_creation(self):
        cfg = ProcessingConfig()
        assert cfg.book_type == "auto"
        assert cfg.dewarp_mode == "dewarpnet"
        assert cfg.split is True
        assert cfg.orient is True
        assert cfg.border is True
        assert cfg.output_size == "A4"
        assert cfg.sensitivity == "medium"
        assert cfg.grayscale is False
        assert cfg.shadow_strength == 1.0
        assert cfg.dpi == 300
        assert cfg.rotate_angle == 0
        assert cfg.writing_mode == "auto"
        assert cfg.ai_enhance is False
        assert cfg.ai_backend == "realesrgan"
        assert cfg.ai_scale == 2
        assert cfg.show_book_area is False
        assert cfg.show_page_area is False


class TestProcessingConfigValidation:
    def test_invalid_book_type(self):
        with pytest.raises(ValueError, match="book_type"):
            ProcessingConfig(book_type="invalid")

    def test_invalid_dewarp_mode(self):
        with pytest.raises(ValueError, match="dewarp_mode"):
            ProcessingConfig(dewarp_mode="bad_mode")

    def test_invalid_sensitivity(self):
        with pytest.raises(ValueError, match="sensitivity"):
            ProcessingConfig(sensitivity="ultra")

    def test_invalid_output_size(self):
        with pytest.raises(ValueError, match="output_size"):
            ProcessingConfig(output_size="C3")

    def test_invalid_ai_backend(self):
        with pytest.raises(ValueError, match="ai_backend"):
            ProcessingConfig(ai_backend="unknown")

    def test_invalid_ai_scale(self):
        with pytest.raises(ValueError, match="ai_scale"):
            ProcessingConfig(ai_scale=3)

    def test_invalid_rotate_angle(self):
        with pytest.raises(ValueError, match="rotate_angle"):
            ProcessingConfig(rotate_angle=45)

    def test_invalid_writing_mode(self):
        with pytest.raises(ValueError, match="writing_mode"):
            ProcessingConfig(writing_mode="diagonal")

    def test_shadow_strength_too_low(self):
        with pytest.raises(ValueError, match="shadow_strength"):
            ProcessingConfig(shadow_strength=-0.1)

    def test_shadow_strength_too_high(self):
        with pytest.raises(ValueError, match="shadow_strength"):
            ProcessingConfig(shadow_strength=1.1)

    def test_shadow_strength_boundary_values(self):
        cfg0 = ProcessingConfig(shadow_strength=0.0)
        assert cfg0.shadow_strength == 0.0
        cfg1 = ProcessingConfig(shadow_strength=1.0)
        assert cfg1.shadow_strength == 1.0

    def test_valid_book_types(self):
        for bt in ("jp_vert", "jp_horiz", "en", "manga", "auto"):
            cfg = ProcessingConfig(book_type=bt)
            assert cfg.book_type == bt

    def test_valid_dewarp_modes(self):
        for mode in ("dewarpnet", "polynomial", "doctr", "none"):
            cfg = ProcessingConfig(dewarp_mode=mode)
            assert cfg.dewarp_mode == mode

    def test_valid_sensitivities(self):
        for s in ("low", "medium", "high"):
            cfg = ProcessingConfig(sensitivity=s)
            assert cfg.sensitivity == s

    def test_valid_rotate_angles(self):
        for a in (0, 90, 180, 270):
            cfg = ProcessingConfig(rotate_angle=a)
            assert cfg.rotate_angle == a

    def test_valid_ai_scales(self):
        for scale in (1, 2, 4):
            cfg = ProcessingConfig(ai_scale=scale)
            assert cfg.ai_scale == scale


class TestPageOrder:
    def test_writing_mode_vertical(self):
        cfg = ProcessingConfig(writing_mode="vertical")
        assert cfg.page_order == "right_first"

    def test_writing_mode_horizontal(self):
        cfg = ProcessingConfig(writing_mode="horizontal")
        assert cfg.page_order == "left_first"

    def test_writing_mode_auto_jp_vert(self):
        cfg = ProcessingConfig(writing_mode="auto", book_type="jp_vert")
        assert cfg.page_order == "right_first"

    def test_writing_mode_auto_manga(self):
        cfg = ProcessingConfig(writing_mode="auto", book_type="manga")
        assert cfg.page_order == "right_first"

    def test_writing_mode_auto_auto(self):
        cfg = ProcessingConfig(writing_mode="auto", book_type="auto")
        assert cfg.page_order == "auto"

    def test_writing_mode_auto_en(self):
        cfg = ProcessingConfig(writing_mode="auto", book_type="en")
        assert cfg.page_order == "left_first"

    def test_writing_mode_auto_jp_horiz(self):
        cfg = ProcessingConfig(writing_mode="auto", book_type="jp_horiz")
        assert cfg.page_order == "left_first"

"""
dewarper.py のテスト。
"""
import numpy as np
import torch
from unittest.mock import MagicMock, patch
from pathlib import Path
from dewarper import (
    Dewarper, _advanced_polynomial_dewarp, _is_result_invalid,
    _DewarpNetInferencer, _DewarpNetContentError,
    _estimate_curvature_percent, _DEWARPNET_MIN_CURVATURE_PCT,
)

class TestDewarperFunctions:
    def test_is_result_invalid(self):
        gray_orig = np.full((10, 10, 3), 128, dtype=np.uint8)
        # 全白・全黒 → 無効
        assert bool(_is_result_invalid(gray_orig, np.full((10, 10, 3), 255, dtype=np.uint8))) is True
        assert bool(_is_result_invalid(gray_orig, np.full((10, 10, 3), 0,   dtype=np.uint8))) is True
        # 中間グレー → 有効
        assert bool(_is_result_invalid(gray_orig, np.full((10, 10, 3), 128, dtype=np.uint8))) is False
        # コンテンツ消失チェック: 元画像に暗ピクセルが 1% 超あるのに処理後に 90% 以上消えた → 無効
        orig_with_text = np.full((100, 100, 3), 200, dtype=np.uint8)
        orig_with_text[10:50, 10:50] = 50  # 約 16% の暗ピクセル (< 100)
        proc_blank = np.full((100, 100, 3), 200, dtype=np.uint8)  # 暗ピクセルなし
        assert bool(_is_result_invalid(orig_with_text, proc_blank)) is True
        # 暗ピクセルが保持されている場合は有効
        proc_keep = orig_with_text.copy()
        assert bool(_is_result_invalid(orig_with_text, proc_keep)) is False

    def test_advanced_polynomial_dewarp_branches(self):
        img = np.zeros((500, 800, 3), dtype=np.uint8)
        w_flat = np.ones(201, dtype=np.float32)

        # 1. curv_pct < 0.2 (平坦な場合)
        pts_flat = np.zeros((201, 2), dtype=np.float32)
        pts_flat[:, 0] = np.linspace(0, 799, 201)
        with patch("dewarper.extract_line_profiles", return_value=(pts_flat, w_flat, 1.0)):
            _advanced_polynomial_dewarp(img)

        # 2. 0.2 <= curv_pct < 65.0 (通常の補正パス & logger.debug 通過)
        pts_curved = np.zeros((201, 2), dtype=np.float32)
        pts_curved[:, 0] = np.linspace(0, 799, 201)
        # 適度な湾曲
        pts_curved[:, 1] = 0.0001 * (pts_curved[:, 0] - 400)**2
        with patch("dewarper.extract_line_profiles", return_value=(pts_curved, w_flat, 1.0)):
            with patch("dewarper._is_result_invalid", return_value=False):
                _advanced_polynomial_dewarp(img)

        # 3. _is_result_invalid == True
        with patch("dewarper.extract_line_profiles", return_value=(pts_curved, w_flat, 1.0)):
            with patch("dewarper._is_result_invalid", return_value=True):
                _advanced_polynomial_dewarp(img)

        # 4. len(pts_np) < 200 (2 回目の iteration で検出なし)
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (pts_curved, w_flat, 1.0)
            return (np.zeros((10, 2)), np.ones(10), 1.0)
        with patch("dewarper.extract_line_profiles", side_effect=side_effect):
            with patch("dewarper._is_result_invalid", return_value=False):
                _advanced_polynomial_dewarp(img)

        # 5. Vertical
        with patch("dewarper.extract_line_profiles", return_value=(pts_flat, w_flat, 1.0)):
            _advanced_polynomial_dewarp(img, is_vertical=True)

    def test_estimate_curvature_percent(self):
        img = np.zeros((500, 800, 3), dtype=np.uint8)
        w_flat = np.ones(201, dtype=np.float32)
        pts_flat = np.zeros((201, 2), dtype=np.float32)
        pts_flat[:, 0] = np.linspace(0, 799, 201)

        # 平坦な場合は 0 に近い
        with patch("dewarper.extract_line_profiles", return_value=(pts_flat, w_flat, 1.0)):
            curv = _estimate_curvature_percent(img)
        assert curv < 0.5

        # ライン少ない場合は None（「湾曲不明」= 0.0 と区別する）
        with patch("dewarper.extract_line_profiles", return_value=(np.zeros((10, 2)), np.ones(10), 1.0)):
            assert _estimate_curvature_percent(img) is None

        # is_vertical=True でも動作する
        with patch("dewarper.extract_line_profiles", return_value=(pts_flat, w_flat, 1.0)):
            _estimate_curvature_percent(img, is_vertical=True)

class TestDewarpNetInferencer:
    @patch("torch.load")
    @patch("dewarper.download_file")
    @patch("torch.nn.Module.load_state_dict")
    def test_init_and_load(self, mock_load_sd, mock_ret, mock_load):
        mock_load.return_value = {"model_state_dict": {}}
        with patch.object(Path, "exists", return_value=False):
            _DewarpNetInferencer()
            assert mock_ret.called

    @patch("torch.load", return_value={})
    @patch("dewarper.get_device", return_value="cpu")
    @patch("torch.nn.Module.load_state_dict")
    def test_dewarp_inference(self, mock_load_sd, mock_dev, mock_load):
        inf = _DewarpNetInferencer()
        inf.wc_model = MagicMock()
        inf.bm_model = MagicMock()
        inf.bm_model.return_value = torch.zeros((1, 2, 128, 128))
        # グレー画像を使用：remap後もグレーのため _is_result_invalid=False → return result を通過
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        res = inf.dewarp(img)
        assert res.shape == (100, 100, 3)

    @patch("torch.load", return_value={})
    @patch("dewarper.get_device", return_value="cpu")
    @patch("torch.nn.Module.load_state_dict")
    def test_dewarp_invalid_result_raises(self, mock_load_sd, mock_dev, mock_load):
        """DewarpNet の出力が白飛び/黒潰れ/コンテンツ消失の場合は例外を投げる。"""
        inf = _DewarpNetInferencer()
        inf.wc_model = MagicMock()
        inf.bm_model = MagicMock()
        inf.bm_model.return_value = torch.zeros((1, 2, 128, 128))
        img = np.zeros((100, 100, 3), dtype=np.uint8)  # 全黒 → remap後も黒 → invalid
        import pytest
        with pytest.raises(_DewarpNetContentError):
            inf.dewarp(img)

    @patch("torch.load", return_value={})
    @patch("dewarper.get_device", return_value="cpu")
    @patch("torch.nn.Module.load_state_dict")
    def test_dewarper_switches_to_polynomial_on_content_error(self, mock_load_sd, mock_dev, mock_load):
        """_DewarpNetContentError 発生時に polynomial に切り替え、以降は DewarpNet を使わない。"""
        d = Dewarper(mode="dewarpnet")
        d._ai_inferencer = MagicMock()
        d._ai_inferencer.dewarp.side_effect = _DewarpNetContentError("テスト用エラー")
        img = np.full((50, 50, 3), 128, dtype=np.uint8)
        with patch("dewarper._estimate_curvature_percent", return_value=_DEWARPNET_MIN_CURVATURE_PCT + 1.0):
            with patch("dewarper._advanced_polynomial_dewarp", return_value=img) as mock_poly:
                result = d.dewarp(img)
        assert d.mode == "polynomial"
        assert d._ai_inferencer is None
        mock_poly.assert_called_once()
        np.testing.assert_array_equal(result, img)

class TestDewarperClass:
    def test_load_model_variants(self):
        d = Dewarper(mode="polynomial")
        assert d.load_model() is True
        d2 = Dewarper(mode="dewarpnet")
        with patch("dewarper._DewarpNetInferencer"):
            assert d2.load_model() is True
        d3 = Dewarper(mode="dewarpnet")
        with patch("dewarper._DewarpNetInferencer", side_effect=Exception()):
            d3.load_model()
            assert d3.mode == "polynomial"

    def test_dewarp_dispatch(self):
        d = Dewarper(mode="dewarpnet")
        mock_inf = MagicMock()
        mock_inf.dewarp.return_value = np.zeros((10,10,3), dtype=np.uint8)
        d._ai_inferencer = mock_inf
        img = np.zeros((10,10,3), dtype=np.uint8)
        # 湾曲度が十分ある場合は DewarpNet を呼ぶ
        with patch("dewarper._estimate_curvature_percent", return_value=_DEWARPNET_MIN_CURVATURE_PCT + 1.0):
            assert d.dewarp(img).shape == (10,10,3)
            mock_inf.dewarp.side_effect = Exception()
            d.dewarp(img)
        d.mode = "polynomial"
        with patch("dewarper._advanced_polynomial_dewarp", side_effect=Exception()):
            d.dewarp(img)

    def test_dewarp_skips_dewarpnet_for_flat_image(self):
        """湾曲度が閾値未満の画像は DewarpNet をスキップして polynomial を使う。"""
        d = Dewarper(mode="dewarpnet")
        d._ai_inferencer = MagicMock()
        img = np.full((50, 50, 3), 128, dtype=np.uint8)
        with patch("dewarper._estimate_curvature_percent", return_value=_DEWARPNET_MIN_CURVATURE_PCT - 0.1):
            with patch("dewarper._advanced_polynomial_dewarp", return_value=img) as mock_poly:
                result = d.dewarp(img)
        d._ai_inferencer.dewarp.assert_not_called()
        mock_poly.assert_called_once()
        np.testing.assert_array_equal(result, img)

    def test_dewarp_calls_dewarpnet_when_curvature_unknown(self):
        """湾曲度が None（ライン検出失敗）でも DewarpNet を試みる（dewarper.py:197）。"""
        d = Dewarper(mode="dewarpnet")
        mock_inf = MagicMock()
        result_img = np.full((10, 10, 3), 128, dtype=np.uint8)
        mock_inf.dewarp.return_value = result_img
        d._ai_inferencer = mock_inf
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        with patch("dewarper._estimate_curvature_percent", return_value=None):
            d.dewarp(img)
        mock_inf.dewarp.assert_called_once()

    def test_unload(self):
        d = Dewarper()
        d._ai_inferencer = MagicMock()
        d.unload_model()
        assert d._ai_inferencer is None

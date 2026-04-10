"""
dewarper.py のテスト。
"""
import numpy as np
import torch
from unittest.mock import MagicMock, patch
from pathlib import Path
from dewarper import Dewarper, _advanced_polynomial_dewarp, _is_image_broken, _DewarpNetInferencer

class TestDewarperFunctions:
    def test_is_image_broken(self):
        assert bool(_is_image_broken(None, np.full((10,10,3), 255, dtype=np.uint8))) is True
        assert bool(_is_image_broken(None, np.full((10,10,3), 0, dtype=np.uint8))) is True
        assert bool(_is_image_broken(None, np.full((10,10,3), 128, dtype=np.uint8))) is False

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
            with patch("dewarper._is_image_broken", return_value=False):
                _advanced_polynomial_dewarp(img)

        # 3. _is_image_broken == True
        with patch("dewarper.extract_line_profiles", return_value=(pts_curved, w_flat, 1.0)):
            with patch("dewarper._is_image_broken", return_value=True):
                _advanced_polynomial_dewarp(img)
        
        # 4. len(pts_np) < 200
        with patch("dewarper.extract_line_profiles", return_value=(np.zeros((10, 2)), np.ones(10), 1.0)):
            _advanced_polynomial_dewarp(img)

        # 5. Vertical
        with patch("dewarper.extract_line_profiles", return_value=(pts_flat, w_flat, 1.0)):
            _advanced_polynomial_dewarp(img, is_vertical=True)

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
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        res = inf.dewarp(img)
        assert res.shape == (100, 100, 3)

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
        assert d.dewarp(img).shape == (10,10,3)
        mock_inf.dewarp.side_effect = Exception()
        d.dewarp(img)
        d.mode = "polynomial"
        with patch("dewarper._advanced_polynomial_dewarp", side_effect=Exception()):
            d.dewarp(img)

    def test_unload(self):
        d = Dewarper()
        d._ai_inferencer = MagicMock()
        d.unload_model()
        assert d._ai_inferencer is None

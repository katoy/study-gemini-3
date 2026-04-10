"""
ai_enhancer.py のテスト。
"""
import cv2
import numpy as np
import pytest
import torch
from unittest.mock import MagicMock, patch, ANY
from pathlib import Path

from ai_enhancer import (
    _apply_tiled,
    _build_rrdbnet,
    _RealESRGANInferencer,
    _build_docres_unet,
    create_enhancer,
    RealESRGANEnhancer,
    Swin2SREnhancer,
    DocResEnhancer,
    BaseAIEnhancer
)

class TestModelArchitectures:
    def test_build_rrdbnet(self):
        for s in [1, 2, 4]:
            assert _build_rrdbnet(scale=s).scale == s

    def test_build_docres_unet_forward(self):
        model = _build_docres_unet()
        model(torch.zeros((1, 3, 32, 32)))

class TestRealESRGANInferencer:
    @patch("torch.load")
    @patch("ai_enhancer.get_device", return_value="cpu")
    def test_inferencer_init_variants(self, mock_device, mock_load):
        for key in ["params_ema", "params", "other"]:
            mock_load.return_value = {key: {}} if key != "other" else {}
            with patch("ai_enhancer._build_rrdbnet") as mock_build:
                m = MagicMock(spec=torch.nn.Module); m.to.return_value = m; mock_build.return_value = m
                _RealESRGANInferencer(scale=2, model_path="f.pth")

    @patch("torch.load", return_value={"params": {}})
    @patch("ai_enhancer.get_device", return_value="cpu")
    def test_enhance_with_padding(self, mock_device, mock_load):
        with patch("ai_enhancer._build_rrdbnet") as mock_build:
            m = MagicMock(spec=torch.nn.Module); m.to.return_value = m
            m.side_effect = lambda x: torch.zeros((1, 3, x.shape[2]*2, x.shape[3]*2))
            mock_build.return_value = m
            inf = _RealESRGANInferencer(scale=2, model_path="f.pth")
            assert inf.enhance(np.zeros((10, 10, 3), dtype=np.uint8)).shape == (20, 20, 3)

    @patch("torch.load", return_value={"params": {}})
    @patch("ai_enhancer.get_device", return_value="cpu")
    def test_tile_enhance(self, mock_device, mock_load):
        with patch("ai_enhancer._build_rrdbnet") as mock_build:
            m = MagicMock(spec=torch.nn.Module); m.to.return_value = m
            m.side_effect = lambda x: torch.zeros((1, 3, x.shape[2]*2, x.shape[3]*2))
            mock_build.return_value = m
            inf = _RealESRGANInferencer(scale=2, model_path="f.pth")
            assert inf.enhance(np.zeros((600, 100, 3), dtype=np.uint8)).shape == (1200, 200, 3)

class TestSwin2SREnhancer:
    @patch("transformers.Swin2SRImageProcessor.from_pretrained")
    @patch("transformers.Swin2SRForImageSuperResolution.from_pretrained")
    def test_try_load_success(self, m_model, m_proc):
        m = MagicMock(); m.to.return_value = m; m_model.return_value = m
        assert Swin2SREnhancer(scale=2)._model is not None

    def test_try_load_fail(self):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: 
                   (MagicMock() if n != "transformers" else exec("raise ImportError()"))):
            assert Swin2SREnhancer()._model is None
        with patch("transformers.Swin2SRImageProcessor.from_pretrained", side_effect=Exception):
            assert Swin2SREnhancer()._model is None

    def test_enhance(self):
        enh = Swin2SREnhancer(scale=2); enh._model = MagicMock(); enh._processor = MagicMock()
        o = MagicMock(); o.reconstruction = torch.zeros((1, 3, 40, 40)); enh._model.return_value = o
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        assert enh.enhance(img).shape == (20, 20, 3)
        enh._model.side_effect = Exception(); assert enh.enhance(img).shape == (20, 20, 3)

    def test_name(self): assert Swin2SREnhancer(scale=4).name() == "Swin2SR_x4"

class TestDocResEnhancer:
    @patch("torch.load")
    @patch("ai_enhancer._build_docres_unet")
    @patch("ai_enhancer.download_file")
    def test_try_load(self, m_ret, m_build, m_load):
        # 1. _MODEL_URL が空の場合はダウンロードせず model が None のまま
        with patch.object(Path, "exists", return_value=False):
            e = DocResEnhancer()
            assert not m_ret.called
            assert e._model is None
        # 2. _MODEL_URL が設定されている場合はダウンロードを試みる
        with patch.object(DocResEnhancer, "_MODEL_URL", "https://example.com/docres.pth"):
            with patch.object(Path, "exists", side_effect=[False, True, True]):
                m = MagicMock(); m.to.return_value = m; m_build.return_value = m
                e = DocResEnhancer()
                assert m_ret.called
        # 3. Load error
        with patch("ai_enhancer._build_docres_unet", side_effect=Exception):
            assert DocResEnhancer()._model is None

    @patch("ai_enhancer._build_docres_unet")
    def test_enhance(self, m_build):
        m = MagicMock(); m.to.return_value = m; m.return_value = torch.zeros((1, 3, 16, 16))
        m_build.return_value = m
        enh = DocResEnhancer()
        assert enh.enhance(np.zeros((10, 10, 3), dtype=np.uint8)).shape == (10, 10, 3)
        # Model is None fallback
        enh._model = None
        with patch("image_processor.remove_shadow", return_value=np.zeros((10,10,3))):
            assert enh.enhance(np.zeros((10,10,3))).shape == (10,10,3)

class TestRealESRGANEnhancer:
    def test_try_load_fail(self):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: 
                   (MagicMock() if n != "torch" else exec("raise ImportError()"))):
            assert RealESRGANEnhancer()._upsampler is None
        with patch("ai_enhancer.CACHE_DIR", Path("/none")):
            assert RealESRGANEnhancer()._upsampler is None

    def test_enhance(self):
        enh = RealESRGANEnhancer(scale=2); enh._upsampler = MagicMock()
        enh._upsampler.enhance.return_value = np.zeros((20, 20, 3), dtype=np.uint8)
        img = np.zeros((10, 10, 3), dtype=np.uint8)
        assert enh.enhance(img).shape == (20, 20, 3)
        enh._upsampler.enhance.side_effect = Exception(); assert enh.enhance(img).shape == (20, 20, 3)

    @patch("ai_enhancer.download_file")
    @patch("ai_enhancer._RealESRGANInferencer")
    def test_download(self, m_inf, m_ret):
        with patch.object(Path, "exists", return_value=False):
            with patch("ai_enhancer.CACHE_DIR", Path("/tmp")):
                RealESRGANEnhancer(); assert m_ret.called

def test_create_enhancer():
    create_enhancer("realesrgan"); create_enhancer("swin2sr"); create_enhancer("docres")
    with pytest.raises(ValueError): create_enhancer("unknown")

def test_base_name():
    class M(BaseAIEnhancer):
        def enhance(self, i): return i
    assert M().name() == "M"

def test_apply_tiled():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    assert _apply_tiled(img, lambda p: p, 5, 0, 1).shape == (10, 10, 3)

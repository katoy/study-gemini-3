"""
utils/device.py のテスト。
"""
import sys
from unittest.mock import MagicMock, patch
import pytest


class TestGetDevice:
    def test_torch_import_error_returns_cpu_string(self):
        """torch が未インストールの場合は "cpu" 文字列を返す。"""
        # torch を消してリロード
        saved = sys.modules.pop("torch", None)
        # utils.device もリロードして ImportError パスを通す
        import utils.device
        import importlib

        with patch.dict(sys.modules, {"torch": None}):
            importlib.reload(utils.device)
            result = utils.device.get_device()
        assert result == "cpu"

        if saved is not None:
            sys.modules["torch"] = saved

    def test_mps_available(self):
        """MPS が利用可能な場合は torch.device("mps") を返す。"""
        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = True
        expected = MagicMock(name="mps_device")
        mock_torch.device.side_effect = lambda x: expected if x == "mps" else MagicMock()

        import utils.device
        import importlib
        with patch.dict(sys.modules, {"torch": mock_torch}):
            importlib.reload(utils.device)
            result = utils.device.get_device()
        assert result is expected

    def test_cuda_available_when_no_mps(self):
        """MPS 不可・CUDA 可の場合は torch.device("cuda") を返す。"""
        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = False
        mock_torch.cuda.is_available.return_value = True
        expected = MagicMock(name="cuda_device")
        mock_torch.device.side_effect = lambda x: expected if x == "cuda" else MagicMock()

        import utils.device
        import importlib
        with patch.dict(sys.modules, {"torch": mock_torch}):
            importlib.reload(utils.device)
            result = utils.device.get_device()
        assert result is expected

    def test_cpu_fallback_when_no_accelerator(self):
        """MPS も CUDA も不可の場合は torch.device("cpu") を返す。"""
        mock_torch = MagicMock()
        mock_torch.backends.mps.is_available.return_value = False
        mock_torch.cuda.is_available.return_value = False
        expected = MagicMock(name="cpu_device")
        mock_torch.device.side_effect = lambda x: expected if x == "cpu" else MagicMock()

        import utils.device
        import importlib
        with patch.dict(sys.modules, {"torch": mock_torch}):
            importlib.reload(utils.device)
            result = utils.device.get_device()
        assert result is expected

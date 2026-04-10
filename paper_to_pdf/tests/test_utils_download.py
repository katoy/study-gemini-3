"""tests/test_utils_download.py - utils/download.py のテスト。"""

from unittest.mock import MagicMock, patch

import pytest

from utils.download import download_file, verify_hash


class TestVerifyHash:
    def test_correct_hash(self, tmp_path):
        f = tmp_path / "file.bin"
        f.write_bytes(b"hello")
        # echo -n hello | shasum -a 256
        assert verify_hash(f, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")

    def test_wrong_hash(self, tmp_path):
        f = tmp_path / "file.bin"
        f.write_bytes(b"hello")
        assert not verify_hash(f, "0" * 64)


class TestDownloadFile:
    def test_success(self, tmp_path):
        dest = tmp_path / "model.pth"
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"hello"

        with patch("utils.download.urllib.request.urlopen", return_value=mock_response):
            download_file("https://example.com/model.pth", dest)

        assert dest.read_bytes() == b"hello"

    def test_hash_mismatch_deletes_file(self, tmp_path):
        dest = tmp_path / "model.pth"
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"hello"

        with patch("utils.download.urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(ValueError, match="ハッシュが一致しません"):
                download_file("https://example.com/model.pth", dest,
                              expected_sha256="0" * 64)

        assert not dest.exists()

    def test_hash_match(self, tmp_path):
        dest = tmp_path / "model.pth"
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"hello"

        correct = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        with patch("utils.download.urllib.request.urlopen", return_value=mock_response):
            download_file("https://example.com/model.pth", dest,
                          expected_sha256=correct)

        assert dest.read_bytes() == b"hello"

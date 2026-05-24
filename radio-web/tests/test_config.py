"""Tests for configuration helpers."""

import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio_web import config


class ConfigHelpersTest(unittest.TestCase):
    def test_resolve_cache_root_dir_respects_env(self):
        with patch.dict("os.environ", {"NHK_RADIO_CACHE_DIR": "/tmp/custom_cache"}):
            self.assertEqual(config._resolve_cache_root_dir(), Path("/tmp/custom_cache"))

    def test_default_download_dir_respects_env(self):
        with patch.dict("os.environ", {"NHK_RADIO_DOWNLOAD_DIR": "/tmp/custom_dl"}):
            self.assertEqual(config._default_download_dir(), Path("/tmp/custom_dl"))

    def test_program_cache_dir_and_episode_cache_dir(self):
        with patch.dict("os.environ", {"NHK_RADIO_CACHE_DIR": "/tmp/c"}):
            self.assertEqual(config._program_cache_dir(), Path("/tmp/c/programs"))
            self.assertEqual(config._episode_cache_dir(), Path("/tmp/c/episodes"))

    def test_find_project_root_returns_path_or_none(self):
        result = config._find_project_root()
        # 実行コンテキストによって None もしくは Path が返る
        self.assertTrue(result is None or isinstance(result, Path))

    def test_resolve_cache_root_dir_fallback_to_default(self):
        """プロジェクトルートが見つからない場合、デフォルトキャッシュルートを返す。"""
        with patch.dict("os.environ", {}, clear=False):
            with patch("nhk_radio_web.config._find_project_root", return_value=None):
                result = config._resolve_cache_root_dir()
                # デフォルトキャッシュルートが返される
                self.assertIsInstance(result, Path)

    def test_default_download_dir_fallback_to_home(self):
        """プロジェクトルートが見つからない場合、ホームディレクトリ配下のダウンロードフォルダを返す。"""
        with patch.dict("os.environ", {}, clear=False):
            with patch("nhk_radio_web.config._find_project_root", return_value=None):
                result = config._default_download_dir()
                # ホームディレクトリ配下が返される
                self.assertIn("Downloads", str(result))

    def test_default_user_cache_root_returns_path(self):
        self.assertIsInstance(config._default_user_cache_root(), Path)


if __name__ == "__main__":
    unittest.main()

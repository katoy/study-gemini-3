"""
utils/paths.py のテスト。
"""
from pathlib import Path
from utils.paths import CACHE_DIR


class TestCacheDir:
    def test_cache_dir_is_path(self):
        assert isinstance(CACHE_DIR, Path)

    def test_cache_dir_exists(self):
        assert CACHE_DIR.exists()
        assert CACHE_DIR.is_dir()

    def test_cache_dir_name(self):
        assert CACHE_DIR.name == "paper_to_pdf"

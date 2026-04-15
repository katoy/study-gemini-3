import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _support  # noqa: F401

from nhk_radio import config


class ConfigHelpersTest(unittest.TestCase):
    def test_resolve_cache_root_uses_explicit_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"NHK_RADIO_CACHE_DIR": tmp}, clear=False):
                self.assertEqual(config._resolve_cache_root_dir(), Path(tmp))

    def test_find_project_root_detects_repository_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\nname='radio'\n", encoding="utf-8")
            (root / "nhk_radio_dl.py").write_text("", encoding="utf-8")
            (root / "src" / "nhk_radio").mkdir(parents=True)
            module_path = root / "src" / "nhk_radio" / "config.py"
            module_path.write_text("", encoding="utf-8")

            with patch.object(config.Path, "resolve", return_value=module_path):
                self.assertEqual(config._find_project_root(), root)


if __name__ == "__main__":
    unittest.main()

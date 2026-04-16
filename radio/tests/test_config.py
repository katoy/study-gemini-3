import json
import os
import pathlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio import config
from tests import _support  # noqa: F401


class _FakePath(pathlib.PurePosixPath):
    @classmethod
    def home(cls):
        return cls("/Users/test")


class ConfigHelpersTest(unittest.TestCase):
    def test_default_user_cache_root_for_each_platform(self):
        with patch.object(config.sys, "platform", "darwin"), patch.object(config.os, "name", "posix"):
            self.assertEqual(config._default_user_cache_root(), Path.home() / "Library" / "Caches" / "nhk_radio")

        with (
            patch.object(config.sys, "platform", "win32"),
            patch.object(config.os, "name", "nt"),
            patch.dict(os.environ, {"LOCALAPPDATA": "/tmp/local"}, clear=False),
            patch.object(config, "Path", _FakePath),
        ):
            self.assertEqual(config._default_user_cache_root(), _FakePath("/tmp/local/nhk_radio"))

        with (
            patch.object(config.sys, "platform", "win32"),
            patch.object(config.os, "name", "nt"),
            patch.dict(os.environ, {}, clear=True),
            patch.object(config, "Path", _FakePath),
        ):
            self.assertEqual(config._default_user_cache_root(), _FakePath("/Users/test/AppData/Local/nhk_radio"))

        with (
            patch.object(config.sys, "platform", "linux"),
            patch.object(config.os, "name", "posix"),
            patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/cache"}, clear=False),
        ):
            self.assertEqual(config._default_user_cache_root(), Path("/tmp/cache/nhk_radio"))

    def test_resolve_cache_root_uses_explicit_env(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"NHK_RADIO_CACHE_DIR": tmp}, clear=False):
            self.assertEqual(config._resolve_cache_root_dir(), Path(tmp))

    def test_resolve_cache_root_uses_project_root_or_default_user_cache(self):
        with patch.object(config, "_find_project_root", return_value=Path("/repo")):
            self.assertEqual(config._resolve_cache_root_dir(), Path("/repo/.cache"))

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(config, "_find_project_root", return_value=None),
            patch.object(config, "_default_user_cache_root", return_value=Path("/user-cache")),
        ):
            self.assertEqual(config._resolve_cache_root_dir(), Path("/user-cache"))

    def test_find_project_root_detects_repository_layout_and_handles_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\nname='radio'\n", encoding="utf-8")
            (root / "nhk_radio_dl.py").write_text("", encoding="utf-8")
            (root / "src" / "nhk_radio").mkdir(parents=True)
            module_path = root / "src" / "nhk_radio" / "config.py"
            module_path.write_text("", encoding="utf-8")

            with patch.object(config.Path, "resolve", return_value=module_path):
                self.assertEqual(config._find_project_root(), root)

        with tempfile.TemporaryDirectory() as tmp:
            module_path = Path(tmp) / "x" / "y" / "config.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text("", encoding="utf-8")
            with patch.object(config.Path, "resolve", return_value=module_path):
                self.assertIsNone(config._find_project_root())

    def test_normalize_search_term_and_history(self):
        self.assertEqual(config._normalize_search_term("　 Hello "), "Hello")
        normalized = config._normalize_search_history([" test ", "ＴＥＳＴ", None, "", "next"])
        self.assertEqual(normalized, ["test", "next"])
        many = [f"item{i}" for i in range(config.SEARCH_HISTORY_LIMIT + 2)]
        self.assertEqual(len(config._normalize_search_history(many)), config.SEARCH_HISTORY_LIMIT)

    def test_load_ui_settings_handles_missing_invalid_and_valid_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            with patch.object(config, "UI_SETTINGS_PATH", settings_path):
                self.assertEqual(config._load_ui_settings(), {})

            settings_path.write_text("{bad json", encoding="utf-8")
            with patch.object(config, "UI_SETTINGS_PATH", settings_path):
                self.assertEqual(config._load_ui_settings(), {})

            settings_path.write_text("[]", encoding="utf-8")
            with patch.object(config, "UI_SETTINGS_PATH", settings_path):
                self.assertEqual(config._load_ui_settings(), {})

            settings_path.write_text(
                json.dumps(
                    {
                        "theme": "dark",
                        "font_size_pt": "99",
                        "program_search_history": [" a ", "Ａ", 1, ""],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(config, "UI_SETTINGS_PATH", settings_path):
                self.assertEqual(
                    config._load_ui_settings(),
                    {"theme": "dark", "font_size_pt": "18", "program_search_history": ["a"]},
                )

            settings_path.write_text(json.dumps({"font_size_pt": "bad"}), encoding="utf-8")
            with patch.object(config, "UI_SETTINGS_PATH", settings_path):
                self.assertEqual(config._load_ui_settings(), {})

            settings_path.write_text(json.dumps({"theme": "blue", "program_search_history": "bad"}), encoding="utf-8")
            with patch.object(config, "UI_SETTINGS_PATH", settings_path):
                self.assertEqual(config._load_ui_settings(), {})

    def test_save_ui_settings_writes_normalized_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "nested" / "ui.json"
            with patch.object(config, "UI_SETTINGS_PATH", settings_path):
                config._save_ui_settings("light", "11", ["a"])

            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(payload, {"theme": "light", "font_size_pt": 11, "program_search_history": ["a"]})


if __name__ == "__main__":
    unittest.main()

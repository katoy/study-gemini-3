"""Tests for configuration and settings."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio import config


class ConfigHelpersTest(unittest.TestCase):
    def test_default_paths_exist(self):
        self.assertIsInstance(config._default_user_cache_root(), Path)
        self.assertIsInstance(config._default_user_config_root(), Path)

    def test_resolve_cache_root_dir_respects_env(self):
        with patch.dict("os.environ", {"NHK_RADIO_CACHE_DIR": "/tmp/custom_cache"}):
            self.assertEqual(config._resolve_cache_root_dir(), Path("/tmp/custom_cache"))

    def test_resolve_config_root_dir_respects_env(self):
        with patch.dict("os.environ", {"NHK_RADIO_CONFIG_DIR": "/tmp/custom_config"}):
            self.assertEqual(config._resolve_config_root_dir(), Path("/tmp/custom_config"))

    def test_migrate_legacy_ui_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            config_dir = tmp_path / "config"
            config_dir.mkdir()

            # 通常の移行
            legacy = cache_dir / "ui_settings.json"
            legacy.write_text('{"theme": "dark"}', encoding="utf-8")
            target = config_dir / "ui_settings.json"
            with (
                patch("nhk_radio.config._resolve_cache_root_dir", return_value=cache_dir),
                patch("nhk_radio.config._ui_settings_path", return_value=target),
            ):
                # グローバル状態をリセット
                config._MIGRATION_DONE = False
                config._migrate_legacy_ui_settings()
            self.assertFalse(legacy.exists())
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), '{"theme": "dark"}')

            # 新パスに既にファイルがある場合は何もしない
            config._MIGRATION_DONE = False
            legacy.write_text("OLD", encoding="utf-8")
            target = config_dir / "ui_settings.json"
            target.write_text("NEW", encoding="utf-8")
            with (
                patch("nhk_radio.config._resolve_cache_root_dir", return_value=cache_dir),
                patch("nhk_radio.config._ui_settings_path", return_value=target),
            ):
                config._migrate_legacy_ui_settings()
            # 新パスが優先される (旧ファイルは触らない)
            self.assertEqual(target.read_text(encoding="utf-8"), "NEW")
            self.assertTrue(legacy.exists())

            # same-path 時は何もしない
            config._MIGRATION_DONE = False
            with (
                patch("nhk_radio.config._resolve_cache_root_dir", return_value=config_dir),
                patch("nhk_radio.config._ui_settings_path", return_value=target),
            ):
                config._migrate_legacy_ui_settings()
            self.assertEqual(target.read_text(encoding="utf-8"), "NEW")

    def test_migrate_legacy_ui_settings_swallows_oserror(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cache_dir = tmp_path / "cache"
            cache_dir.mkdir()
            config_dir = tmp_path / "config"
            config_dir.mkdir()

            legacy = cache_dir / "ui_settings.json"
            legacy.write_text("{}", encoding="utf-8")
            target = config_dir / "ui_settings.json"
            with (
                patch("nhk_radio.config._resolve_cache_root_dir", return_value=cache_dir),
                patch("nhk_radio.config._ui_settings_path", return_value=target),
                patch.object(Path, "replace", side_effect=OSError("boom")),
            ):
                config._MIGRATION_DONE = False
                config._migrate_legacy_ui_settings()  # 例外は握りつぶされる
            self.assertTrue(legacy.exists())
            self.assertFalse(target.exists())

    def test_normalize_search_term_and_history(self):
        self.assertEqual(config._normalize_search_term("　 Hello "), "Hello")
        normalized = config._normalize_search_history([" test ", "ＴＥＳＴ", None, "", "next"])
        self.assertEqual(normalized, ["test", "next"])
        many = [f"item{i}" for i in range(config.SEARCH_HISTORY_LIMIT + 2)]
        self.assertEqual(len(config._normalize_search_history(many)), config.SEARCH_HISTORY_LIMIT)

    def test_load_ui_settings_handles_missing_invalid_and_valid_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                self.assertEqual(config._load_ui_settings(), {})

            settings_path.write_text("{bad json", encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                self.assertEqual(config._load_ui_settings(), {})

            settings_path.write_text("[]", encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
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
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                self.assertEqual(
                    config._load_ui_settings(),
                    {"theme": "dark", "font_size_pt": 18, "program_search_history": ["a"]},
                )

            settings_path.write_text(json.dumps({"font_size_pt": "bad"}), encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                self.assertEqual(config._load_ui_settings(), {})

            settings_path.write_text(json.dumps({"theme": "blue", "program_search_history": "bad"}), encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                self.assertEqual(config._load_ui_settings(), {})

    def test_save_ui_settings_writes_normalized_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "nested" / "ui.json"
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_ui_settings("light", 11, ["a"])

            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(payload, {"theme": "light", "font_size_pt": 11, "program_search_history": ["a"]})


if __name__ == "__main__":
    unittest.main()

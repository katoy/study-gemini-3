"""Tests for configuration and settings."""

import json
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import mock_open, patch

from nhk_radio import config


class ConfigHelpersTest(unittest.TestCase):
    def test_default_paths_cover_windows_and_posix_fallbacks(self):
        class FakeWindowsPath(PureWindowsPath):
            @classmethod
            def home(cls):
                return cls("C:/Users/tester")

        with (
            patch.object(config.sys, "platform", "win32"),
            patch.object(config.os, "name", "nt"),
            patch.dict("os.environ", {"LOCALAPPDATA": "/tmp/local", "APPDATA": "/tmp/roaming"}, clear=True),
            patch("nhk_radio.config.Path", FakeWindowsPath),
        ):
            self.assertEqual(config._default_user_cache_root(), FakeWindowsPath("/tmp/local") / "nhk_radio")
            self.assertEqual(config._default_user_config_root(), FakeWindowsPath("/tmp/roaming") / "nhk_radio")

        with (
            patch.object(config.sys, "platform", "win32"),
            patch.object(config.os, "name", "nt"),
            patch.dict("os.environ", {}, clear=True),
            patch("nhk_radio.config.Path", FakeWindowsPath),
        ):
            self.assertEqual(
                config._default_user_cache_root(),
                FakeWindowsPath("C:/Users/tester") / "AppData" / "Local" / "nhk_radio",
            )
            self.assertEqual(
                config._default_user_config_root(),
                FakeWindowsPath("C:/Users/tester") / "AppData" / "Roaming" / "nhk_radio",
            )

        with (
            patch.object(config.sys, "platform", "linux"),
            patch.object(config.os, "name", "posix"),
            patch.dict("os.environ", {}, clear=True),
            patch.object(Path, "home", return_value=Path("/home/tester")),
            patch("nhk_radio.config._find_project_root", return_value=None),
        ):
            self.assertEqual(config._default_user_cache_root(), Path("/home/tester/.cache/nhk_radio"))
            self.assertEqual(config._default_user_config_root(), Path("/home/tester/.config/nhk_radio"))
            self.assertEqual(config._resolve_cache_root_dir(), Path("/home/tester/.cache/nhk_radio"))
            self.assertEqual(config._resolve_config_root_dir(), Path("/home/tester/.config/nhk_radio"))
            self.assertEqual(config._program_cache_dir(), Path("/home/tester/.cache/nhk_radio/programs"))
            self.assertEqual(config._episode_cache_dir(), Path("/home/tester/.cache/nhk_radio/episodes"))

        with (
            patch.object(config.sys, "platform", "darwin"),
            patch.object(config.os, "name", "posix"),
            patch.dict("os.environ", {}, clear=True),
            patch.object(Path, "home", return_value=Path("/Users/tester")),
            patch("nhk_radio.config._find_project_root", return_value=None),
        ):
            self.assertEqual(config._default_user_cache_root(), Path("/Users/tester/Library/Caches/nhk_radio"))
            self.assertEqual(
                config._default_user_config_root(),
                Path("/Users/tester/Library/Application Support/nhk_radio"),
            )

    def test_find_project_root_returns_none_when_markers_missing(self):
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "is_dir", return_value=False),
        ):
            self.assertIsNone(config._find_project_root())

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

            settings_path.write_text(json.dumps({"font_size_pt": True}), encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                self.assertEqual(config._load_ui_settings(), {"font_size_pt": 9})

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

    def test_save_ui_settings_cleanup_ignores_unlink_error(self):
        settings_path = Path("/tmp/ui.json")
        mocked_file = mock_open()
        with (
            patch("nhk_radio.config._ui_settings_path", return_value=settings_path),
            patch("nhk_radio.config._migrate_legacy_ui_settings"),
            patch("tempfile.mkstemp", return_value=(99, "/tmp/ui.tmp")),
            patch("os.fdopen", mocked_file),
            patch.object(Path, "replace", side_effect=RuntimeError("boom")),
            patch("os.unlink", side_effect=OSError("deny")),
        ):
            self.assertRaises(RuntimeError, config._save_ui_settings, "dark", 12, [])

    def test_save_help_seen_version_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "nested" / "ui.json"
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_help_seen_version(1)

            self.assertTrue(settings_path.exists())
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["help_seen_version"], 1)

    def test_save_help_seen_version_preserves_existing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                # 既存設定を保存
                config._save_ui_settings("light", 11, ["search1", "search2"])
                # help_seen_version を追加
                config._save_help_seen_version(1)

            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["help_seen_version"], 1)
            self.assertEqual(payload["theme"], "light")
            self.assertEqual(payload["font_size_pt"], 11)
            self.assertEqual(payload["program_search_history"], ["search1", "search2"])

    def test_load_ui_settings_reads_help_seen_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text(json.dumps({"help_seen_version": 1}), encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                settings = config._load_ui_settings()

            self.assertEqual(settings.get("help_seen_version"), 1)

    def test_load_ui_settings_ignores_invalid_help_seen_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text(json.dumps({"help_seen_version": "invalid"}), encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                settings = config._load_ui_settings()

            self.assertNotIn("help_seen_version", settings)

    def test_save_ui_settings_with_invalid_json_gracefully_recovers(self):
        """JSON decode error 時は空辞書で初期化。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text("{bad json", encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_ui_settings("dark", 12, ["search"])
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["theme"], "dark")
            self.assertEqual(loaded["font_size_pt"], 12)

    def test_save_ui_settings_with_non_dict_json_recovers(self):
        """JSON が配列など dict でない場合は上書き。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text("[]", encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_ui_settings("light", 11, [])
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["theme"], "light")

    def test_save_help_seen_version_with_invalid_json(self):
        """help_seen_version 保存時 JSON decode error を処理。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text("{invalid", encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_help_seen_version(1)
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["help_seen_version"], 1)

    def test_save_help_seen_version_with_non_dict_json(self):
        """help_seen_version で JSON が dict でない場合を処理。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text('{"existing": "value"}', encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_help_seen_version(5)
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["help_seen_version"], 5)
            self.assertEqual(loaded["existing"], "value")

    def test_save_ui_settings_preserves_help_seen_version(self):
        """UI 設定保存時に既存の help_seen_version を保持。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text(
                json.dumps({"theme": "light", "help_seen_version": 3}),
                encoding="utf-8"
            )
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_ui_settings("dark", 12, [])
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["help_seen_version"], 3)
            self.assertEqual(loaded["theme"], "dark")

    def test_save_ui_settings_with_write_failure_rolls_back(self):
        """一時ファイル書き込み失敗時 roll back。"""
        from contextlib import suppress
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text(
                json.dumps({"existing": "value"}),
                encoding="utf-8"
            )
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path), \
                 patch("nhk_radio.config.os.fdopen", side_effect=OSError("write failed")), \
                 suppress(OSError):
                config._save_ui_settings("dark", 12, [])
            # 既存ファイルが破損していないことを確認
            self.assertEqual(settings_path.read_text(encoding="utf-8"), '{"existing": "value"}')

    def test_save_help_seen_version_with_list_json(self):
        """JSON が list の場合、dict で上書き。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            settings_path.write_text("[]", encoding="utf-8")
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path):
                config._save_help_seen_version(3)
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["help_seen_version"], 3)
            self.assertIsInstance(loaded, dict)

    def test_save_help_seen_version_with_replace_failure(self):
        """ファイル置き換え失敗時は一時ファイルをクリーンアップして例外をスロー。"""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "ui.json"
            with patch("nhk_radio.config._ui_settings_path", return_value=settings_path), \
                 patch.object(Path, "replace", side_effect=OSError("replace failed")), \
                 self.assertRaises(OSError):
                config._save_help_seen_version(1)


class ConfigRootDirTest(unittest.TestCase):
    """_resolve_config_root_dir() のテスト。"""

    def test_resolve_config_root_dir_with_project_root(self):
        """project_root が見つかった場合。"""
        import os
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir()
            with patch("nhk_radio.config._find_project_root", return_value=project_root), \
                 patch.dict(os.environ, {"NHK_RADIO_CONFIG_DIR": ""}):
                result = config._resolve_config_root_dir()
                self.assertEqual(result, project_root / ".config")


if __name__ == "__main__":
    unittest.main()

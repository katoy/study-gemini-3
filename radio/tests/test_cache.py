import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio import cache
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401


class CacheHelpersTest(unittest.TestCase):
    def test_program_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            program = Program(title="A", display_title="A", display_date="----", site_id="S", corner_id="01", url="U", onair_date="20240415")
            with (
                patch("nhk_radio.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio.cache._episode_cache_dir", return_value=base / "episodes"),
                patch.object(cache.time, "time", return_value=1000.0),
            ):
                cache.save_program_cache("language", [program])
                loaded = cache.load_program_cache("language")
        self.assertEqual(loaded[0].display_date, "2024-04-15(月)")

    def test_episode_cache_respects_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            program = Program(title="P", display_title="P", display_date="----", site_id="SITE", corner_id="01", url="U")
            episode = Episode(id="ep1", title="Ep", display_title="Ep", date="20240415", display_date="2024-04-15", broadcast_time="", duration_str="", url="")
            with (
                patch("nhk_radio.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio.cache._episode_cache_dir", return_value=base / "episodes"),
                patch.object(cache.time, "time", side_effect=[1000.0, 2005.0]),
            ):
                cache.save_episode_cache(program, [episode])
                loaded = cache.load_episode_cache(program, ttl_seconds=10)
        self.assertIsNone(loaded)

    def test_low_level_json_cache_helpers_cover_invalid_and_filtered_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            v = cache.CACHE_SCHEMA_VERSION
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text("{bad", encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            # 非 dict の payload (配列) は None
            cache_path.write_text(json.dumps([]), encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            # schema_version 欠落 (旧フォーマット) は None
            cache_path.write_text(json.dumps({"fetched_at": 0, "items": []}), encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            # schema_version 不一致は None
            cache_path.write_text(json.dumps({"schema_version": 999, "fetched_at": 0, "items": []}), encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            # bool は int の派生だが弾く
            cache_path.write_text(
                json.dumps({"schema_version": v, "fetched_at": True, "items": []}), encoding="utf-8"
            )
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text(
                json.dumps({"schema_version": v, "fetched_at": "bad", "items": []}), encoding="utf-8"
            )
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            # items が list でない
            cache_path.write_text(
                json.dumps({"schema_version": v, "fetched_at": 0, "items": "oops"}), encoding="utf-8"
            )
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            with patch.object(cache.time, "time", return_value=100):
                cache_path.write_text(
                    json.dumps({"schema_version": v, "fetched_at": 0, "items": []}), encoding="utf-8"
                )
                self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 10))

                cache_path.write_text(
                    json.dumps({"schema_version": v, "fetched_at": 95, "items": [{"a": 1}, "x"]}),
                    encoding="utf-8",
                )
                self.assertEqual(cache._load_json_ttl_cache(cache_path, "items", 10), [{"a": 1}])

    def test_save_json_cache_injects_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            cache._save_json_cache(cache_path, {"fetched_at": 100, "items": []})
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], cache.CACHE_SCHEMA_VERSION)
            self.assertEqual(payload["fetched_at"], 100)

    def test_save_json_cache_and_cache_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            program = Program(title="P", display_title="P", display_date="----", site_id="SITE", corner_id="01", url="U")
            with (
                patch("nhk_radio.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio.cache._episode_cache_dir", return_value=base / "episodes"),
            ):
                self.assertEqual(cache._program_cache_path(None), base / "programs" / "all.json")
                self.assertEqual(
                    cache._episode_cache_path(program),
                    base / "episodes" / "SITE_01.json",
                )
                target = base / "programs" / "x.json"
                cache._save_json_cache(target, {"ok": True})
                payload = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema_version"], cache.CACHE_SCHEMA_VERSION)
                self.assertTrue(payload["ok"])

    def test_clear_cache_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cache_dir = base / "programs"
            cache_dir.mkdir()
            (cache_dir / "a.json").write_text("{}", encoding="utf-8")
            (cache_dir / "b.txt").write_text("x", encoding="utf-8")
            (cache_dir / "nested").mkdir()
            self.assertEqual(cache._clear_cache_dir(base / "missing"), 0)
            self.assertEqual(cache._clear_cache_dir(cache_dir), 1)
            self.assertTrue((cache_dir / "b.txt").exists())

    def test_clear_all_cache_does_not_remove_ui_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ui_settings = base / "ui_settings.json"
            ui_settings.write_text("{}", encoding="utf-8")
            prog_dir = base / "programs"
            ep_dir = base / "episodes"
            prog_dir.mkdir()
            ep_dir.mkdir()
            (prog_dir / "p.json").write_text("{}", encoding="utf-8")
            with (
                patch("nhk_radio.cache._program_cache_dir", return_value=prog_dir),
                patch("nhk_radio.cache._episode_cache_dir", return_value=ep_dir),
                patch("nhk_radio.cache._ui_settings_path", return_value=ui_settings),
            ):
                removed = cache.clear_all_cache()
            self.assertEqual(removed, 1)
            self.assertTrue(ui_settings.exists())

    def test_clear_ui_settings_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ui_settings = Path(tmp) / "ui_settings.json"
            ui_settings.write_text("{}", encoding="utf-8")
            with patch("nhk_radio.cache._ui_settings_path", return_value=ui_settings):
                removed = cache.clear_ui_settings()
                self.assertEqual(removed, 1)
                self.assertFalse(ui_settings.exists())

    def test_clear_ui_settings_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ui_settings = Path(tmp) / "nonexistent.json"
            with patch("nhk_radio.cache._ui_settings_path", return_value=ui_settings):
                removed = cache.clear_ui_settings()
            self.assertEqual(removed, 0)

    def test_load_program_cache_filters_unknown_legacy_fields(self):
        """旧バージョンで書かれた余剰フィールド (extra_data など) があっても読み込めること。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "programs"
            base.mkdir()
            payload = {
                "schema_version": cache.CACHE_SCHEMA_VERSION,
                "fetched_at": time.time(),
                "genre": "language",
                "programs": [
                    {
                        "title": "A",
                        "display_title": "A",
                        "display_date": "----",
                        "site_id": "S",
                        "corner_id": "01",
                        "url": "U",
                        "onair_date": "20240415",
                        "extra_data": {"legacy": True},  # 現在は存在しないフィールド
                        "unknown_future_field": 42,
                    }
                ],
            }
            (base / "language.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch("nhk_radio.cache._program_cache_dir", return_value=base):
                loaded = cache.load_program_cache("language")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, "A")

    def test_load_episode_cache_filters_unknown_legacy_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "episodes"
            base.mkdir()
            program = Program(title="P", display_title="P", display_date="----", site_id="SITE", corner_id="01", url="U")
            payload = {
                "schema_version": cache.CACHE_SCHEMA_VERSION,
                "fetched_at": time.time(),
                "site_id": "SITE",
                "corner_id": "01",
                "episodes": [
                    {
                        "id": "ep1",
                        "title": "E",
                        "display_title": "E",
                        "date": "20240415",
                        "display_date": "2024-04-15",
                        "broadcast_time": "",
                        "duration_str": "",
                        "url": "",
                        "extra_data": {"legacy": True},
                    }
                ],
            }
            (base / "SITE_01.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch("nhk_radio.cache._episode_cache_dir", return_value=base):
                loaded = cache.load_episode_cache(program)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "ep1")

    def test_clear_ui_settings_logs_warning_on_unlink_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            ui_settings = Path(tmp) / "ui_settings.json"
            ui_settings.write_text("{}", encoding="utf-8")
            with (
                patch("nhk_radio.cache._ui_settings_path", return_value=ui_settings),
                patch.object(Path, "unlink", side_effect=OSError("read-only")),
                self.assertLogs("nhk_radio.cache", level="WARNING") as logs,
            ):
                removed = cache.clear_ui_settings()
            self.assertEqual(removed, 0)
            self.assertTrue(any("UI 設定の削除に失敗" in m for m in logs.output))

    def test_clear_program_and_episode_cache_wrappers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "programs").mkdir()
            (base / "episodes").mkdir()
            (base / "programs" / "p.json").write_text("{}", encoding="utf-8")
            (base / "episodes" / "e.json").write_text("{}", encoding="utf-8")
            with (
                patch("nhk_radio.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio.cache._episode_cache_dir", return_value=base / "episodes"),
            ):
                self.assertEqual(cache.clear_program_cache(), 1)
                self.assertEqual(cache.clear_episode_cache(), 1)


if __name__ == "__main__":
    unittest.main()

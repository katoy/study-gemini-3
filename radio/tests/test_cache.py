import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio import cache
from tests import _support  # noqa: F401


class CacheHelpersTest(unittest.TestCase):
    def test_program_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with (
                patch.object(cache, "PROGRAM_CACHE_DIR", base / "programs"),
                patch.object(cache, "EPISODE_CACHE_DIR", base / "episodes"),
                patch.object(cache.time, "time", return_value=1000.0),
            ):
                cache.save_program_cache("language", [{"title": "A", "onair_date": "20240415"}])
                loaded = cache.load_program_cache("language")
        self.assertEqual(loaded[0]["display_date"], "2024-04-15(月)")
        self.assertEqual(cache._normalize_cached_episode({"date": "20240415"})["display_date"], "2024-04-15(月)")

    def test_episode_cache_respects_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            program = {"site_id": "SITE", "corner_id": "01"}
            with (
                patch.object(cache, "PROGRAM_CACHE_DIR", base / "programs"),
                patch.object(cache, "EPISODE_CACHE_DIR", base / "episodes"),
                patch.object(cache.time, "time", side_effect=[1000.0, 2005.0]),
            ):
                cache.save_episode_cache(program, [{"date": "20240415", "title": "Ep"}])
                loaded = cache.load_episode_cache(program, ttl_seconds=10)
        self.assertIsNone(loaded)

    def test_low_level_json_cache_helpers_cover_invalid_and_filtered_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text("{bad", encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text(json.dumps({"fetched_at": "bad", "items": []}), encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            with patch.object(cache.time, "time", return_value=100):
                cache_path.write_text(json.dumps({"fetched_at": 0, "items": []}), encoding="utf-8")
                self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 10))

                cache_path.write_text(json.dumps({"fetched_at": 95, "items": [{"a": 1}, "x"]}), encoding="utf-8")
                self.assertEqual(cache._load_json_ttl_cache(cache_path, "items", 10), [{"a": 1}])
                self.assertEqual(
                    cache._load_normalized_json_ttl_cache(cache_path, "items", 10, lambda item: {"ok": item["a"]}),
                    [{"ok": 1}],
                )

    def test_save_json_cache_and_cache_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with (
                patch.object(cache, "PROGRAM_CACHE_DIR", base / "programs"),
                patch.object(cache, "EPISODE_CACHE_DIR", base / "episodes"),
            ):
                self.assertEqual(cache._program_cache_path(None), base / "programs" / "all.json")
                self.assertEqual(
                    cache._episode_cache_path({"site_id": "SITE", "corner_id": "01"}),
                    base / "episodes" / "SITE_01.json",
                )
                target = base / "programs" / "x.json"
                cache._save_json_cache(target, {"ok": True})
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

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
                patch.object(cache, "PROGRAM_CACHE_DIR", prog_dir),
                patch.object(cache, "EPISODE_CACHE_DIR", ep_dir),
                patch.object(cache, "UI_SETTINGS_PATH", ui_settings),
            ):
                removed = cache.clear_all_cache()
            self.assertEqual(removed, 1)
            self.assertTrue(ui_settings.exists())

    def test_clear_ui_settings_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ui_settings = Path(tmp) / "ui_settings.json"
            ui_settings.write_text("{}", encoding="utf-8")
            with patch.object(cache, "UI_SETTINGS_PATH", ui_settings):
                removed = cache.clear_ui_settings()
                self.assertEqual(removed, 1)
                self.assertFalse(ui_settings.exists())

    def test_clear_ui_settings_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ui_settings = Path(tmp) / "nonexistent.json"
            with patch.object(cache, "UI_SETTINGS_PATH", ui_settings):
                removed = cache.clear_ui_settings()
            self.assertEqual(removed, 0)

    def test_clear_program_and_episode_cache_wrappers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "programs").mkdir()
            (base / "episodes").mkdir()
            (base / "programs" / "p.json").write_text("{}", encoding="utf-8")
            (base / "episodes" / "e.json").write_text("{}", encoding="utf-8")
            with (
                patch.object(cache, "PROGRAM_CACHE_DIR", base / "programs"),
                patch.object(cache, "EPISODE_CACHE_DIR", base / "episodes"),
            ):
                self.assertEqual(cache.clear_program_cache(), 1)
                self.assertEqual(cache.clear_episode_cache(), 1)


if __name__ == "__main__":
    unittest.main()

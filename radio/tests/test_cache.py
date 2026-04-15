import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _support  # noqa: F401

from nhk_radio import cache


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

    def test_clear_all_cache_removes_ui_settings_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ui_settings = base / "ui_settings.json"
            ui_settings.write_text("{}", encoding="utf-8")
            with (
                patch.object(cache, "PROGRAM_CACHE_DIR", base / "programs"),
                patch.object(cache, "EPISODE_CACHE_DIR", base / "episodes"),
                patch.object(cache, "UI_SETTINGS_PATH", ui_settings),
            ):
                removed = cache.clear_all_cache()
        self.assertEqual(removed, 1)
        self.assertFalse(ui_settings.exists())


if __name__ == "__main__":
    unittest.main()

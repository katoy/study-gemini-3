import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from nhk_radio_web import cache
from nhk_radio_web.types import Episode, Program


class CacheHelpersTest(unittest.TestCase):
    def test_program_cache_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            program = Program(
                title="A", display_title="A", display_date="----",
                site_id="S", corner_id="01", url="U", onair_date="20240415",
            )
            with (
                patch("nhk_radio_web.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio_web.cache._episode_cache_dir", return_value=base / "episodes"),
                patch.object(cache.time, "time", return_value=1000.0),
            ):
                cache.save_program_cache("language", [program])
                loaded = cache.load_program_cache("language")
        self.assertEqual(loaded[0].display_date, "2024-04-15(月)")

    def test_episode_cache_respects_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            program = Program(title="P", display_title="P", display_date="----", site_id="SITE", corner_id="01", url="U")
            episode = Episode(
                id="ep1", title="Ep", display_title="Ep", date="20240415",
                display_date="2024-04-15", broadcast_time="", duration_str="", url="",
            )
            with (
                patch("nhk_radio_web.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio_web.cache._episode_cache_dir", return_value=base / "episodes"),
                patch.object(cache.time, "time", side_effect=[1000.0, 2005.0]),
            ):
                cache.save_episode_cache(program, [episode])
                loaded = cache.load_episode_cache(program, ttl_seconds=10)
        self.assertIsNone(loaded)

    def test_low_level_json_cache_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            v = cache.CACHE_SCHEMA_VERSION
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text("{bad", encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text(json.dumps([]), encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text(json.dumps({"fetched_at": 0, "items": []}), encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text(json.dumps({"schema_version": 999, "fetched_at": 0, "items": []}), encoding="utf-8")
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text(
                json.dumps({"schema_version": v, "fetched_at": True, "items": []}), encoding="utf-8"
            )
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

            cache_path.write_text(
                json.dumps({"schema_version": v, "fetched_at": "bad", "items": []}), encoding="utf-8"
            )
            self.assertIsNone(cache._load_json_ttl_cache(cache_path, "items", 1))

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
                patch("nhk_radio_web.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio_web.cache._episode_cache_dir", return_value=base / "episodes"),
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

    def test_clear_program_and_episode_cache_wrappers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "programs").mkdir()
            (base / "episodes").mkdir()
            (base / "programs" / "p.json").write_text("{}", encoding="utf-8")
            (base / "episodes" / "e.json").write_text("{}", encoding="utf-8")
            with (
                patch("nhk_radio_web.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio_web.cache._episode_cache_dir", return_value=base / "episodes"),
            ):
                self.assertEqual(cache.clear_program_cache(), 1)
                self.assertEqual(cache.clear_episode_cache(), 1)

    def test_clear_all_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "programs").mkdir()
            (base / "episodes").mkdir()
            (base / "programs" / "p.json").write_text("{}", encoding="utf-8")
            (base / "episodes" / "e.json").write_text("{}", encoding="utf-8")
            with (
                patch("nhk_radio_web.cache._program_cache_dir", return_value=base / "programs"),
                patch("nhk_radio_web.cache._episode_cache_dir", return_value=base / "episodes"),
            ):
                removed = cache.clear_all_cache()
            self.assertEqual(removed, 2)

    def test_load_program_cache_filters_unknown_legacy_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "programs"
            base.mkdir()
            payload = {
                "schema_version": cache.CACHE_SCHEMA_VERSION,
                "fetched_at": time.time(),
                "genre": "language",
                "programs": [
                    {
                        "title": "A", "display_title": "A", "display_date": "----",
                        "site_id": "S", "corner_id": "01", "url": "U",
                        "onair_date": "20240415",
                        "extra_data": {"legacy": True},
                        "unknown_future_field": 42,
                    }
                ],
            }
            (base / "language.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch("nhk_radio_web.cache._program_cache_dir", return_value=base):
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
                "episodes": [
                    {
                        "id": "ep1", "title": "E", "display_title": "E",
                        "date": "20240415", "display_date": "2024-04-15",
                        "broadcast_time": "", "duration_str": "", "url": "",
                        "extra_data": {"legacy": True},
                    }
                ],
            }
            (base / "SITE_01.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch("nhk_radio_web.cache._episode_cache_dir", return_value=base):
                loaded = cache.load_episode_cache(program)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].id, "ep1")

    def test_load_program_cache_returns_none_when_cache_missing(self):
        """キャッシュが見つからない場合は None を返す。"""
        with patch("nhk_radio_web.cache._load_json_ttl_cache", return_value=None):
            result = cache.load_program_cache(None)
            self.assertIsNone(result)

    def test_clear_cache_dir_skips_non_files(self):
        """_clear_cache_dir でディレクトリをスキップする。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cache_dir = base / "cache"
            cache_dir.mkdir()
            (cache_dir / "subdir").mkdir()  # ディレクトリ
            self.assertEqual(cache._clear_cache_dir(cache_dir), 0)

    def test_clear_cache_dir_handles_oserror(self):
        """ファイル削除エラーをログし続行する。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cache_dir = base / "cache"
            cache_dir.mkdir()
            (cache_dir / "file.json").write_text("{}")
            # ファイル削除後に OSError を発生させるようにモック
            with patch("pathlib.Path.unlink", side_effect=OSError("Permission denied")):
                # エラーがログされるが、例外は発生しない
                result = cache._clear_cache_dir(cache_dir)
                self.assertEqual(result, 0)

    def test_save_json_cache_handles_exception(self):
        """_save_json_cache で例外が発生した場合、一時ファイルをクリーンアップする。"""
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            # json.dumps に例外を発生させる
            with patch("json.dumps", side_effect=ValueError("Serialization error")):
                with self.assertRaises(ValueError):
                    cache._save_json_cache(cache_path, {"data": "test"})



if __name__ == "__main__":
    unittest.main()

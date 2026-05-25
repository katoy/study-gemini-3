import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio_web import downloads
from nhk_radio_web.types import Episode, Program

PROGRAM = Program(
    title="番組A", display_title="番組A", genre="language", genre_label="語学",
    site_id="SITE", corner_id="01", url="https://example.com/SITE_01",
    display_date="2024-04-15(月)",
)

EPISODE = Episode(
    id="ep-1", date="20240415", title="第1回", display_title="第1回",
    display_date="2024-04-15", broadcast_time="", duration_str="",
    url="https://example.com/ep1",
)


class DownloadHelpersTest(unittest.TestCase):
    def test_program_storage_helpers(self):
        output_dir = Path("/tmp/output")
        self.assertEqual(downloads._program_output_dir(output_dir, PROGRAM), output_dir / "SITE_01")
        self.assertEqual(
            downloads._program_storage_id(
                Program(title="番/組", display_title="", display_date="", site_id="", corner_id="", url="")
            ),
            "番_組",
        )
        self.assertEqual(
            downloads._program_storage_title(
                Program(title="", display_title="表示", display_date="", site_id="", corner_id="", url="")
            ),
            "表示",
        )
        self.assertEqual(
            downloads._program_storage_titles(
                Program(title="A", display_title="A", site_id="SITE", corner_id="01", display_date="", url="")
            ),
            ["A", "SITE_01"],
        )

    def test_legacy_search_dirs(self):
        legacy_dirs = downloads._legacy_program_output_dirs(Path("/tmp/out"), PROGRAM)
        self.assertIn(Path("/tmp/out/語学/番組A"), legacy_dirs)
        search_dirs = downloads._program_search_dirs(Path("/tmp/out"), PROGRAM)
        self.assertEqual(search_dirs[0], Path("/tmp/out/SITE_01"))

    def test_episode_identity_and_filename_templates(self):
        self.assertEqual(
            downloads._episode_output_identity(PROGRAM, EPISODE),
            (["番組A", "SITE_01"], "第1回", "20240415"),
        )
        self.assertEqual(
            downloads._program_filename_template(PROGRAM),
            "%(upload_date)s_番組A_%(title)s.%(ext)s",
        )
        self.assertEqual(
            downloads._program_filename_template(PROGRAM, max_items=True),
            "%(playlist_index)s_%(upload_date)s_番組A_%(title)s.%(ext)s",
        )
        self.assertEqual(
            downloads._episode_key(
                Episode(id="", date="20240415", title="第1回", display_title="", display_date="", broadcast_time="", duration_str="", url="")
            ),
            "20240415:第1回",
        )

    def test_load_download_manifest_handles_invalid_and_legacy_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            legacy_dir = output_dir / "語学" / "番組A"
            program_dir.mkdir(parents=True, exist_ok=True)
            legacy_dir.mkdir(parents=True, exist_ok=True)
            (program_dir / ".downloaded.json").write_text("{bad", encoding="utf-8")
            (legacy_dir / ".downloaded.json").write_text(
                json.dumps({"downloaded": ["ep-1"], "paths": {"ep-1": "20240415_番組A_第1回.mp3"}}),
                encoding="utf-8",
            )
            saved_paths = downloads._load_download_manifest(PROGRAM, output_dir)
        self.assertEqual(saved_paths["ep-1"], "20240415_番組A_第1回.mp3")

    def test_episode_output_pattern_matching_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            program_dir = Path(tmp)
            preferred = program_dir / "20240415_番組A_第1回.mp3"
            other = program_dir / "001_20240415_番組A_第1回.m4a"
            partial = program_dir / "20240415_番組A_第1回.part"
            preferred.write_text("x", encoding="utf-8")
            other.write_text("x", encoding="utf-8")
            partial.write_text("x", encoding="utf-8")

            patterns = downloads._episode_output_patterns(PROGRAM, EPISODE)
            self.assertIn("20240415_番組A_第1回.*", patterns)
            self.assertTrue(downloads._episode_output_matches(preferred, PROGRAM, EPISODE))
            self.assertFalse(downloads._episode_output_matches(partial, PROGRAM, EPISODE))
            self.assertEqual(downloads._episode_output_candidates(program_dir, PROGRAM, EPISODE)[0], preferred)

    def test_episode_output_matches_date_and_title_conditions(self):
        """_episode_output_matches の日付とタイトル条件をカバー。"""
        with tempfile.TemporaryDirectory() as tmp:
            program_dir = Path(tmp)

            # 日付が異なるファイル → False
            wrong_date = program_dir / "20240101_番組A_第1回.mp3"
            wrong_date.write_text("x")
            self.assertFalse(downloads._episode_output_matches(wrong_date, PROGRAM, EPISODE))

            # エピソードタイトルが異なるファイル → False
            wrong_title = program_dir / "20240415_番組A_別エピ.mp3"
            wrong_title.write_text("x")
            self.assertFalse(downloads._episode_output_matches(wrong_title, PROGRAM, EPISODE))

            # 正しいファイル → True
            correct = program_dir / "20240415_番組A_第1回.mp3"
            correct.write_text("x")
            self.assertTrue(downloads._episode_output_matches(correct, PROGRAM, EPISODE))

    def test_get_cached_glob_files_error_handling(self):
        """_get_cached_glob_files の OSError ハンドリング。"""
        # ディレクトリが存在しない場合
        nonexistent = Path("/nonexistent/directory")
        result = downloads._get_cached_glob_files(nonexistent)
        self.assertEqual(result, [])

    def test_episode_output_helpers_without_date(self):
        episode = Episode(
            id="", title="第1回", display_title="第1回", date="", display_date="",
            broadcast_time="", duration_str="", url="",
        )
        patterns = downloads._episode_output_patterns(PROGRAM, episode)
        self.assertIn("番組A_第1回.*", patterns)

        with tempfile.TemporaryDirectory() as tmp:
            program_dir = Path(tmp)
            nested = program_dir / "001_番組A_第1回.mp3"
            direct = program_dir / "番組A_第1回.mp3"
            nested.write_text("x", encoding="utf-8")
            direct.write_text("x", encoding="utf-8")
            self.assertTrue(downloads._episode_output_matches(nested, PROGRAM, episode))
            self.assertEqual(downloads._episode_output_candidates(program_dir, PROGRAM, episode)[0], direct)

    def test_mark_and_resolve_downloaded_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            file_path = program_dir / "20240415_番組A_第1回.mp3"
            file_path.write_text("dummy", encoding="utf-8")

            downloads.mark_episode_downloaded(output_dir, PROGRAM, EPISODE, file_path)

            self.assertTrue(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))
            self.assertEqual(downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE), file_path)

    def test_mark_episode_downloaded_stores_absolute_path_outside_program_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            outside_path = Path(tmp) / "outside.mp3"
            outside_path.write_text("dummy", encoding="utf-8")

            downloads.mark_episode_downloaded(output_dir, PROGRAM, EPISODE, outside_path)

            manifest = json.loads((output_dir / "SITE_01" / ".downloaded.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["paths"]["ep-1"], str(outside_path))

    def test_get_cached_glob_files_returns_empty_on_iterdir_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            downloads._clear_file_scan_cache()
            with patch.object(Path, "iterdir", side_effect=OSError("denied")):
                result = downloads._get_cached_glob_files(target)
            self.assertEqual(result, [])

    def test_cleanup_partial_episode_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            partial = program_dir / "20240415_番組A_第1回.mp3.part"
            ytdl = program_dir / "20240415_番組A_第1回.mp3.ytdl"
            partial.write_text("partial", encoding="utf-8")
            ytdl.write_text("partial", encoding="utf-8")

            downloads.cleanup_partial_episode_files(output_dir, PROGRAM, EPISODE)

            self.assertFalse(partial.exists())
            self.assertFalse(ytdl.exists())

    def test_download_manifest_lock_is_shared_per_manifest(self):
        lock_a = downloads._download_manifest_lock(PROGRAM, Path("/tmp/output"))
        lock_b = downloads._download_manifest_lock(PROGRAM, Path("/tmp/output"))
        self.assertIs(lock_a, lock_b)
        self.assertTrue(hasattr(lock_a, "acquire"))

    def test_find_episode_downloaded_path_supports_legacy_and_saved_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            legacy_dir = output_dir / "語学" / "番組A"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            legacy_file = legacy_dir / "20240415_番組A_第1回.mp3"
            legacy_file.write_text("dummy", encoding="utf-8")

            resolved = downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE)
            self.assertEqual(resolved, legacy_file)

            manifest_dir = output_dir / "SITE_01"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            (manifest_dir / ".downloaded.json").write_text(
                json.dumps({"downloaded": ["ep-1"], "paths": {"ep-1": "saved.mp3"}}),
                encoding="utf-8",
            )
            saved = manifest_dir / "saved.mp3"
            saved.write_text("x", encoding="utf-8")
            legacy_file.unlink()
            self.assertEqual(downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE), saved)

    def test_mark_episode_downloaded_returns_false_on_save_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            file_path = program_dir / "20240415_番組A_第1回.mp3"
            file_path.write_text("dummy", encoding="utf-8")

            with (
                patch.object(Path, "write_text", side_effect=OSError("disk full")),
                self.assertLogs("nhk_radio_web.downloads", level="WARNING") as logs,
            ):
                result = downloads.mark_episode_downloaded(output_dir, PROGRAM, EPISODE, file_path)
            self.assertFalse(result)
            self.assertTrue(any("ダウンロード履歴の保存に失敗" in m for m in logs.output))

    def test_sync_primary_candidate_updates_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            manifest_dir = output_dir / "SITE_01"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            primary = manifest_dir / "20240415_番組A_第1回.mp3"
            primary.write_text("x", encoding="utf-8")
            (manifest_dir / ".downloaded.json").write_text(
                json.dumps({"downloaded": ["ep-1"], "paths": {"ep-1": "old.mp3"}}),
                encoding="utf-8",
            )
            resolved = downloads.sync_episode_download_history(output_dir, PROGRAM, EPISODE)
            self.assertEqual(resolved, primary)
            manifest = json.loads((manifest_dir / ".downloaded.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["paths"]["ep-1"], "20240415_番組A_第1回.mp3")


if __name__ == "__main__":
    unittest.main()

import tempfile
import threading
import unittest
from pathlib import Path

from tests import _support  # noqa: F401

from nhk_radio import downloads


PROGRAM = {
    "title": "番組A",
    "display_title": "番組A",
    "genre": "language",
    "genre_label": "語学",
}

EPISODE = {
    "id": "ep-1",
    "date": "20240415",
    "title": "第1回",
    "display_title": "第1回",
}


class DownloadHelpersTest(unittest.TestCase):
    def test_program_filename_template(self):
        self.assertEqual(
            downloads._program_filename_template(PROGRAM),
            "%(upload_date)s_番組A_%(title)s.%(ext)s",
        )

    def test_mark_and_resolve_downloaded_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            file_path = program_dir / "20240415_番組A_第1回.mp3"
            file_path.write_text("dummy", encoding="utf-8")

            downloads.mark_episode_downloaded(output_dir, PROGRAM, EPISODE, file_path)

            self.assertTrue(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))
            self.assertEqual(downloads.resolve_episode_downloaded_path(output_dir, PROGRAM, EPISODE), file_path)

    def test_cleanup_partial_episode_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            partial = program_dir / "20240415_番組A_第1回.mp3.part"
            partial.write_text("partial", encoding="utf-8")

            downloads.cleanup_partial_episode_files(output_dir, PROGRAM, EPISODE)

            self.assertFalse(partial.exists())

    def test_download_manifest_lock_is_shared_per_manifest(self):
        lock_a = downloads._download_manifest_lock(PROGRAM, Path("/tmp/output"))
        lock_b = downloads._download_manifest_lock(PROGRAM, Path("/tmp/output"))

        self.assertIs(lock_a, lock_b)
        self.assertTrue(hasattr(lock_a, "acquire"))
        self.assertTrue(hasattr(lock_a, "release"))


if __name__ == "__main__":
    unittest.main()

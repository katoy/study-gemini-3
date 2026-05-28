import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nhk_radio import downloads
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401

PROGRAM = Program(
    title="番組A",
    display_title="番組A",
    genre="language",
    genre_label="語学",
    site_id="SITE",
    corner_id="01",
    url="https://example.com/SITE_01",
    display_date="2024-04-15(月)",
)

EPISODE = Episode(
    id="ep-1",
    date="20240415",
    title="第1回",
    display_title="第1回",
    display_date="2024-04-15",
    broadcast_time="",
    duration_str="",
    url="https://example.com/ep1",
)


class DownloadHelpersTest(unittest.TestCase):
    def test_program_storage_helpers(self):
        output_dir = Path("/tmp/output")
        self.assertEqual(downloads._program_output_dir(output_dir, PROGRAM), output_dir / "SITE_01")
        self.assertEqual(downloads._program_storage_id(Program(title="番/組", display_title="", display_date="", site_id="", corner_id="", url="")), "番_組")
        self.assertEqual(downloads._program_storage_title(Program(title="", display_title="表示", display_date="", site_id="", corner_id="", url="")), "表示")
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

        multi_genre_program = Program(
            title="ラジオ文芸館",
            display_title="ラジオ文芸館",
            display_date="2024-04-15(月)",
            site_id="SITE2",
            corner_id="01",
            url="https://example.com/SITE2_01",
            genre="hobby",
            genre_label="新番組",
            genres=("hobby",),
            genre_labels=("新番組", "趣味/教養"),
        )
        multi_dirs = downloads._legacy_program_output_dirs(Path("/tmp/out"), multi_genre_program)
        self.assertIn(Path("/tmp/out/新番組/ラジオ文芸館"), multi_dirs)
        self.assertIn(Path("/tmp/out/趣味_教養/ラジオ文芸館"), multi_dirs)

    def test_episode_identity_and_filename_templates(self):
        self.assertEqual(
            downloads._episode_output_identity(PROGRAM, EPISODE), (["番組A", "SITE_01"], "第1回", "20240415")
        )
        self.assertEqual(downloads._program_filename_template(PROGRAM), "%(upload_date)s_番組A_%(title)s.%(ext)s")
        self.assertEqual(
            downloads._program_filename_template(PROGRAM, max_items=True),
            "%(playlist_index)s_%(upload_date)s_番組A_%(title)s.%(ext)s",
        )
        self.assertEqual(downloads._episode_key(Episode(id="", date="20240415", title="第1回", display_title="", display_date="", broadcast_time="", duration_str="", url="")), "20240415:第1回")

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

    def test_episode_output_helpers_without_date_and_manifest_only_cases(self):
        episode = Episode(id="", title="第1回", display_title="第1回", date="", display_date="", broadcast_time="", duration_str="", url="")
        patterns = downloads._episode_output_patterns(PROGRAM, episode)
        self.assertIn("番組A_第1回.*", patterns)

        with tempfile.TemporaryDirectory() as tmp:
            program_dir = Path(tmp)
            nested = program_dir / "001_番組A_第1回.mp3"
            direct = program_dir / "番組A_第1回.mp3"
            nested.write_text("x", encoding="utf-8")
            direct.write_text("x", encoding="utf-8")
            self.assertTrue(downloads._episode_output_matches(nested, PROGRAM, episode))
            wrong = program_dir / "other.mp3"
            wrong.write_text("x", encoding="utf-8")
            self.assertEqual(downloads._episode_output_candidates(program_dir, PROGRAM, episode)[0], direct)
            self.assertFalse(downloads._episode_output_matches(wrong, PROGRAM, episode))

        with tempfile.TemporaryDirectory() as tmp:
            program_dir = Path(tmp)
            dated = program_dir / "20240415_番組A_第1回.mp3"
            mismatch = program_dir / "20240415_番組A_別回.mp3"
            dated.write_text("x", encoding="utf-8")
            mismatch.write_text("x", encoding="utf-8")
            self.assertFalse(downloads._episode_output_matches(mismatch, PROGRAM, EPISODE))
            self.assertEqual(downloads._episode_output_candidates(program_dir, PROGRAM, EPISODE), [dated])

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            manifest_dir = output_dir / "SITE_01"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            (manifest_dir / ".downloaded.json").write_text(
                json.dumps({"downloaded": ["ep-1"], "paths": {}}), encoding="utf-8"
            )
            # 修正後: ファイルが実在しない場合は False を返す
            self.assertFalse(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))
            self.assertIsNone(downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE))

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = output_dir / "SITE_01"
            program_dir.mkdir(parents=True, exist_ok=True)
            found = program_dir / "20240415_番組A_第1回.mp3"
            found.write_text("x", encoding="utf-8")
            self.assertTrue(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))
            self.assertEqual(downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE), found)

        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(downloads.find_episode_downloaded_path(Path(tmp), PROGRAM, EPISODE))

    def test_sync_primary_candidate_updates_manifest_when_relative_path_changes(self):
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

    def test_episode_output_candidates_skips_duplicate_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            program_dir = Path(tmp)
            file_path = program_dir / "dup.mp3"
            file_path.write_text("x", encoding="utf-8")
            with (
                patch.object(downloads, "_episode_output_patterns", return_value=["*.mp3", "*.mp3"]),
                patch.object(downloads, "_episode_output_matches", return_value=True),
            ):
                candidates = downloads._episode_output_candidates(program_dir, PROGRAM, EPISODE)
            self.assertEqual(candidates, [file_path])

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

    def test_get_cached_glob_files_returns_empty_on_stat_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            downloads._clear_file_scan_cache()
            with (
                patch.object(Path, "is_dir", return_value=True),
                patch.object(Path, "stat", side_effect=OSError("denied")),
            ):
                result = downloads._get_cached_glob_files(target)
            self.assertEqual(result, [])

    def test_cleanup_partial_episode_files_swallows_iterdir_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            # 例外が発生しても呼び出し元に伝播しないこと
            with patch.object(Path, "iterdir", side_effect=OSError("denied")):
                downloads.cleanup_partial_episode_files(output_dir, PROGRAM, EPISODE)

    def test_mark_episode_downloaded_returns_false_on_save_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)
            file_path = program_dir / "20240415_番組A_第1回.mp3"
            file_path.write_text("dummy", encoding="utf-8")

            # アトミック書き込みで tempfile.mkstemp をモック
            with (
                patch("tempfile.mkstemp", side_effect=OSError("disk full")),
                self.assertLogs("nhk_radio.downloads", level="WARNING") as logs,
            ):
                result = downloads.mark_episode_downloaded(output_dir, PROGRAM, EPISODE, file_path)
            self.assertFalse(result)
            self.assertTrue(any("ダウンロード履歴の保存に失敗" in m for m in logs.output))

    def test_find_episode_downloaded_path_supports_legacy_title_based_folder_and_saved_paths(self):
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

            (manifest_dir / ".downloaded.json").write_text(
                json.dumps({"downloaded": ["ep-1"], "paths": {"ep-1": "missing.mp3"}}),
                encoding="utf-8",
            )
            self.assertIsNone(downloads.find_episode_downloaded_path(output_dir, PROGRAM, EPISODE))

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
        self.assertTrue(hasattr(lock_a, "release"))

    def test_load_download_manifest_error(self):
        program = Program(site_id="SITE", corner_id="01", title="番組", display_title="番組", display_date="----", url="U")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            prog_dir = out / "SITE_01"
            prog_dir.mkdir()
            manifest = prog_dir / ".downloaded.json"
            manifest.write_text("{bad", encoding="utf-8")

            with patch("nhk_radio.downloads.logger") as logger_mock:
                paths = downloads._load_download_manifest(program, out)
                self.assertEqual(paths, {})
                logger_mock.debug.assert_called()

    def test_episode_output_patterns_no_date(self):
        program = Program(site_id="SITE", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episode = Episode(id="", title="E", display_title="E", date="", display_date="", broadcast_time="", duration_str="", url="")
        patterns = downloads._episode_output_patterns(program, episode)
        self.assertIn("P_E.*", patterns)

    def test_episode_output_matches_edge_cases(self):
        program = Program(site_id="SITE", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episode = Episode(id="", title="E", display_title="E", date="20240415", display_date="20240415", broadcast_time="", duration_str="", url="")

        # タイトル不一致
        path = Path("20240415_OTHER_E.mp3")
        with patch("pathlib.Path.is_file", return_value=True):
            self.assertFalse(downloads._episode_output_matches(path, program, episode))

    def test_episode_output_patterns_multi_title(self):
        program = Program(site_id="SITE", corner_id="01", title="P", display_title="D", display_date="----", url="U")
        episode = Episode(id="", title="E", display_title="E", date="2024", display_date="2024", broadcast_time="", duration_str="", url="")
        patterns = downloads._episode_output_patterns(program, episode)
        self.assertIn("2024_P_E.*", patterns)
        self.assertIn("2024_D_E.*", patterns)

    def test_episode_output_matches_no_date_in_episode(self):
        program = Program(site_id="SITE", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episode = Episode(id="", title="E", display_title="E", date="", display_date="", broadcast_time="", duration_str="", url="")
        path = Path("P_E.mp3")
        with patch("pathlib.Path.is_file", return_value=True):
            self.assertTrue(downloads._episode_output_matches(path, program, episode))

    def test_find_episode_downloaded_path_missing_file(self):
        program = Program(site_id="SITE", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episode = Episode(id="ep1", title="E", display_title="E", date="", display_date="", broadcast_time="", duration_str="", url="")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            prog_dir = out / "SITE_01"
            prog_dir.mkdir()
            manifest = prog_dir / ".downloaded.json"
            manifest.write_text(json.dumps({"downloaded": ["ep1"], "paths": {"ep1": "missing.mp3"}}), encoding="utf-8")

            # マニフェストにはあるがファイルがない
            self.assertIsNone(downloads.find_episode_downloaded_path(out, program, episode))

    def test_download_progress_formatters_and_command_builders(self):
        self.assertEqual(downloads._format_download_percent(None), "--%")
        self.assertEqual(downloads._format_download_percent(10.0), "10%")
        self.assertEqual(downloads._format_download_percent(10.26), "10.3%")
        self.assertEqual(downloads._format_download_eta("00:10"), "残り 00:10")
        self.assertEqual(downloads._format_download_eta(None), "残り --:--")
        self.assertEqual(downloads._parse_yt_dlp_progress(""), (None, None, None))
        self.assertEqual(downloads._parse_yt_dlp_progress("[ExtractAudio] Destination"), (100.0, None, "変換中..."))
        self.assertEqual(
            downloads._parse_yt_dlp_progress("[download]  53.2% of 1.0MiB at 1MiB/s ETA 00:03"),
            (53.2, "00:03", "ダウンロード中..."),
        )
        self.assertEqual(
            downloads._parse_yt_dlp_progress("[download]  100% of 1.0MiB at 1MiB/s"),
            (100.0, None, "変換中..."),
        )
        self.assertEqual(downloads._parse_yt_dlp_progress("noise"), (None, None, None))
        self.assertIn("--newline", downloads._download_episode_command("https://e", Path("/tmp"), "%(title)s.%(ext)s"))
        self.assertIn(
            "--playlist-end",
            downloads._yt_dlp_command("https://e", "x", audio_only=False, no_playlist=False, max_items=3),
        )
        self.assertIn("--no-playlist", downloads._yt_dlp_command("https://e", "x", audio_only=False, no_playlist=True))
        # AES-128 暗号化 HLS の ffmpeg muxer 失敗を防ぐため --hls-use-mpegts が必須
        self.assertIn(
            "--hls-use-mpegts", downloads._download_episode_command("https://e", Path("/tmp"), "%(title)s.%(ext)s")
        )
        self.assertIn(
            "--hls-use-mpegts", downloads._yt_dlp_command("https://e", "x", audio_only=True, no_playlist=True)
        )

    def test_yt_dlp_command_contains_concurrency_and_timeout_flags(self):
        """yt-dlp コマンドが HLS フラグメント並列化とソケットタイムアウトオプションを含む"""
        from nhk_radio.constants import YTDLP_CONCURRENT_FRAGMENTS, YTDLP_SOCKET_TIMEOUT

        cmd = downloads._yt_dlp_command("https://e", "x", audio_only=False, no_playlist=True)
        self.assertIn("--concurrent-fragments", cmd)
        self.assertIn(str(YTDLP_CONCURRENT_FRAGMENTS), cmd)
        self.assertIn("--socket-timeout", cmd)
        self.assertIn(str(YTDLP_SOCKET_TIMEOUT), cmd)

    def test_is_episode_downloaded_false_when_nothing_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(downloads.is_episode_downloaded(Path(tmp), PROGRAM, EPISODE))

    def test_is_episode_downloaded_reflects_physical_file_deletion_regression(self):
        """Finderなどでファイルが消された場合に[済]マークが消えることを保証する回帰テスト"""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)

            # 1. ファイルを作成し、ダウンロード済みとしてマーク
            file_path = program_dir / "20240415_番組A_第1回.mp3"
            file_path.write_text("dummy", encoding="utf-8")
            downloads.mark_episode_downloaded(output_dir, PROGRAM, EPISODE, file_path)

            self.assertTrue(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))

            # 2. 物理ファイルを削除
            file_path.unlink()

            # 3. 判定が False に戻ることを確認 (キャッシュクリアと実在確認の合わせ技)
            self.assertFalse(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE),
                             "物理ファイル削除後は、マニフェストに記録があっても False を返すべき")

    def test_is_episode_downloaded_cache_invalidation(self):
        """同一プロセス内でファイルが削除された際、キャッシュに邪魔されず検知できるか"""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            program_dir = downloads._program_output_dir(output_dir, PROGRAM)
            program_dir.mkdir(parents=True, exist_ok=True)

            # 命名規則に沿ったファイルを作成
            file_path = program_dir / "20240415_番組A_第1回.mp3"
            file_path.write_text("x", encoding="utf-8")

            # 1回目の呼び出しでキャッシュが作成され、True が返るべき
            self.assertTrue(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))

            # ファイル削除
            file_path.unlink()

            # 2回目の呼び出しでキャッシュが効いていると True になってしまうが、
            # 修正後は _clear_file_scan_cache() が呼ばれるため False になるはず
            self.assertFalse(downloads.is_episode_downloaded(output_dir, PROGRAM, EPISODE))

    def test_open_downloaded_folder_success_macos(self):
        """open_downloaded_folder() が macOS で正常に動作することをテスト。"""
        with tempfile.TemporaryDirectory() as tmp:
            folder_path = Path(tmp)
            with patch("sys.platform", "darwin"), patch("subprocess.run") as run_mock:
                result = downloads.open_downloaded_folder(folder_path)
                self.assertTrue(result)
                run_mock.assert_called_once_with(["open", str(folder_path)], check=True)

    def test_open_downloaded_folder_success_windows(self):
        """open_downloaded_folder() が Windows で正常に動作することをテスト。"""
        with tempfile.TemporaryDirectory() as tmp:
            folder_path = Path(tmp)
            with patch("sys.platform", "win32"), patch("subprocess.run") as run_mock:
                result = downloads.open_downloaded_folder(folder_path)
                self.assertTrue(result)
                run_mock.assert_called_once_with(["explorer", str(folder_path)], check=True)

    def test_open_downloaded_folder_success_linux(self):
        """open_downloaded_folder() が Linux で正常に動作することをテスト。"""
        with tempfile.TemporaryDirectory() as tmp:
            folder_path = Path(tmp)
            with patch("sys.platform", "linux"), patch("subprocess.run") as run_mock:
                result = downloads.open_downloaded_folder(folder_path)
                self.assertTrue(result)
                run_mock.assert_called_once_with(["xdg-open", str(folder_path)], check=True)

    def test_open_downloaded_folder_nonexistent(self):
        """open_downloaded_folder() が存在しないフォルダで False を返すことをテスト。"""
        nonexistent = Path("/nonexistent/path/12345")
        result = downloads.open_downloaded_folder(nonexistent)
        self.assertFalse(result)

    def test_open_downloaded_folder_command_error(self):
        """open_downloaded_folder() がコマンド失敗時に False を返すことをテスト。"""
        import subprocess
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("sys.platform", "darwin"),
            patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "open")),
        ):
            folder_path = Path(tmp)
            result = downloads.open_downloaded_folder(folder_path)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

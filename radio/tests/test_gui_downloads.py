import queue
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from nhk_radio.gui.download_manager import DownloadManager
from nhk_radio.gui.downloads import GuiDownloadsMixin
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401


class MockGui(GuiDownloadsMixin):
    def __init__(self):
        self.root = MagicMock()
        self.active_download_rows = {}
        self.download_result_queue = queue.Queue()
        self.download_polling = False
        self.loading = False
        self.displayed_episode_map = {}
        self.displayed_program = None
        self.episodes_cache = {}
        self.output_dir = Path("/tmp/radio")
        self.audio_only = True
        self._palette = {"surface": "white", "row_odd": "gray", "dl_even": "blue", "dl_odd": "lightblue"}

        # Managers (Composition)
        self.data_manager = MagicMock()
        self.download_manager = MagicMock()

        # UI vars
        self.status_var = MagicMock()
        self.episode_message_var = MagicMock()
        self.fetch_button_var = MagicMock()
        self.progress_text_var = MagicMock()

        # UI widgets
        self.fetch_button = MagicMock()
        self.download_jobs_canvas = MagicMock()
        self.download_jobs_inner = MagicMock()
        self.episode_tree = MagicMock()

    def _selected_program(self):
        return self.displayed_program

    def _update_program_overview(self, *args):
        pass

    def _show_episodes(self, *args, **kwargs):
        pass

    def _refresh_downloaded_column(self, *args):
        pass

    def _reset_ui_state_after_cache_clear(self):
        pass

    def _cached_episodes_for(self, program):
        return []


class GuiDownloadsTest(unittest.TestCase):
    def setUp(self):
        self.gui = MockGui()

    def test_update_download_row_progress(self):
        episode_key = "test_ep"
        row = {
            "state": "running", "percent_var": MagicMock(), "status_var": MagicMock(),
            "progress": MagicMock(), "progress_meta_var": MagicMock(),
        }
        self.gui.active_download_rows[episode_key] = row
        self.gui._update_download_row_progress(episode_key, percent=50.5, eta="00:10", status_text="Downloading")
        update_func = self.gui.root.after.call_args[0][1]
        update_func()
        row["percent_var"].set.assert_called_with("50.5%")

    def test_set_loading(self):
        self.gui._set_loading(True)
        self.assertTrue(self.gui.loading)
        self.gui.fetch_button_var.set.assert_called_with("取得中...")

    def test_add_download_row(self):
        program = Program(site_id="S1", corner_id="01", title="Prog", display_title="Prog", display_date="----", url="U")
        episode = Episode(id="E1", title="Ep", display_title="Ep", date="2024", display_date="2024", broadcast_time="", duration_str="", url="http://")
        with patch.object(self.gui, "_create_download_job_widgets") as create_mock:
            create_mock.return_value = {
                "frame": MagicMock(), "progress": MagicMock(), "percent_var": MagicMock(),
                "progress_meta_var": MagicMock(), "status_var": MagicMock(),
                "action_button": MagicMock(),
            }
            self.gui._add_download_row(program, episode)
            self.assertIn("E1", self.gui.active_download_rows)

    def test_finish_download_row(self):
        episode_key = "test_ep"
        row = {"state": "running", "progress": MagicMock(), "percent_var": MagicMock(),
               "progress_meta_var": MagicMock(), "status_var": MagicMock(), "action_button": MagicMock()}
        self.gui.active_download_rows[episode_key] = row
        self.gui._finish_download_row(episode_key, "完了")
        self.assertEqual(row["state"], "done")

    def test_on_cancel_all(self):
        self.gui._on_cancel_all()
        self.gui.download_manager.cancel_all.assert_called_once()

    def test_poll_download_result_progress(self):
        episode_key = "test_ep"
        row = {"state": "running", "percent_var": MagicMock(), "progress": MagicMock(),
               "progress_meta_var": MagicMock(), "status_var": MagicMock()}
        self.gui.active_download_rows[episode_key] = row
        self.gui.download_polling = True
        # 新しい形式: (kind, key, program, episode, data)
        self.gui.download_result_queue.put(("progress", episode_key, None, None, (50.0, "00:10", "Working")))
        with patch.object(self.gui, "_update_download_row_progress") as update_mock:
            self.gui._poll_download_result()
            update_mock.assert_called_with(episode_key, percent=50.0, eta="00:10", status_text="Working")

    def test_poll_download_result_done(self):
        episode_key = "test_ep"
        row = {"state": "running", "progress": MagicMock(), "percent_var": MagicMock(),
               "progress_meta_var": MagicMock(), "status_var": MagicMock(), "action_button": MagicMock()}
        self.gui.active_download_rows[episode_key] = row
        self.gui.download_polling = True
        program = Program(site_id="S1", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episode = Episode(id="E1", title="Ep", display_title="Ep", date="2024", display_date="2024", broadcast_time="", duration_str="", url="")
        self.gui.download_result_queue.put(("done_one", episode_key, program, episode, "/tmp/out.mp3"))
        with patch.object(self.gui, "_refresh_downloaded_column"):
            self.gui._poll_download_result()
            self.assertEqual(row["state"], "done")

    def test_update_download_summary(self):
        self.gui.active_download_rows = {"k1": {"state": "running"}}
        self.gui._update_download_summary()
        self.gui.progress_text_var.set.assert_called_with("実行中: 1 / 全体: 1")

    def test_reflow_download_rows(self):
        row_frame = MagicMock()
        self.gui.active_download_rows = {"k1": {"frame": row_frame, "state": "done"}}
        self.gui._reflow_download_rows()
        row_frame.grid.assert_called_once()

    def test_remove_download_row(self):
        row_frame = MagicMock()
        self.gui.active_download_rows = {"k1": {"frame": row_frame, "state": "done"}}
        self.gui._remove_download_row("k1")
        row_frame.destroy.assert_called_once()
        self.assertNotIn("k1", self.gui.active_download_rows)

    def test_create_download_job_widgets(self):
        episode = Episode(id="E1", title="E", display_title="E", date="2024", display_date="2024", broadcast_time="", duration_str="", url="")
        with (
            patch("nhk_radio.gui.downloads.ttk.Frame"),
            patch("nhk_radio.gui.downloads.ttk.Label"),
            patch("nhk_radio.gui.downloads.tk.StringVar"),
            patch("nhk_radio.gui.downloads.ttk.Button"),
            patch("nhk_radio.gui.downloads.ttk.Progressbar")
        ):
            widgets = self.gui._create_download_job_widgets(0, episode, "k1")
            self.assertIn("frame", widgets)

    def test_clear_cache(self):
        with patch("nhk_radio.gui.downloads.clear_all_cache"):
            self.gui._clear_cache()
            self.gui.status_var.set.assert_any_call("キャッシュを削除中...")
            # 完了通知
            self.gui._on_cache_cleared_success()
            self.gui.status_var.set.assert_any_call("キャッシュを削除しました。")


class DownloadManagerTest(unittest.TestCase):
    def setUp(self):
        self.program = Program(site_id="S1", corner_id="01", title="Prog", display_title="Prog", display_date="----", url="U")
        self.episode = Episode(
            id="E1",
            title="Ep",
            display_title="Ep",
            date="2024",
            display_date="2024",
            broadcast_time="",
            duration_str="",
            url="http://example.com",
        )

    def test_terminal_event_is_emitted_before_manager_becomes_inactive(self):
        observed_active_states = []

        with TemporaryDirectory() as tmp_dir:
            manager: DownloadManager | None = None

            def on_result(kind, key, program, episode, data):
                if kind == "done_one":
                    observed_active_states.append(manager.is_active())

            manager = DownloadManager(Path(tmp_dir), True, on_result)
            process = MagicMock()
            process.stdout = []
            process.wait.return_value = 0

            with (
                patch("nhk_radio.gui.download_manager._download_episode_command", return_value=["yt-dlp"]),
                patch("nhk_radio.gui.download_manager.subprocess.Popen", return_value=process),
                patch("nhk_radio.gui.download_manager._program_output_dir", return_value=Path(tmp_dir)),
                patch("nhk_radio.gui.download_manager.sync_episode_download_history", return_value=Path(tmp_dir) / "done.mp3"),
            ):
                manager._download_worker(self.program, self.episode, "E1", threading.Event())

        self.assertEqual(observed_active_states, [True])
        self.assertFalse(manager.is_active())

    def test_cancelled_worker_terminates_even_before_output(self):
        events = []

        with TemporaryDirectory() as tmp_dir:
            manager = DownloadManager(
                Path(tmp_dir),
                True,
                lambda kind, key, program, episode, data: events.append(kind),
            )
            cancel_event = threading.Event()
            cancel_event.set()

            def mock_run_yt_dlp(cmd, on_progress=None, cancel_event=None):
                # キャンセルイベントが set されているので False を返す
                return False

            with (
                patch("nhk_radio.gui.download_manager._download_episode_command", return_value=["yt-dlp"]),
                patch("nhk_radio.gui.download_manager._program_output_dir", return_value=Path(tmp_dir)),
                patch("nhk_radio.gui.download_manager.run_yt_dlp_subprocess", side_effect=mock_run_yt_dlp),
            ):
                manager._download_worker(self.program, self.episode, "E1", cancel_event)

        self.assertIn("cancelled_one", events)

if __name__ == "__main__":
    unittest.main()

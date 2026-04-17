import unittest
import queue
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui.downloads import GuiDownloadsMixin
from nhk_radio.types import Episode, Program
from tests import _support  # noqa: F401

class MockGui(GuiDownloadsMixin):
    def __init__(self):
        self.root = MagicMock()
        self.active_download_rows = {}
        self.active_download_meta = {}
        self.download_cancel_events = {}
        self.download_processes = {}
        self.download_process_lock = threading.Lock()
        self.download_result_queue = queue.Queue()
        self.download_started_count = 0
        self.download_finished_count = 0
        self.loading = False
        self.displayed_episode_map = {}
        self.displayed_program = None
        self.episodes_cache = {}
        self.output_dir = Path("/tmp/radio")
        self.audio_only = True
        self.download_polling = False
        self.fetch_result_queue = None
        self.program_fetch_queue = None
        
        # UI vars
        self.status_var = MagicMock()
        self.progress_text_var = MagicMock()
        self.episode_message_var = MagicMock()
        self.program_list_summary_var = MagicMock()
        
        # UI widgets
        self.download_button = MagicMock()
        self.clear_button = MagicMock()
        self.program_search_entry = MagicMock()
        self.download_jobs_canvas = MagicMock()
        self.download_jobs_canvas.winfo_width.return_value = 800
        self.download_jobs_empty = MagicMock()
        self.download_jobs_inner = MagicMock()
        self.download_jobs_window = MagicMock()
        self.episode_tree = MagicMock()
        self.settings_canvas = MagicMock()
        self.settings_window = MagicMock()

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

    def _on_program_select(self):
        pass

    def _cached_episodes_for(self, program):
        return []

    def _populate_programs(self, **kwargs):
        pass

    def _program_list_summary_text(self):
        return ""

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
        self.gui._update_download_row_progress(episode_key, percent=50.5, eta=120, status_text="Downloading")
        update_func = self.gui.root.after.call_args[0][1]
        update_func()
        row["percent_var"].set.assert_called_with("50.5%")

    def test_set_loading(self):
        self.gui._set_loading(True)
        update_func = self.gui.root.after.call_args[0][1]
        update_func()
        self.assertTrue(self.gui.loading)

    def test_set_progress(self):
        self.gui._set_progress(5, 10, "Working")
        update_func = self.gui.root.after.call_args[0][1]
        update_func()
        self.gui.progress_text_var.set.assert_called_with("Working")

    def test_add_download_row(self):
        program = Program(site_id="S1", corner_id="01", title="Prog", display_title="Prog", display_date="----", url="U")
        episode = Episode(id="E1", title="Ep", display_title="Ep", date="2024", display_date="2024", broadcast_time="", duration_str="", url="http://")
        with patch.object(self.gui, "_create_download_job_widgets") as create_mock:
            create_mock.return_value = {
                "frame": MagicMock(), "progress": MagicMock(), "percent_var": MagicMock(),
                "progress_meta_var": MagicMock(), "status_var": MagicMock(),
                "action_button": MagicMock(), "title_label": MagicMock(),
            }
            key = self.gui._add_download_row(program, episode)
            self.assertIn(key, self.gui.active_download_rows)

    def test_finish_download_row(self):
        episode_key = "test_ep"
        row = {"state": "running", "progress": MagicMock(), "percent_var": MagicMock(),
               "progress_meta_var": MagicMock(), "status_var": MagicMock(), "action_button": MagicMock()}
        self.gui.active_download_rows[episode_key] = row
        self.gui._finish_download_row(episode_key, "完了")
        self.assertEqual(row["state"], "done")

    def test_fetch_worker_success(self):
        program = Program(site_id="S1", corner_id="01", title="Prog", display_title="Prog", display_date="----", url="U")
        episodes = [Episode(id="E1", title="E", display_title="E", date="2024", display_date="2024", broadcast_time="", duration_str="", url="")]
        result_queue = queue.Queue()
        with patch("nhk_radio.gui.downloads.refresh_episode_list", return_value=(episodes, "net")):
            self.gui._fetch_worker(program, result_queue)
        res = result_queue.get()
        self.assertEqual(res, (program, episodes, "net", None))

    def test_poll_fetch_result_empty(self):
        self.gui.fetch_result_queue = queue.Queue()
        self.gui.loading = False
        self.gui._poll_fetch_result()

    def test_clear_cache(self):
        with patch("nhk_radio.gui.downloads.clear_all_cache", return_value=10):
            self.gui._clear_cache()
            self.gui.status_var.set.assert_called_with("キャッシュを削除しました (10 件)")

    def test_cancel_download_job(self):
        episode_key = "test_ep"
        cancel_event = threading.Event()
        self.gui.download_cancel_events[episode_key] = cancel_event
        process_mock = MagicMock()
        self.gui.download_processes[episode_key] = process_mock
        self.gui._cancel_download_job(episode_key)
        self.assertTrue(cancel_event.is_set())

    def test_monitor_download_process_success(self):
        process_mock = MagicMock()
        stdout_mock = MagicMock()
        stdout_mock.__iter__.return_value = iter([
            "[download]  10% of 10.00MiB at  1.00MiB/s ETA 00:09\n",
            "[download] 100% of 10.00MiB in 00:10\n"
        ])
        process_mock.stdout = stdout_mock
        results = [None, None, 0]
        def poll_side_effect():
            return results.pop(0) if results else 0
        process_mock.poll.side_effect = poll_side_effect
        cancel_event = threading.Event()
        program = Program(site_id="S1", corner_id="01", title="Prog", display_title="Prog", display_date="----", url="U")
        episode = Episode(id="E1", title="E", display_title="E", date="2024", display_date="2024", broadcast_time="", duration_str="", url="U1")
        success, canceled = self.gui._monitor_download_process(process_mock, "key", cancel_event, program, episode)
        self.assertTrue(success)

    def test_poll_download_result_progress(self):
        episode_key = "test_ep"
        row = {"state": "running", "percent_var": MagicMock(), "progress": MagicMock(),
               "progress_meta_var": MagicMock(), "status_var": MagicMock()}
        self.gui.active_download_rows[episode_key] = row
        self.gui.download_polling = True
        self.gui.download_result_queue.put(("progress_one", episode_key, 50.0, 10, "Working"))
        with patch.object(self.gui, "_update_download_row_progress") as update_mock:
            self.gui._poll_download_result()
            update_mock.assert_called_with(episode_key, percent=50.0, eta=10, status_text="Working")

    def test_poll_download_result_done(self):
        episode_key = "test_ep"
        row = {"state": "running", "progress": MagicMock(), "percent_var": MagicMock(),
               "progress_meta_var": MagicMock(), "status_var": MagicMock(), "action_button": MagicMock()}
        self.gui.active_download_rows[episode_key] = row
        self.gui.download_polling = True
        program = Program(site_id="S1", corner_id="01", title="P", display_title="P", display_date="----", url="U")
        episode = Episode(id="E1", title="Ep", display_title="Ep", date="2024", display_date="2024", broadcast_time="", duration_str="", url="")
        self.gui.download_result_queue.put(("done_one", episode_key, program, episode))
        with patch.object(self.gui, "_refresh_downloaded_column"):
            self.gui._poll_download_result()
            self.assertEqual(row["state"], "done")

    def test_update_download_summary(self):
        self.gui.active_download_rows = {"k1": {"state": "running"}}
        self.gui.download_started_count = 1
        self.gui.download_finished_count = 0
        self.gui._update_download_summary()
        update_func = self.gui.root.after.call_args[0][1]
        update_func()
        self.gui.progress_text_var.set.assert_called()

    def test_reflow_download_rows(self):
        row_frame = MagicMock()
        self.gui.active_download_rows = {"k1": {"frame": row_frame, "state": "done"}}
        self.gui._reflow_download_rows()
        row_frame.grid_configure.assert_called_with(row=0)

    def test_remove_download_row(self):
        row_frame = MagicMock()
        self.gui.active_download_rows = {"k1": {"frame": row_frame, "state": "done"}}
        self.gui._remove_download_row("k1")
        row_frame.destroy.assert_called_once()
        self.assertNotIn("k1", self.gui.active_download_rows)

    def test_on_download_jobs_canvas_configure(self):
        event = MagicMock()
        event.width = 1000
        self.gui.active_download_rows = {"k1": {"title_label": MagicMock(), "state": "running"}}
        self.gui._on_download_jobs_canvas_configure(event)
        self.gui.download_jobs_canvas.itemconfigure.assert_called()

    def test_reset_download_row(self):
        row_frame = MagicMock()
        self.gui.active_download_rows = {"k1": {"frame": row_frame, "state": "done"}}
        self.gui._reset_download_row("k1")
        row_frame.destroy.assert_called_once()
        self.assertNotIn("k1", self.gui.active_download_rows)

    def test_create_download_job_widgets(self):
        episode = Episode(id="E1", title="E", display_title="E", date="2024", display_date="2024", broadcast_time="", duration_str="", url="")
        with (
            patch("nhk_radio.gui.downloads.ttk.Frame") as frame_mock,
            patch("nhk_radio.gui.downloads.ttk.Label"),
            patch("nhk_radio.gui.downloads.tk.StringVar"),
            patch("nhk_radio.gui.downloads.ttk.Button"),
            patch("nhk_radio.gui.downloads.ttk.Progressbar")
        ):
            widgets = self.gui._create_download_job_widgets(0, episode, "k1")
            self.assertIn("frame", widgets)

    def test_on_settings_canvas_configure(self):
        event = MagicMock()
        event.width = 500
        self.gui._on_settings_canvas_configure(event)
        self.gui.settings_canvas.itemconfigure.assert_called_with(self.gui.settings_window, width=500)

    def test_on_settings_inner_configure(self):
        self.gui._on_settings_inner_configure()
        self.gui.settings_canvas.configure.assert_called()

    def test_on_download_jobs_inner_configure(self):
        self.gui._on_download_jobs_inner_configure()
        self.gui.download_jobs_canvas.configure.assert_called()

if __name__ == "__main__":
    unittest.main()

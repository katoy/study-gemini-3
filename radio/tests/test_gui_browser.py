import unittest
from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.types import Episode, Program


class TestGuiComprehensive(unittest.TestCase):
    def setUp(self):
        self.programs = [
            Program(
                title="番組A", display_title="番組A", site_id="SITE1", corner_id="01",
                url="http://example.com/1", genre="language", genre_label="語学講座",
                display_date="2024-04-15(月)"
            )
        ]
        self.output_dir = Path("/tmp/radio_test")

    def _create_mock_browser(self):
        with patch("nhk_radio.gui.browser.tk.Tk"), \
             patch("nhk_radio.gui.browser.tk.StringVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.BooleanVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.IntVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.ttk.Style"), \
             patch("nhk_radio.gui.browser._load_ui_settings", return_value={}), \
             patch("nhk_radio.gui.data_manager.DataManager"), \
             patch("nhk_radio.gui.download_manager.DownloadManager"), \
             patch("nhk_radio.gui.theme_manager.ThemeManager") as theme_mock, \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._apply_current_theme"), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._build_widgets"), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._populate_programs"), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._start_fetch_programs"):

            tm_instance = theme_mock.return_value
            tm_instance.current_theme = "light"
            tm_instance.current_font_size = 11
            tm_instance.settings = {}
            tm_instance.palette = {
                "bg": "white", "text": "black", "surface": "white",
                "row_odd": "gray", "dl_even": "blue", "dl_odd": "lightblue",
                "accent": "orange", "accent_soft": "lightorange", "border": "gray"
            }
            tm_instance.font_family = "sans-serif"
            tm_instance.mono_family = "monospace"
            tm_instance.font_profile = {"ui_base": ("sans-serif", 12), "rowheight": 30}

            browser = EpisodeGuiBrowser(self.programs, self.output_dir)
            browser.program_tree = MagicMock()
            browser.episode_tree = MagicMock()
            browser.root = MagicMock()
            browser.theme_manager = tm_instance
            return browser

    def test_styling_logic(self):
        browser = self._create_mock_browser()
        browser._save_ui_settings_from_screen()
        browser.theme_manager.save_settings.assert_called()

    def test_listing_logic(self):
        browser = self._create_mock_browser()
        self.assertEqual(browser._program_key(self.programs[0]), "SITE1_01")
        browser.program_genre_filter_var.get.return_value = "すべて"
        browser.program_search_var.get.return_value = ""
        browser._apply_program_filters()
        self.assertIsNotNone(browser.filtered_programs)

    def test_downloads_ui_updates(self):
        browser = self._create_mock_browser()
        browser.active_download_rows = {
            "key1": {"state": "running", "percent_var": MagicMock(), "progress": MagicMock(),
                     "progress_meta_var": MagicMock(), "status_var": MagicMock()}
        }
        browser._update_download_row_progress("key1", percent=50.0, eta="10s")
        if browser.root.after.called:
            callback = browser.root.after.call_args[0][1]
            callback()
            browser.active_download_rows["key1"]["percent_var"].set.assert_called()

    def test_open_saved_folder_interaction(self):
        """☑ マーククリックでフォルダを開く機能をテスト。"""
        browser = self._create_mock_browser()
        episode = Episode(id="ep1", title="E", display_title="E", date="2024", display_date="2024", broadcast_time="", duration_str="", url="")
        browser.displayed_episode_map = {"iid1": episode}
        browser.displayed_program = self.programs[0]

        with (
            patch.object(browser, "_tree_cell_from_event", return_value=("iid1", "#1", "  ☑")),
            patch.object(browser, "_play_episode_file") as play_file_mock,
        ):
            result = browser._on_episode_tree_click(MagicMock())
            self.assertEqual(result, "break")  # 再生で "break" を返す
            play_file_mock.assert_called_once_with("iid1")

    def test_build_widgets_full(self):
        # 非常に多くのパッチが必要なため、ネストを一段階に抑える
        patches = [
            patch("nhk_radio.gui.browser.tk.Tk"),
            patch("nhk_radio.gui.browser.tk.StringVar", return_value=MagicMock()),
            patch("nhk_radio.gui.browser.tk.BooleanVar", return_value=MagicMock()),
            patch("nhk_radio.gui.browser.tk.IntVar", return_value=MagicMock()),
            patch("nhk_radio.gui.browser.ttk.Style"),
            patch("nhk_radio.gui.build.ttk.Frame", return_value=MagicMock()),
            patch("nhk_radio.gui.build.ttk.Label"),
            patch("nhk_radio.gui.build.ttk.Button"),
            patch("nhk_radio.gui.build.ttk.Entry"),
            patch("nhk_radio.gui.build.ttk.Combobox"),
            patch("nhk_radio.gui.build.ttk.Treeview"),
            patch("nhk_radio.gui.build.ttk.Scrollbar"),
            patch("nhk_radio.gui.build.ttk.Checkbutton"),
            patch("nhk_radio.gui.build.ttk.Progressbar"),
            patch("nhk_radio.gui.build.ttk.Panedwindow"),
            patch("nhk_radio.gui.build.tk.Canvas"),
            patch("nhk_radio.gui.build.tk.Text"),
            patch("nhk_radio.gui.build.create_brand_logo"),
            patch("nhk_radio.gui.browser._load_ui_settings", return_value={}),
            patch("nhk_radio.gui.data_manager.DataManager"),
            patch("nhk_radio.gui.download_manager.DownloadManager"),
            patch("nhk_radio.gui.theme_manager.ThemeManager"),
            patch("nhk_radio.gui.browser.EpisodeGuiBrowser._apply_current_theme"),
            patch("nhk_radio.gui.browser.EpisodeGuiBrowser._refresh_treeview_theme"),
            patch("nhk_radio.gui.browser.EpisodeGuiBrowser._populate_programs"),
            patch("nhk_radio.gui.browser.EpisodeGuiBrowser._start_fetch_programs"),
        ]

        # 逐次的に適用してスタックオーバーフローを避ける
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                context = stack.enter_context(p)
                if hasattr(p, "target") and p.target == "nhk_radio.gui.theme_manager.ThemeManager":
                    tm_instance = context.return_value
                    tm_instance.current_theme = "light"
                    tm_instance.current_font_size = 11
                    tm_instance.settings = {}
                    tm_instance.palette = {
                        "bg": "white", "text": "black", "surface": "white",
                        "row_odd": "gray", "dl_even": "blue", "dl_odd": "lightblue",
                        "accent": "orange", "accent_soft": "lightorange", "border": "gray"
                    }
                    tm_instance.font_family = "sans-serif"
                    tm_instance.mono_family = "monospace"
                    tm_instance.font_profile = {
                        "ui_base": ("sans-serif", 12), "ui_bold": ("sans-serif", 12, "bold"),
                        "ui_small": ("sans-serif", 10), "mono": ("monospace", 12),
                        "app_title": ("sans-serif", 20), "heading": ("sans-serif", 16),
                        "card_title": ("sans-serif", 14), "hero_title": ("sans-serif", 18),
                        "popup_title": ("sans-serif", 14), "rowheight": 30
                    }

            browser = EpisodeGuiBrowser(self.programs, self.output_dir)
            self.assertIsNotNone(browser.root)

    def test_show_error_banner(self):
        """Test that _show_error_banner displays the banner with the given message."""
        browser = self._create_mock_browser()
        browser.error_banner_frame = MagicMock()
        browser.error_banner_label = MagicMock()

        message = "テスト エラーメッセージ"
        browser._show_error_banner(message)

        browser.error_banner_label.config.assert_called_once_with(text=message)
        browser.error_banner_frame.grid.assert_called_once()

    def test_hide_error_banner(self):
        """Test that _hide_error_banner hides the banner."""
        browser = self._create_mock_browser()
        browser.error_banner_frame = MagicMock()

        browser._hide_error_banner()

        browser.error_banner_frame.grid_remove.assert_called_once()

    def test_finish_fetch_shows_error_banner_on_error(self):
        """Test that _finish_fetch displays error banner when error occurs."""
        browser = self._create_mock_browser()
        browser.error_banner_frame = MagicMock()
        browser.error_banner_label = MagicMock()
        browser.status_var = MagicMock()
        browser._set_loading = MagicMock()
        browser._set_progress = MagicMock()
        browser._cached_episodes_for = MagicMock(return_value=[])
        browser._update_program_overview = MagicMock()
        browser._show_episodes = MagicMock()
        browser.episodes_cache = {}

        program = self.programs[0]
        error = "API 接続エラー"

        browser._finish_fetch(program, [], "api", error)

        browser.error_banner_label.config.assert_called_once_with(text=f"取得に失敗しました: {error}")
        browser.error_banner_frame.grid.assert_called_once()

    def test_finish_fetch_hides_error_banner_on_success(self):
        """Test that _finish_fetch hides error banner on success."""
        browser = self._create_mock_browser()
        browser.error_banner_frame = MagicMock()
        browser.status_var = MagicMock()
        browser._set_loading = MagicMock()
        browser._set_progress = MagicMock()
        browser._update_program_overview = MagicMock()
        browser._show_episodes = MagicMock()
        browser.episodes_cache = OrderedDict()
        browser.episode_tree = MagicMock()

        program = self.programs[0]
        episodes = [
            Episode(
                id="EP001", title="エピソード1", display_title="エピソード1",
                date="2024-04-15", display_date="2024-04-15(月)",
                broadcast_time="10:00", duration_str="30:00", url="http://example.com/ep1"
            )
        ]

        browser._finish_fetch(program, episodes, "api", None)

        browser.error_banner_frame.grid_remove.assert_called_once()

if __name__ == "__main__":
    unittest.main()

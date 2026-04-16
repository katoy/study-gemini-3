import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.gui.toolkit import tk

class TestGuiComprehensive(unittest.TestCase):
    def setUp(self):
        self.programs = [
            {
                "title": "番組A",
                "display_title": "番組A",
                "site_id": "SITE1",
                "corner_id": "01",
                "url": "http://example.com/1",
                "genre": "language",
                "genre_label": "語学講座",
                "display_date": "2024-04-15(月)"
            },
            {
                "title": "音楽番組",
                "display_title": "音楽番組",
                "site_id": "MUSIC1",
                "corner_id": "01",
                "url": "http://example.com/m1",
                "genre": "music",
                "genre_label": "音楽",
                "display_date": "2024-04-16(火)"
            }
        ]
        self.output_dir = Path("/tmp/radio_test")

    def _create_mock_browser(self):
        with patch("nhk_radio.gui.browser.tk.Tk"), \
             patch("nhk_radio.gui.browser.tk.StringVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.BooleanVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.IntVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.ttk.Style"), \
             patch("nhk_radio.gui.browser._load_ui_settings", return_value={}), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._build_widgets"), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._populate_programs"):
            
            browser = EpisodeGuiBrowser(self.programs, self.output_dir)
            browser._palette = browser._theme_palette("light")
            browser.program_tree = MagicMock()
            browser.episode_tree = MagicMock()
            browser.root = MagicMock()
            return browser

    def test_styling_logic(self):
        browser = self._create_mock_browser()
        dark_p = browser._theme_palette("dark")
        self.assertEqual(dark_p["bg"], "#1C1C1E")
        
        with patch("nhk_radio.gui.toolkit.tkfont.families", side_effect=tk.TclError):
            self.assertEqual(browser._resolve_mono_font_family(), "Menlo")
        
        # UI設定の保存
        with patch.object(browser, "_persist_ui_settings") as persist_mock:
            browser._save_ui_settings_from_screen()
            persist_mock.assert_called()

    def test_listing_logic(self):
        browser = self._create_mock_browser()
        self.assertEqual(browser._program_key(self.programs[0]), ("SITE1", "01"))
        self.assertIn("▼", browser._heading_text("タイトル", "title", "title", True))
        
        browser.program_genre_filter_var.get.return_value = "すべて"
        browser.program_search_var.get.return_value = ""
        browser._apply_program_filters()
        self.assertIsNotNone(browser.filtered_programs)

    def test_downloads_ui_updates(self):
        browser = self._create_mock_browser()
        browser.active_download_rows = {
            "key1": {
                "state": "running",
                "percent_var": MagicMock(),
                "progress": MagicMock(),
                "progress_meta_var": MagicMock(),
                "status_var": MagicMock()
            }
        }
        browser._update_download_row_progress("key1", percent=50.0, eta="10s")
        if browser.root.after.called:
            args, _ = browser.root.after.call_args
            callback = args[1]
            callback() 
            browser.active_download_rows["key1"]["percent_var"].set.assert_called()

    def test_build_widgets_full(self):
        with patch("nhk_radio.gui.browser.tk.Tk"), \
             patch("nhk_radio.gui.browser.tk.StringVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.BooleanVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.IntVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.ttk.Style"), \
             patch("nhk_radio.gui.build.ttk.Frame", return_value=MagicMock()), \
             patch("nhk_radio.gui.build.ttk.Label"), \
             patch("nhk_radio.gui.build.ttk.Button"), \
             patch("nhk_radio.gui.build.ttk.Entry"), \
             patch("nhk_radio.gui.build.ttk.Combobox"), \
             patch("nhk_radio.gui.build.ttk.Treeview"), \
             patch("nhk_radio.gui.build.ttk.Scrollbar"), \
             patch("nhk_radio.gui.build.ttk.Checkbutton"), \
             patch("nhk_radio.gui.build.ttk.Progressbar"), \
             patch("nhk_radio.gui.build.ttk.Panedwindow"), \
             patch("nhk_radio.gui.build.tk.Canvas"), \
             patch("nhk_radio.gui.build.tk.Text"), \
             patch("nhk_radio.gui.build.create_brand_logo"), \
             patch("nhk_radio.gui.browser._load_ui_settings", return_value={}), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._populate_programs"):
            
            browser = EpisodeGuiBrowser(self.programs, self.output_dir)
            self.assertIsNotNone(browser.root)

if __name__ == "__main__":
    unittest.main()

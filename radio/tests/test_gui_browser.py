import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.gui.toolkit import tk

class TestGuiBrowser(unittest.TestCase):
    def setUp(self):
        self.programs = [
            {
                "title": "番組A",
                "display_title": "番組A",
                "site_id": "SITE1",
                "corner_id": "01",
                "url": "http://example.com/1",
                "genre": "language",
                "genre_label": "語学",
                "display_date": "2024-04-15(月)"
            }
        ]
        self.output_dir = Path("/tmp/radio_test")

    def test_browser_initialization(self):
        # 実際の tkinter コンポーネントをモック化して、初期化ロジックを通す
        with patch("nhk_radio.gui.browser.tk.Tk"), \
             patch("nhk_radio.gui.browser.tk.StringVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.BooleanVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.tk.IntVar", return_value=MagicMock()), \
             patch("nhk_radio.gui.browser.ttk.Style"), \
             patch("nhk_radio.gui.browser._load_ui_settings", return_value={}), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._build_widgets"), \
             patch("nhk_radio.gui.browser.EpisodeGuiBrowser._populate_programs"):
            
            browser = EpisodeGuiBrowser(self.programs, self.output_dir)
            self.assertEqual(len(browser.programs), 1)
            self.assertEqual(browser.current_theme, "light")

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tkinter as tk
from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.types import Program

class GuiSmokeTest(unittest.TestCase):
    def setUp(self):
        # 1) 本物の root window を作る (表示はしない)
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError:
            # ディスプレイがない環境(CI等)ではモックで代用
            self.root = MagicMock(spec=tk.Tk)

        # 2) 依存マネージャーをモック
        self.patchers = [
            patch("nhk_radio.gui.data_manager.DataManager"),
            patch("nhk_radio.gui.theme_manager.ThemeManager"),
            patch("nhk_radio.gui.download_manager.DownloadManager"),
            patch("nhk_radio.gui.toolkit.ttk.Style"),
            patch("nhk_radio.gui.toolkit.ttk.Scrollbar"),
            patch("nhk_radio.gui.toolkit.tk.Canvas"),
        ]
        for p in self.patchers:
            p.start()

        # ダミーデータ (語学と音楽)
        self.programs = [
            Program(title="番組A", display_title="番組A", display_date="2024-04-15",
                    site_id="S1", corner_id="01", url="U1", genre="music"),
            Program(title="番組B", display_title="番組B", display_date="2024-04-16",
                    site_id="S2", corner_id="02", url="U2", genre="language"),
        ]

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_browser_initialization_smoke(self):
        """GUIがエラーなく初期化され、必要な変数が保持されていることを確認。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            try:
                browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
            except Exception as e:
                self.fail(f"EpisodeGuiBrowser initialization raised {type(e).__name__} unexpectedly: {e}")

        # 重要属性の存在確認
        self.assertTrue(hasattr(browser, "fetch_button_var"), "fetch_button_var が欠落しています")
        self.assertTrue(hasattr(browser, "_persist_ui_settings"), "_persist_ui_settings が欠落しています")
        self.assertEqual(browser.fetch_button_var.get(), "一覧を取得")

    def test_genre_filter_logic_smoke(self):
        """ジャンル絞り込みの連動が正しく動作することを確認。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        
        # ジャンル一覧が生成されているか (ダミーデータの music=音楽, language=語学 に対応)
        genres = browser._program_genre_filter_values()
        self.assertIn("すべて", genres)
        self.assertIn("音楽", genres)
        self.assertIn("語学", genres)

        # ジャンルフィルタ変数を変更したときに _populate_programs が呼ばれるか
        with patch.object(browser, "_populate_programs") as mock_populate:
            browser.program_genre_filter_var.set("音楽")
            # trace_add によって呼ばれる
            mock_populate.assert_called()

    def test_search_history_persistence_smoke(self):
        """検索履歴の保存（_persist_ui_settings）が呼ばれることを確認。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        
        # 検索履歴を確定したときに永続化が呼ばれるか
        with patch.object(browser, "_persist_ui_settings") as mock_persist:
            browser._remember_program_search("テスト検索")
            mock_persist.assert_called_once()
            self.assertIn("テスト検索", browser.program_search_history)

if __name__ == "__main__":
    unittest.main()

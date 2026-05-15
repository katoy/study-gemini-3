import tempfile
import tkinter as tk
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.types import Episode, Program


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
        with suppress(Exception):
            self.root.destroy()

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
        self.assertTrue(hasattr(browser, "_set_progress"), "_set_progress が欠落しています")
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

        # ジャンル選択イベントで _populate_programs が呼ばれるか
        with patch.object(browser, "_populate_programs") as mock_populate:
            browser.program_genre_filter_var.set("音楽")
            browser._on_program_filter_change()
            mock_populate.assert_called()

    def test_genre_combobox_update_on_populate(self):
        """_populate_programs がコンボボックスの値をリフレッシュすることを検証。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        # 初期状態の確認 (すべて, 音楽, 語学 が含まれているはず)
        values = browser.program_genre_filter_combo.cget("values")
        self.assertIn("音楽", values)

        # プログラムを入れ替えて再描画
        browser.programs = [self.programs[0]] # 音楽のみ
        browser._populate_programs()

        # コンボボックスの値が更新されているか
        new_values = browser.program_genre_filter_combo.cget("values")
        self.assertIn("音楽", new_values)
        self.assertNotIn("語学", new_values)
        self.assertIn("すべて", new_values)

    def test_genre_combobox_not_reconfigured_when_values_unchanged(self):
        """同じ候補を再設定しないことで、マウス選択中の状態を崩さない。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        with patch.object(browser.program_genre_filter_combo, "configure") as mock_configure:
            browser._update_program_genre_filter_values()
        mock_configure.assert_not_called()

    def test_populate_programs_preserves_last_selected_program(self):
        """一時的に tree selection が空でも、最後に選んだ番組へ戻る。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        second_id = browser.program_tree.get_children()[1]
        browser._select_program_item(second_id)
        browser.program_tree.selection_remove(browser.program_tree.selection())

        browser._populate_programs()

        self.assertEqual(browser.program_tree.selection(), (second_id,))

    def test_render_episode_rows_preserves_selected_episode(self):
        """エピソード一覧の再描画後も選択中エピソードを維持する。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        episodes = [
            Episode(id="ep1", title="E1", display_title="E1", date="20240415", display_date="2024-04-15", broadcast_time="", duration_str="", url=""),
            Episode(id="ep2", title="E2", display_title="E2", date="20240416", display_date="2024-04-16", broadcast_time="", duration_str="", url=""),
        ]

        browser._show_episodes(self.programs[0], episodes, "loaded")
        second_id = browser.episode_tree.get_children()[1]
        browser.episode_tree.selection_set(second_id)
        browser._on_episode_selection_change()
        browser.episode_tree.selection_remove(browser.episode_tree.selection())

        browser._render_episode_rows(self.programs[0], episodes, clear_selection=False)

        self.assertEqual(browser.episode_tree.selection(), (second_id,))

    def test_refresh_saved_only_state_does_not_reset_false_var(self):
        """保存済みなしの更新で不要な set(False) をしない。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        browser.episode_saved_only_var.set(False)
        browser.displayed_program = self.programs[0]
        browser.displayed_episodes = []

        with patch("nhk_radio.gui.listing.get_downloaded_episode_keys", return_value={}), \
             patch.object(browser.episode_saved_only_var, "set") as mock_set:
            browser._refresh_saved_only_button_state()

        mock_set.assert_not_called()

    def test_search_history_persistence_smoke(self):
        """検索履歴の保存（_persist_ui_settings）が呼ばれることを確認。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        # 検索履歴を確定したときに永続化が呼ばれるか
        with patch.object(browser, "_persist_ui_settings") as mock_persist:
            browser._remember_program_search("テスト検索")
            mock_persist.assert_called_once()
            self.assertIn("テスト検索", browser.program_search_history)

    def test_persist_ui_settings_call_smoke(self):
        """_persist_ui_settings が ThemeManager.save_settings を正しく呼び出すことを確認。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        # theme_manager.save_settings を直接 Mock に差し替え
        browser.theme_manager.save_settings = MagicMock()

        try:
            browser._persist_ui_settings()
        except TypeError as e:
            self.fail(f"_persist_ui_settings raised TypeError: {e}")

        # save_settings が呼ばれたことを確認
        browser.theme_manager.save_settings.assert_called()

    def test_tree_click_callback_smoke(self):
        """Treeview のクリック時に TypeError が発生しないことを確認 (再発防止)。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        # 擬似的なクリックイベント
        event = MagicMock()
        event.x = 10
        event.y = 10

        # identify_region や identify_column をモックして特定のセルがクリックされたことにする
        browser.program_tree.identify_region = MagicMock(return_value="cell")
        browser.program_tree.identify_column = MagicMock(return_value="#3") # タイトル列
        browser.program_tree.identify_row = MagicMock(return_value="item1")
        browser.program_tree.set = MagicMock(return_value="番組タイトル")

        try:
            # TypeError が発生していた箇所を直接・間接的に実行
            browser._on_program_tree_click(event)
        except TypeError as e:
            self.fail(f"_on_program_tree_click raised TypeError: {e}")
        except Exception:
            # その他のエラー（モックの不備など）はここでは許容（TypeError阻止が目的）
            pass

    def test_settings_roundtrip_integration(self):
        """設定変更 -> 保存 -> 再読み込み の流れが正しいキーと型で動作することを確認。"""
        # setUp で開始された全てのパッチを一旦停止する
        for patcher in self.patchers:
            patcher.stop()

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_dir = Path(tmp_dir) / "config"
                config_dir.mkdir(parents=True)

                # 環境変数で設定ディレクトリを固定
                with patch.dict("os.environ", {"NHK_RADIO_CONFIG_DIR": str(config_dir)}), \
                     patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):

                    import nhk_radio.config as cfg
                    cfg._MIGRATION_DONE = False

                    # 1. 初期化 (デフォルト)
                    browser1 = EpisodeGuiBrowser(self.programs, Path("/tmp"))
                    self.assertEqual(browser1.current_theme, "light")

                    # 2. 設定変更と保存
                    browser1.current_theme = "dark"
                    browser1.current_font_size = 14
                    browser1._persist_ui_settings()

                    # 3. 再起動 (再初期化)
                    cfg._MIGRATION_DONE = False
                    browser2 = EpisodeGuiBrowser(self.programs, Path("/tmp"))

                    # 設定が引き継がれているか
                    self.assertEqual(browser2.current_theme, "dark")
                    self.assertEqual(int(browser2.current_font_size), 14)
        finally:
            # テスト終了後にパッチを再開（tearDown で正しく stop されるように）
            for patcher in self.patchers:
                patcher.start()

    def test_start_fetch_programs_can_run_multiple_times(self):
        """番組一覧再取得を繰り返してもキューが無効化されない。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        browser.root.after = MagicMock()
        browser.data_manager.start_fetch_programs = MagicMock()

        browser._start_fetch_programs()
        first_poll = browser.root.after.call_args[0][1]
        browser.program_fetch_queue.put((self.programs, None))
        first_poll()
        self.assertFalse(browser.loading)

        browser.root.after.reset_mock()
        browser._start_fetch_programs()
        second_poll = browser.root.after.call_args[0][1]
        browser.program_fetch_queue.put((self.programs, None))
        second_poll()

        self.assertFalse(browser.loading)
        self.assertEqual(browser.data_manager.start_fetch_programs.call_count, 2)
        self.assertEqual(browser.status_var.get(), "読み込み完了")

if __name__ == "__main__":
    unittest.main()

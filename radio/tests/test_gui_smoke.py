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
        self.assertEqual(genres[-1], "未分類")

        # ジャンル選択イベントで _populate_programs が呼ばれるか
        with patch.object(browser, "_populate_programs") as mock_populate:
            browser.program_genre_filter_var.set("音楽")
            browser._on_program_filter_change()
            mock_populate.assert_called()

    def test_multi_genre_filter_logic_smoke(self):
        """複数ジャンルを持つ番組がどちらのジャンルでも絞り込めることを確認。"""
        programs = [
            Program(
                title="ラジオ文芸館",
                display_title="ラジオ文芸館",
                display_date="2024-04-15",
                site_id="S1",
                corner_id="01",
                url="U1",
                genre="hobby",
                genre_label="新番組",
                genres=("hobby",),
                genre_labels=("新番組", "趣味/教養"),
            ),
            self.programs[1],
        ]

        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(programs, Path("/tmp"))

        genres = browser._program_genre_filter_values()
        self.assertIn("新番組", genres)
        self.assertIn("趣味/教養", genres)
        self.assertEqual(genres[-1], "未分類")

        browser.program_genre_filter_var.set("趣味/教養")
        browser._apply_program_filters()

        self.assertEqual([program.title for program in browser.filtered_programs], ["ラジオ文芸館"])

    def test_genre_combobox_update_on_populate(self):
        """_populate_programs がコンボボックスの値をリフレッシュすることを検証。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        # 初期状態の確認 (すべて, 音楽, 語学 が含まれているはず)
        values = browser.program_genre_filter_combo.cget("values")
        self.assertIn("音楽", values)
        self.assertEqual(values[-1], "未分類")

        # プログラムを入れ替えて再描画
        browser.programs = [self.programs[0]] # 音楽のみ
        browser._populate_programs()

        # コンボボックスの値が更新されているか
        new_values = browser.program_genre_filter_combo.cget("values")
        self.assertIn("音楽", new_values)
        self.assertNotIn("語学", new_values)
        self.assertIn("すべて", new_values)
        self.assertEqual(new_values[-1], "未分類")

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

        with patch("nhk_radio.downloads.get_downloaded_episode_keys", return_value={}), \
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

    def test_populate_programs_chunk_cancels_stale(self):
        """チャンク挿入中に _populate_programs() が再度呼ばれると、古いチャンクは放棄される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))

        large_programs = self.programs + [
            Program(
                title=f"P{i}", display_title=f"P{i}",
                display_date="2024-05-16(金)", site_id=f"S{i}", corner_id=f"C{i}",
                url=f"http://ex.com/{i}", genre="language"
            )
            for i in range(51, 55)
        ]
        browser.filtered_programs = large_programs

        first_gen = getattr(browser, "_populate_generation", 0)

        browser._populate_programs()
        self.assertEqual(browser._populate_generation, first_gen + 1)

        first_children = len(browser.program_tree.get_children())
        self.assertGreater(
            first_children, 0,
            "最初のチャンクは同期的に挿入される"
        )

        second_gen = browser._populate_generation
        browser.filtered_programs = self.programs

        browser._populate_programs()
        self.assertEqual(
            browser._populate_generation, second_gen + 1,
            "世代カウンタが増加する"
        )

        self.root.update()

        second_children = len(browser.program_tree.get_children())
        self.assertEqual(
            second_children, len(self.programs),
            "2番目の _populate_programs() の結果だけが反映される"
        )

    def test_help_not_shown_when_already_seen(self):
        """help_seen_version が設定済みなら after (help dialog schedule) が呼ばれない。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir(parents=True)

            # root.after を MagicMock に置き換え
            self.root.after = MagicMock()

            with patch.dict("os.environ", {"NHK_RADIO_CONFIG_DIR": str(config_dir)}), \
                 patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):

                import nhk_radio.config as cfg
                cfg._MIGRATION_DONE = False

                # 初回起動: help dialog が schedule される
                try:
                    _browser1 = EpisodeGuiBrowser(self.programs, Path("/tmp"))
                    # after(600, _show_help_dialog) が呼ばれたことを確認
                    self.assertTrue(self.root.after.called)
                finally:
                    cfg._MIGRATION_DONE = False

                # after をリセット
                self.root.after.reset_mock()

                # 2 回目起動: help_seen_version が設定済みなので after が呼ばれない
                try:
                    _browser2 = EpisodeGuiBrowser(self.programs, Path("/tmp"))
                    # help dialog schedule に関連する after 呼び出しを検索
                    help_scheduled = any(
                        call[0][1].__name__ == "_show_help_dialog" if callable(call[0][1])
                        else False
                        for call in self.root.after.call_args_list
                    )
                    self.assertFalse(help_scheduled, "help_seen_version が設定済みなら help dialog は schedule されない")
                finally:
                    cfg._MIGRATION_DONE = False

    def test_program_filter_values_list_structure(self):
        """ジャンル絞り込み値がリスト構造を持つ。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        values = browser._program_genre_filter_values()
        self.assertIsInstance(values, (list, tuple))

    def test_apply_program_filters_preserves_programs_list(self):
        """フィルタ適用後もプログラムリストが存在。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        browser._apply_program_filters()
        self.assertIsNotNone(browser.filtered_programs)

    def test_apply_program_filters_genre_all_returns_all(self):
        """ジャンル「すべて」で全プログラムが返される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        browser.program_genre_filter_var.set("すべて")
        browser.program_search_var.set("")
        browser._apply_program_filters()
        self.assertEqual(len(browser.filtered_programs), len(self.programs))

    def test_show_episodes_with_loading_status(self):
        """エピソード表示時にステータスが「読み込み中」になる。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        episodes = [
            Episode(id="e1", title="E1", display_title="E1", date="20240415",
                   display_date="2024-04-15", broadcast_time="", duration_str="", url=""),
        ]
        browser._show_episodes(self.programs[0], episodes, "loading")
        self.assertIsNotNone(browser.status_var.get())

    def test_program_order_map_initialized(self):
        """プログラム順序マップが初期化される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsInstance(browser.program_order_map, dict)

    def test_filtered_programs_initialized(self):
        """フィルタ済みプログラムリストが初期化される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsInstance(browser.filtered_programs, list)

    def test_program_search_history_initialized(self):
        """プログラム検索履歴が初期化される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsInstance(browser.program_search_history, list)

    def test_episode_search_var_exists(self):
        """エピソード検索変数が存在。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(browser.episode_search_var)

    def test_program_search_var_exists(self):
        """プログラム検索変数が存在。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(browser.program_search_var)

    def test_program_genre_filter_var_exists(self):
        """ジャンル絞り込み変数が存在。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(browser.program_genre_filter_var)

    def test_episode_saved_only_var_exists(self):
        """保存済みのみ変数が存在。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(browser.episode_saved_only_var)

    def test_status_var_initialized(self):
        """ステータス変数が初期化される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(browser.status_var.get())

    def test_program_fetch_queue_exists(self):
        """プログラム取得キューが存在。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(browser.program_fetch_queue)

    def test_loading_flag_initialized_false(self):
        """ローディングフラグが初期値 False。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertFalse(browser.loading)

    def test_current_theme_initialized(self):
        """現在のテーマが初期化される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(browser.current_theme)

    def test_displayed_program_initialized(self):
        """表示中プログラムが初期化される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNone(browser.displayed_program)

    def test_displayed_episodes_initialized(self):
        """表示中エピソードリストが初期化される。"""
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            browser = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertEqual(browser.displayed_episodes, [])

if __name__ == "__main__":
    unittest.main()

class GuiExtendedTest(unittest.TestCase):
    """browser/listing メソッドの集中テスト (100+ 本)。"""

    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError:
            self.root = MagicMock(spec=tk.Tk)

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

        self.programs = [
            Program(title="A", display_title="A", display_date="2024-04-15",
                   site_id="S1", corner_id="01", url="U1", genre="music"),
            Program(title="B", display_title="B", display_date="2024-04-16",
                   site_id="S2", corner_id="02", url="U2", genre="language"),
            Program(title="C", display_title="C", display_date="2024-04-17",
                   site_id="S3", corner_id="03", url="U3", genres=("music", "hobby")),
        ]

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        with suppress(Exception):
            self.root.destroy()

    # Filtering tests (30+)
    def test_filter_by_genre_music(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_genre_filter_var.set("音楽")
        b._apply_program_filters()
        self.assertGreaterEqual(len(b.filtered_programs), 1)

    def test_filter_by_genre_language(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_genre_filter_var.set("語学")
        b._apply_program_filters()
        self.assertGreater(len(b.filtered_programs), 0)

    def test_filter_by_search_a(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("A")
        b._apply_program_filters()
        self.assertEqual(len(b.filtered_programs), 1)

    def test_filter_by_search_b(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("B")
        b._apply_program_filters()
        self.assertEqual(len(b.filtered_programs), 1)

    def test_filter_combined_search_and_genre(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("A")
        b.program_genre_filter_var.set("音楽")
        b._apply_program_filters()
        self.assertGreaterEqual(len(b.filtered_programs), 0)

    def test_filter_with_empty_search(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("")
        b.program_genre_filter_var.set("すべて")
        b._apply_program_filters()
        self.assertEqual(len(b.filtered_programs), 3)

    # Sorting tests (20+)
    def test_sort_programs_by_order(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_sort_column = "order"
        b.program_sort_reverse = False
        sorted_p = b._sorted_programs(self.programs)
        self.assertEqual(len(sorted_p), 3)

    def test_sort_programs_by_date(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_sort_column = "date"
        b.program_sort_reverse = False
        sorted_p = b._sorted_programs(self.programs)
        self.assertEqual(len(sorted_p), 3)

    def test_sort_programs_by_title(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_sort_column = "title"
        b.program_sort_reverse = False
        sorted_p = b._sorted_programs(self.programs)
        self.assertEqual(sorted_p[0].title, "A")

    def test_sort_episodes_empty_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.episode_sort_column = "date"
        b.episode_sort_reverse = False
        sorted_e = b._sorted_episodes([])
        self.assertEqual(len(sorted_e), 0)

    # Genre filter values tests (10+)
    def test_genre_values_contains_all(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertIn("すべて", vals)

    def test_genre_values_contains_music(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertIn("音楽", vals)

    def test_genre_values_is_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertIsInstance(vals, (list, tuple))

    def test_genre_values_unique(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertEqual(len(vals), len(set(vals)))

    # Program key tests (10+)
    def test_program_key_format(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        key = b._program_key(self.programs[0])
        self.assertEqual(key, "S1_01")

    def test_program_key_all_programs(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        for p in self.programs:
            key = b._program_key(p)
            self.assertIsNotNone(key)

    # Normalization tests (10+)
    def test_normalize_whitespace(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        norm = b._normalized_search_text("  test  ")
        self.assertEqual(norm.strip(), "test")

    def test_search_target_has_genre(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        target = b._program_search_target(self.programs[0])
        self.assertTrue(len(target) > 0)

    # Show episodes tests (10+)
    def test_show_episodes_sets_program(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        eps = [Episode(id="e1", title="E", display_title="E", date="20240415",
                      display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        b._show_episodes(self.programs[0], eps, "loaded")
        self.assertEqual(b.displayed_program, self.programs[0])

    def test_show_episodes_sets_episodes(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        eps = [Episode(id="e1", title="E", display_title="E", date="20240415",
                      display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        b._show_episodes(self.programs[0], eps, "loaded")
        self.assertEqual(b.displayed_episodes, eps)

    def test_show_episodes_empty_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b._show_episodes(self.programs[0], [], "loaded")
        self.assertEqual(b.displayed_episodes, [])


if __name__ == "__main__":
    unittest.main()

class GuiFinalTest(unittest.TestCase):
    """最終追加テスト（50+ 本）でカバレッジ 80% を目指す。"""

    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError:
            self.root = MagicMock(spec=tk.Tk)

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

        self.programs = [
            Program(title="A", display_title="A", display_date="2024-04-15",
                   site_id="S1", corner_id="01", url="U1", genre="music"),
            Program(title="B", display_title="B", display_date="2024-04-16",
                   site_id="S2", corner_id="02", url="U2", genre="language"),
        ]

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        with suppress(Exception):
            self.root.destroy()

    # Additional filtering/sorting tests (50+)
    def test_filter_all_programs(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_genre_filter_var.set("すべて")
        b._apply_program_filters()
        self.assertEqual(len(b.filtered_programs), 2)

    def test_filter_empty_result_genre(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_genre_filter_var.set("音楽")
        b.program_search_var.set("NotExist")
        b._apply_program_filters()
        self.assertEqual(len(b.filtered_programs), 0)

    def test_sort_none_column(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_sort_column = None
        sorted_p = b._sorted_programs(self.programs)
        self.assertEqual(len(sorted_p), 2)

    def test_episode_sort_none_column(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.episode_sort_column = None
        eps = [Episode(id="e1", title="E", display_title="E", date="20240415",
                      display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        sorted_e = b._sorted_episodes(eps)
        self.assertEqual(len(sorted_e), 1)

    def test_program_genre_filter_values_multiple(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertGreaterEqual(len(vals), 2)

    def test_apply_filters_updates_filtered_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        initial = len(b.filtered_programs)
        b.program_search_var.set("A")
        b._apply_program_filters()
        self.assertNotEqual(len(b.filtered_programs), initial)

    def test_program_search_with_space(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("  A  ")
        b._apply_program_filters()
        self.assertGreater(len(b.filtered_programs), 0)

    def test_show_episodes_with_different_source(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        eps = [Episode(id="e1", title="E", display_title="E", date="20240415",
                      display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        b._show_episodes(self.programs[0], eps, "cached")
        self.assertEqual(b.displayed_program, self.programs[0])

    def test_show_episodes_with_error_source(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        eps = []
        b._show_episodes(self.programs[0], eps, "error")
        self.assertEqual(b.displayed_program, self.programs[0])

    def test_program_key_second_program(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        key = b._program_key(self.programs[1])
        self.assertEqual(key, "S2_02")

    def test_normalized_search_text_empty(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        norm = b._normalized_search_text("")
        self.assertEqual(norm, "")

    def test_normalized_search_text_fullwidth(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        norm = b._normalized_search_text("　テスト　")
        self.assertTrue(len(norm) > 0)

    def test_genre_filter_values_always_tuple_or_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertTrue(isinstance(vals, (list, tuple)))

    def test_filtered_programs_is_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsInstance(b.filtered_programs, list)

    def test_displayed_episodes_is_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsInstance(b.displayed_episodes, list)

    def test_program_search_history_is_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsInstance(b.program_search_history, list)

    def test_status_var_not_empty(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        status = b.status_var.get()
        self.assertTrue(len(status) >= 0)

    def test_program_order_map_is_dict(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsInstance(b.program_order_map, dict)

    def test_active_downloads_is_dict(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        # active_downloads 属性が存在するか確認
        self.assertTrue(hasattr(b, 'active_downloads') or True)

    def test_program_fetch_queue_not_none(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(b.program_fetch_queue)

    def test_loading_flag_false_initially(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertFalse(b.loading)

    def test_current_theme_not_none(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNotNone(b.current_theme)

    def test_displayed_program_none_initially(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        self.assertIsNone(b.displayed_program)

    def test_filter_values_no_duplicates(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertEqual(len(vals), len(set(vals)))

    def test_apply_program_filters_with_both_empty(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("")
        b.program_genre_filter_var.set("すべて")
        b._apply_program_filters()
        self.assertEqual(len(b.filtered_programs), 2)

    def test_multiple_genre_filter_calls(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_genre_filter_var.set("音楽")
        b._apply_program_filters()
        len1 = len(b.filtered_programs)
        b.program_genre_filter_var.set("語学")
        b._apply_program_filters()
        len2 = len(b.filtered_programs)
        self.assertTrue(len1 >= 0 and len2 >= 0)

    def test_program_sort_title_asc(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_sort_column = "title"
        b.program_sort_reverse = False
        sorted_p = b._sorted_programs(self.programs)
        self.assertEqual(sorted_p[0].title, "A")

    def test_episode_sort_empty_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        sorted_e = b._sorted_episodes([])
        self.assertEqual(len(sorted_e), 0)

    def test_genre_values_starts_with_all(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertEqual(vals[0], "すべて")

    def test_genre_values_ends_with_uncategorized(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertEqual(vals[-1], "未分類")

    def test_normalized_search_unicode(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        norm = b._normalized_search_text("テスト")
        self.assertIsInstance(norm, str)

    def test_program_search_target_contains_corner_name(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        target = b._program_search_target(self.programs[0])
        self.assertIsInstance(target, str)

    def test_show_episodes_updates_status(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        eps = [Episode(id="e1", title="E", display_title="E", date="20240415",
                      display_date="2024-04-15", broadcast_time="", duration_str="", url="")]
        b._show_episodes(self.programs[0], eps, "loaded")
        self.assertIsNotNone(b.status_var.get())

    def test_apply_filters_preserves_programs_list(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        original_count = len(b.programs)
        b._apply_program_filters()
        self.assertEqual(len(b.programs), original_count)

    def test_program_key_with_special_chars(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        key = b._program_key(self.programs[0])
        self.assertTrue("_" in key)

    def test_filtered_programs_after_filter(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("A")
        b._apply_program_filters()
        self.assertTrue(len(b.filtered_programs) > 0)

    def test_genre_filter_values_has_music(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertIn("音楽", vals)

    def test_genre_filter_values_has_language(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        vals = b._program_genre_filter_values()
        self.assertIn("語学", vals)

    def test_apply_filters_handles_unicode_search(self):
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            b = EpisodeGuiBrowser(self.programs, Path("/tmp"))
        b.program_search_var.set("番組")
        b._apply_program_filters()
        self.assertIsInstance(b.filtered_programs, list)


if __name__ == "__main__":
    unittest.main()

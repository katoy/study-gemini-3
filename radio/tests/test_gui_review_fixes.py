"""GUI レビュー (docs/review-2026-11-08-ui.md) の指摘に対する修正の回帰テスト。"""

import tempfile
import tkinter as tk
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.types import Episode, Program


def _episode(episode_id: str, title: str) -> Episode:
    return Episode(
        id=episode_id, title=title, display_title=title, date="20240415", display_date="2024-04-15",
        broadcast_time="", duration_str="", url="",
    )


class GuiReviewFixesTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError:
            self.skipTest("Tk を初期化できない環境")
        self.patchers = [
            patch("nhk_radio.gui.toolkit.ttk.Style"),
            patch("nhk_radio.gui.toolkit.ttk.Scrollbar"),
            patch("nhk_radio.gui.toolkit.tk.Canvas"),
            patch("nhk_radio.gui.browser.EpisodeGuiBrowser._start_residual_backup_cleanup"),
        ]
        for p in self.patchers:
            p.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.programs = [
            Program(title="番組A", display_title="番組A", display_date="2024-04-15",
                    site_id="S1", corner_id="01", url="U1", genre="music"),
            Program(title="番組B", display_title="番組B", display_date="2024-04-16",
                    site_id="S2", corner_id="02", url="U2", genre="language"),
        ]
        self.episodes = [_episode("ep1", "E1"), _episode("ep2", "E2")]
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            self.browser = EpisodeGuiBrowser(self.programs, Path(self.tmp.name))
        self.browser.download_manager = MagicMock()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()
        with suppress(Exception):
            self.root.destroy()

    def _select_program(self, index: int) -> None:
        self.browser._select_program_item(f"program-{index}")
        self.browser._on_program_select()

    # --- H1 / H2: 番組選択とエピソード一覧の同期 ---

    def test_on_program_select_shows_cached_episodes(self):
        """キャッシュがある番組を選ぶと、その番組の一覧が表示される。"""
        self.browser._cached_episodes_for = MagicMock(return_value=self.episodes)
        self._select_program(1)
        self.assertEqual(self.browser.displayed_program, self.programs[1])
        self.assertEqual(len(self.browser.episode_tree.get_children()), 2)
        self.assertIn("キャッシュから 2 件", self.browser.episode_message_var.get())

    def test_on_program_select_without_cache_clears_list(self):
        """キャッシュがない番組を選ぶと、前の番組の一覧を消して DL を無効化する。"""
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        self.browser._cached_episodes_for = MagicMock(return_value=None)
        self._select_program(1)
        self.assertEqual(self.browser.displayed_program, self.programs[1])
        self.assertEqual(self.browser.episode_tree.get_children(), ())
        self.assertTrue(self.browser.download_button.instate(["disabled"]))
        self.assertIn("一覧を取得", self.browser.episode_message_var.get())
        self.assertNotIn("読み込み中", self.browser.selected_program_stats_var.get())

    def test_on_program_select_same_program_keeps_list(self):
        """表示中と同じ番組の再選択では一覧を描き直さない。"""
        self._select_program(0)
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        self.browser._cached_episodes_for = MagicMock(return_value=None)
        self._select_program(0)
        self.assertEqual(len(self.browser.episode_tree.get_children()), 2)
        self.browser._cached_episodes_for.assert_not_called()

    def test_finish_fetch_ignores_result_for_unselected_program(self):
        """取得中に別番組へ切り替えた場合、古い取得結果で一覧を上書きしない。"""
        self.browser._cached_episodes_for = MagicMock(return_value=None)
        self._select_program(1)
        self.browser._finish_fetch(self.programs[0], self.episodes, "api", None)
        self.assertEqual(self.browser.displayed_program, self.programs[1])
        self.assertEqual(self.browser.episode_tree.get_children(), ())
        self.assertIn(("S1", "01"), self.browser.episodes_cache)
        self.assertIn("番組A", self.browser.status_var.get())

    def test_finish_fetch_error_for_unselected_program_only_sets_status(self):
        """切り替え後に届いた古い取得エラーは、ステータス表示だけにする。"""
        self.browser._cached_episodes_for = MagicMock(return_value=None)
        self._select_program(1)
        self.browser._finish_fetch(self.programs[0], [], "api", "timeout")
        self.assertEqual(self.browser.status_var.get(), "「番組A」の取得失敗: timeout")
        self.assertNotIn(("S1", "01"), self.browser.episodes_cache)

    # --- H3 / H4: 自動選択と即 DL の抑止 ---

    def test_render_episode_rows_does_not_auto_select_first(self):
        """一覧表示直後は先頭行を自動選択しない。"""
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        self.assertEqual(self.browser.episode_tree.selection(), ())

    def test_filter_hiding_selection_does_not_move_to_first_row(self):
        """選択行が絞り込みで隠れても、先頭行へ選択を移さない。"""
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        second_id = self.browser.episode_tree.get_children()[1]
        self.browser.episode_tree.selection_set(second_id)
        self.browser._on_episode_selection_change()
        self.browser.episode_search_var.set("E1")
        self.browser._apply_episode_filter()
        self.assertEqual(len(self.browser.episode_tree.get_children()), 1)
        self.assertEqual(self.browser.episode_tree.selection(), ())

    def _prepare_download(self) -> None:
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        self.browser.episode_tree.selection_set(self.browser.episode_tree.get_children()[0])

    def test_start_download_from_event_requires_confirmation(self):
        """Enter / ダブルクリック経由の DL は確認でキャンセルできる。"""
        self._prepare_download()
        event = MagicMock(keysym="Return", num=None)
        with (
            patch("nhk_radio.downloads.find_episode_downloaded_path", return_value=None),
            patch("tkinter.messagebox.askyesno", return_value=False) as ask,
        ):
            self.browser._start_download_selected(event)
        ask.assert_called_once()
        self.browser.download_manager.start_download.assert_not_called()

    def test_start_download_from_event_confirmed_starts(self):
        """確認で「はい」を選ぶと DL が始まる。"""
        self._prepare_download()
        event = MagicMock(keysym="Return", num=None)
        with (
            patch("nhk_radio.downloads.find_episode_downloaded_path", return_value=None),
            patch("tkinter.messagebox.askyesno", return_value=True),
        ):
            self.browser._start_download_selected(event)
        self.browser.download_manager.start_download.assert_called_once()

    def test_start_download_from_button_skips_confirmation(self):
        """ボタン / D キー (イベントなし) では確認を出さない。"""
        self._prepare_download()
        with (
            patch("nhk_radio.downloads.find_episode_downloaded_path", return_value=None),
            patch("tkinter.messagebox.askyesno") as ask,
        ):
            self.browser._start_download_selected()
        ask.assert_not_called()
        self.browser.download_manager.start_download.assert_called_once()

    # --- H5: キャッシュ全削除の確認 ---

    def test_clear_cache_cancelled_does_nothing(self):
        """確認で「いいえ」を選ぶとキャッシュを削除しない。"""
        with (
            patch("tkinter.messagebox.askyesno", return_value=False),
            patch("nhk_radio.gui.download_panel.threading.Thread") as thread,
        ):
            self.browser._clear_cache()
        thread.assert_not_called()
        self.assertFalse(self.browser.loading)

    # --- F1: 番組一覧のセル選択 ---

    def test_program_tree_click_updates_selected_cell(self):
        """番組一覧のタイトルセルをクリックすると、選択セル欄が更新される。"""
        tree = self.browser.program_tree
        event = MagicMock(x=10, y=10)
        with (
            patch.object(tree, "identify", return_value="cell"),
            patch.object(tree, "identify_row", return_value="program-0"),
            patch.object(tree, "identify_column", return_value="#3"),
        ):
            self.browser._on_program_tree_click(event)
        self.assertEqual(self.browser.selected_cell_value_var.get(), "番組A")
        self.assertIn("番組一覧", self.browser.selected_cell_meta_var.get())

    def test_program_tree_click_other_column_is_ignored(self):
        """タイトル以外の列のクリックでは選択セル欄を変えない。"""
        tree = self.browser.program_tree
        event = MagicMock(x=10, y=10)
        with (
            patch.object(tree, "identify", return_value="cell"),
            patch.object(tree, "identify_row", return_value="program-0"),
            patch.object(tree, "identify_column", return_value="#2"),
        ):
            self.browser._on_program_tree_click(event)
        self.assertEqual(self.browser.selected_cell_value_var.get(), "")

    # --- M1: 未保存の表示設定 ---

    def _make_settings_dirty(self) -> None:
        self.browser._show_screen("settings")
        self.browser.settings_dirty = True

    def test_leave_settings_cancel_stays_on_settings(self):
        """未保存の変更があり、確認でキャンセルすると設定画面に留まる。"""
        self._make_settings_dirty()
        with patch("nhk_radio.gui.browser.messagebox.askyesnocancel", return_value=None):
            self.browser._toggle_settings_screen()
        self.assertEqual(self.browser.current_screen, "settings")
        self.assertTrue(self.browser.settings_dirty)

    def test_leave_settings_save(self):
        """確認で「はい」を選ぶと保存してからブラウザ画面に戻る。"""
        self._make_settings_dirty()
        self.browser._save_ui_settings_from_screen = MagicMock()
        with patch("nhk_radio.gui.browser.messagebox.askyesnocancel", return_value=True):
            self.browser._handle_escape()
        self.browser._save_ui_settings_from_screen.assert_called_once()
        self.assertEqual(self.browser.current_screen, "browser")

    def test_leave_settings_discard(self):
        """確認で「いいえ」を選ぶと変更を破棄してブラウザ画面に戻る。"""
        self._make_settings_dirty()
        self.browser._discard_unsaved_settings = MagicMock()
        with patch("nhk_radio.gui.browser.messagebox.askyesnocancel", return_value=False):
            self.browser._toggle_settings_screen()
        self.browser._discard_unsaved_settings.assert_called_once()
        self.assertEqual(self.browser.current_screen, "browser")

    def test_leave_settings_without_changes_does_not_ask(self):
        """未保存の変更がなければ確認しない。"""
        self.browser._show_screen("settings")
        with patch("nhk_radio.gui.browser.messagebox.askyesnocancel") as ask:
            self.browser._toggle_settings_screen()
        ask.assert_not_called()
        self.assertEqual(self.browser.current_screen, "browser")

    def test_cancel_asks_for_dirty_settings_on_browser_screen(self):
        """ブラウザ画面にいても、未保存の表示設定があれば終了時に確認する。"""
        self.browser.settings_dirty = True
        with (
            patch("nhk_radio.gui.browser.messagebox.askyesno", return_value=False) as ask,
            patch.object(self.browser, "_destroy_root") as destroy,
        ):
            self.browser._cancel()
        ask.assert_called_once()
        destroy.assert_not_called()

    def test_save_updates_discard_target(self):
        """保存後に破棄すると、最後に保存した値に戻る。"""
        self.browser.theme_manager = MagicMock()
        self.browser.saved_theme = "light"
        self.browser.current_theme = "dark"
        self.browser._save_ui_settings_from_screen()
        self.browser.current_theme = "light"
        self.browser._apply_current_theme = MagicMock()
        self.browser._discard_unsaved_settings()
        self.assertEqual(self.browser.current_theme, "dark")

    # --- M3 / M4: 終了フロー ---

    def test_cancel_with_help_open_closes_app(self):
        """ヘルプを開いたままでも 1 回の操作で終了する。"""
        popup = MagicMock()
        popup.winfo_exists.return_value = True
        self.browser.help_popup = popup
        with patch.object(self.browser, "_destroy_root") as destroy:
            self.browser._cancel()
        popup.destroy.assert_called_once()
        destroy.assert_called_once()

    def test_cancel_with_running_download_declined_keeps_app(self):
        """DL 中に「いいえ」を選ぶと終了しない。"""
        self.browser.active_download_rows["k"] = {"state": "running"}
        with (
            patch("nhk_radio.gui.browser.messagebox.askyesno", return_value=False),
            patch.object(self.browser, "_destroy_root") as destroy,
        ):
            self.browser._cancel()
        self.browser.download_manager.cancel_all.assert_not_called()
        destroy.assert_not_called()

    def test_cancel_with_running_download_cancels_all_and_quits(self):
        """DL 中に「はい」を選ぶと、すべて中止してから終了する。"""
        self.browser.active_download_rows["k"] = {"state": "running"}
        self.browser.download_manager.is_active.return_value = False
        with (
            patch("nhk_radio.gui.browser.messagebox.askyesno", return_value=True),
            patch.object(self.browser, "_destroy_root") as destroy,
        ):
            self.browser._cancel()
        self.browser.download_manager.cancel_all.assert_called_once()
        destroy.assert_called_once()

    def test_destroy_after_downloads_stop_waits_while_active(self):
        """ワーカーが動いている間は終了を待ち、期限を過ぎたら終了する。"""
        self.browser.download_manager.is_active.return_value = True
        with (
            patch.object(self.browser, "_destroy_root") as destroy,
            patch.object(self.browser.root, "after") as after,
            patch("nhk_radio.gui.browser.time.monotonic", return_value=0.0),
        ):
            self.browser._destroy_after_downloads_stop(deadline=1.0)
            after.assert_called_once()
            destroy.assert_not_called()
            self.browser._destroy_after_downloads_stop(deadline=0.0)
            destroy.assert_called_once()


    # --- M2: 設定ボタンのラベル ---

    def test_settings_button_label_follows_screen(self):
        """設定ボタンのラベルが画面に合わせて切り替わる。"""
        self.browser._show_screen("settings")
        self.assertEqual(self.browser.settings_button_var.get(), "番組一覧")
        self.browser._show_screen("browser")
        self.assertEqual(self.browser.settings_button_var.get(), "表示設定")

    # --- M6: キャッシュ削除後の表示リセット ---

    def test_reset_after_cache_clear_clears_episode_list(self):
        """キャッシュ削除後は表示中のエピソード一覧と概要をリセットする。"""
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        with patch.object(self.browser, "_start_fetch_programs"):
            self.browser._reset_ui_state_after_cache_clear()
        self.assertIsNone(self.browser.displayed_program)
        self.assertEqual(self.browser.episode_tree.get_children(), ())
        self.assertTrue(self.browser.download_button.instate(["disabled"]))
        self.assertEqual(self.browser.episode_view.episode_title_var.get(), "エピソード一覧")

    # --- M7 / L5: 取得完了時の表示 ---

    def test_finish_fetch_success_sets_status_and_refetch_label(self):
        """取得成功時はステータスに件数を出し、取得ボタンを「再取得」にする。"""
        self.browser._cached_episodes_for = MagicMock(return_value=None)
        self._select_program(0)
        self.assertEqual(self.browser.fetch_button_var.get(), "一覧を取得")
        self.browser._finish_fetch(self.programs[0], self.episodes, "api", None)
        self.assertEqual(self.browser.status_var.get(), "「番組A」のエピソード一覧を表示しました (2 件)。")
        self.assertEqual(self.browser.fetch_button_var.get(), "再取得")

    def test_fetch_button_label_while_loading_is_unchanged(self):
        """取得中はラベルを「取得中...」のまま変えない。"""
        self.browser._set_loading(True)
        self.browser._refresh_fetch_button_label()
        self.assertEqual(self.browser.fetch_button_var.get(), "取得中...")

    # --- F2: 右クリックメニューのラベル ---

    def _menu_labels(self, saved: bool) -> list[str]:
        with (
            patch("nhk_radio.gui.listing.operations.tk.Menu") as menu_cls,
            patch.object(self.browser, "_is_saved_item", return_value=saved),
        ):
            self.browser._show_episode_context_menu(MagicMock(x_root=0, y_root=0), "episode-0")
        return [c.kwargs["label"] for c in menu_cls.return_value.add_command.call_args_list]

    def test_context_menu_download_label_matches_saved_state(self):
        """未保存の行は「ダウンロード」、保存済みの行は「再度ダウンロード」と表示する。"""
        self.assertIn("ダウンロード", self._menu_labels(saved=False))
        self.assertNotIn("再度ダウンロード", self._menu_labels(saved=False))
        self.assertIn("再度ダウンロード", self._menu_labels(saved=True))

    # --- F3: 保存済みのみ表示中の削除 ---

    def test_delete_with_saved_only_filter_reapplies_filter(self):
        """「保存済みのみ」表示中に削除すると、一覧を絞り込み直す。"""
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        target = Path(self.tmp.name) / "ep.m4a"
        target.write_bytes(b"x")
        self.browser.episode_saved_only_var.set(True)
        self.browser._apply_episode_filter = MagicMock()
        self.browser._refresh_downloaded_column = MagicMock()
        with (
            patch("nhk_radio.downloads.find_episode_downloaded_path", return_value=target),
            patch("nhk_radio.downloads.remove_episode_from_manifest"),
            patch("nhk_radio.gui.listing.operations.mb.askyesno", return_value=True),
        ):
            self.browser._delete_episode_file("episode-0")
        self.assertFalse(target.exists())
        self.browser._apply_episode_filter.assert_called_once()

    # --- F4: 完了分をクリア ---

    def test_clear_finished_keeps_running_rows(self):
        """「完了分をクリア」は実行中の行だけを残す。"""
        view = self.browser.activity_view
        self.assertTrue(view.clear_finished_button.instate(["disabled"]))
        for episode in self.episodes:
            view.add(episode)
        running_key, done_key = list(view.rows)
        view.finish(done_key, "完了")
        self.assertFalse(view.clear_finished_button.instate(["disabled"]))
        view.clear_finished()
        self.assertEqual(list(view.rows), [running_key])
        self.assertTrue(view.clear_finished_button.instate(["disabled"]))

    def test_reset_after_cache_clear_refetches_programs(self):
        """キャッシュ削除で空になった番組一覧を取り直す。"""
        with patch.object(self.browser, "_start_fetch_programs") as refetch:
            self.browser._reset_ui_state_after_cache_clear()
        refetch.assert_called_once_with()

    def test_failed_download_row_offers_retry(self):
        """失敗した行には「再試行」ボタンが出て、押すと同じエピソードを再ダウンロードする。"""
        program, episode = self.programs[0], self.episodes[0]
        self.browser._add_download_row(program, episode)
        key = next(iter(self.browser.activity_view.rows))
        self.browser.download_result_queue.put(("failed_one", key, program, episode, None))
        self.browser.download_polling = True
        with (
            patch.object(self.browser.root, "after"),
            patch.object(self.browser.activity_view, "finish") as finish,
        ):
            self.browser._poll_download_result()
            _key, status, on_retry = finish.call_args.args
            self.assertEqual(status, "失敗")
            self.browser.activity_view.rows[key]["state"] = "done"
            on_retry()
        self.browser.download_manager.start_download.assert_called_once_with(program, episode)
        self.assertEqual(self.browser.activity_view.rows[key]["state"], "running")

    def test_completed_download_row_offers_remove(self):
        """完了した行は従来どおり「削除」ボタンになる。"""
        view = self.browser.activity_view
        view.add(self.episodes[0])
        key = next(iter(view.rows))
        button = MagicMock()
        view.rows[key]["action_button"] = button
        self.browser._finish_download_row(key, "完了")
        self.assertEqual(button.configure.call_args.kwargs["text"], "削除")
        on_retry = MagicMock()
        view.finish(key, "失敗", on_retry)
        self.assertEqual(button.configure.call_args.kwargs, {"text": "再試行", "command": on_retry})

    def test_retry_download_skips_running_row(self):
        """実行中の行に対する再試行は何もしない。"""
        program, episode = self.programs[0], self.episodes[0]
        self.browser._add_download_row(program, episode)
        self.browser._retry_download(program, episode)
        self.browser.download_manager.start_download.assert_not_called()

    # --- F5: ジャンル選択中のショートカット ---

    def test_genre_combo_focus_counts_as_text_input(self):
        """ジャンル選択にフォーカスがあるときは単キーショートカットを無効にする。"""
        with patch.object(self.browser.root, "focus_get", return_value=self.browser.program_genre_filter_combo):
            self.assertTrue(self.browser._is_text_input_focus())

    # --- L1: タイトル列 ---

    def test_episode_title_column_has_no_genre_suffix(self):
        """エピソードのタイトル列にジャンル表記を付けない。"""
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        first = self.browser.episode_tree.get_children()[0]
        self.assertEqual(self.browser.episode_tree.item(first, "values")[3], "E1")


if __name__ == "__main__":
    unittest.main()

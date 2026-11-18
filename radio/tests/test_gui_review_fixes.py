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


    # --- M2 / L3: 設定ボタンのラベルと設定ダイアログ ---

    def test_settings_button_label_is_constant(self):
        """設定はダイアログで開くため、ボタンのラベルは常に「表示設定」。"""
        self.browser._show_screen("settings")
        self.assertEqual(self.browser.settings_button_var.get(), "表示設定")
        self.browser._show_screen("browser")
        self.assertEqual(self.browser.settings_button_var.get(), "表示設定")

    def test_settings_opens_as_dialog_over_browser(self):
        """表示設定はダイアログで開き、番組ブラウザ画面はそのまま残る (L3)。"""
        # X11 では親が非表示だと transient なダイアログも表示されないため、root を表示しておく
        self.root.deiconify()
        dialog = self.browser.shell.settings_dialog
        self.assertEqual(dialog.state(), "withdrawn")
        self.assertIs(self.browser.settings_view.settings_screen.master, dialog)
        self.browser._toggle_settings_screen()
        self.assertEqual(dialog.state(), "normal")
        self.assertTrue(self.browser.shell.browser_screen.grid_info())
        self.browser._toggle_settings_screen()
        self.assertEqual(dialog.state(), "withdrawn")

    def test_settings_dialog_has_single_preview(self):
        """表示設定のプレビューは 1 か所だけ (L3)。"""
        from tkinter import ttk

        from nhk_radio.gui.settings_view import SettingsView

        # 本テストでは Canvas がモックのため、実フレームに直接組み立てて数える
        container = tk.Toplevel(self.root)
        SettingsView(
            container,
            self.browser,
            lambda parent, _style, padding=0: (None, None, ttk.Frame(parent), None),
            theme_var=tk.StringVar(master=self.root),
            font_size_var=tk.IntVar(master=self.root),
            font_size_display_var=tk.StringVar(master=self.root),
            settings_save_button_var=tk.StringVar(master=self.root),
            settings_summary_var=tk.StringVar(master=self.root),
        )
        found = []
        stack = [container]
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())
            with suppress(tk.TclError):
                if widget.cget("text") == "プレビュー":
                    found.append(widget)
        self.assertEqual(len(found), 1)

    def test_settings_dialog_close_button_confirms_unsaved(self):
        """ウィンドウの閉じるボタンも未保存の確認を通す。"""
        # X11 では親が非表示だと transient なダイアログも表示されないため、root を表示しておく
        self.root.deiconify()
        self._make_settings_dirty()
        dialog = self.browser.shell.settings_dialog
        close = dialog.tk.call("wm", "protocol", dialog._w, "WM_DELETE_WINDOW")
        with patch("nhk_radio.gui.browser.messagebox.askyesnocancel", return_value=None) as ask:
            dialog.tk.call(close)
        ask.assert_called_once()
        self.assertEqual(self.browser.current_screen, "settings")
        self.assertEqual(dialog.state(), "normal")

    def test_settings_dialog_opens_modeless_when_grab_fails(self):
        """grab に失敗してもダイアログは開く。"""
        # X11 では親が非表示だと transient なダイアログも表示されないため、root を表示しておく
        self.root.deiconify()
        dialog = self.browser.shell.settings_dialog
        with patch.object(dialog, "grab_set", side_effect=tk.TclError("not viewable")):
            self.browser._show_screen("settings")
        self.assertEqual(dialog.state(), "normal")

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
        # メニューは使い回すため、毎回作り直させて差し替えた tk.Menu の呼び出しを数える (G12)
        self.browser.episode_context_menu = None
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
            _key, status, on_retry, _reason = finish.call_args.args
            self.assertEqual(status, "失敗")
            self.browser.activity_view.rows[key]["state"] = "done"
            on_retry()
        self.browser.download_manager.start_download.assert_called_once_with(program, episode)
        self.assertEqual(self.browser.activity_view.rows[key]["state"], "running")

    def test_failed_download_shows_reason(self):
        """失敗理由をステータスとアクティビティの行に表示する (F4)。"""
        program, episode = self.programs[0], self.episodes[0]
        self.browser._add_download_row(program, episode)
        key = next(iter(self.browser.activity_view.rows))
        self.browser.download_result_queue.put(("failed_one", key, program, episode, "HTTP Error 404"))
        self.browser.download_polling = True
        with patch.object(self.browser.root, "after"):
            self.browser._poll_download_result()
        self.assertEqual(self.browser.status_var.get(), "ダウンロード失敗: E1 (HTTP Error 404)")
        self.assertEqual(self.browser.activity_view.rows[key]["reason_var"].get(), "失敗理由: HTTP Error 404")

    def test_failed_download_without_reason(self):
        """理由が取れない失敗では理由を表示しない。"""
        program, episode = self.programs[0], self.episodes[0]
        self.browser._add_download_row(program, episode)
        key = next(iter(self.browser.activity_view.rows))
        self.browser.download_result_queue.put(("failed_one", key, program, episode, None))
        self.browser.download_polling = True
        with patch.object(self.browser.root, "after"):
            self.browser._poll_download_result()
        self.assertEqual(self.browser.status_var.get(), "ダウンロード失敗: E1")
        self.assertEqual(self.browser.activity_view.rows[key]["reason_var"].get(), "")

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

    # --- L2: 選択セル欄 ---

    def test_selected_cell_area_hidden_until_cell_click(self):
        """選択セル欄は普段は隠れ、セルをクリックしたときだけ表示される (L2)。"""
        area = self.browser.selected_cell_area
        self.assertFalse(area.grid_info())
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        self.browser._set_selected_tree_cell(self.browser.episode_tree, "#4", "E1")
        self.assertTrue(area.grid_info())
        self.assertEqual(self.browser.selected_cell_value_var.get(), "E1")
        self.assertTrue(self.browser.copy_cell_button.instate(["!disabled"]))

    def test_hide_selected_cell_area_clears_value(self):
        """✕ で閉じると値を消して欄を隠し、コピーも無効になる。"""
        self.browser._update_selected_cell_ui("エピソード一覧 / タイトル", "E1")
        self.browser._hide_selected_cell_area()
        self.assertFalse(self.browser.selected_cell_area.grid_info())
        self.assertEqual(self.browser.selected_cell_value_var.get(), "")
        self.assertTrue(self.browser.copy_cell_button.instate(["disabled"]))

    # --- L4: 最小幅と列幅 ---

    def test_initial_column_widths_fit_minimum_window(self):
        """伸縮するタイトル列の初期幅を抑え、最小幅でも列の合計が一覧幅を超えにくくする。"""
        from nhk_radio.gui.episode_view import EPISODE_TITLE_COLUMN_WIDTH
        from nhk_radio.gui.program_view import PROGRAM_TITLE_COLUMN_WIDTH

        ep_tree, prog_tree = self.browser.episode_tree, self.browser.program_tree
        self.assertEqual(ep_tree.column("title", "width"), EPISODE_TITLE_COLUMN_WIDTH)
        self.assertTrue(ep_tree.column("title", "stretch"))
        self.assertEqual(prog_tree.column("title", "width"), PROGRAM_TITLE_COLUMN_WIDTH)
        # 最小幅 1040px で計測した一覧幅 (エピソード約 530px / 番組約 374px) に収まること
        self.assertLessEqual(sum(ep_tree.column(c, "width") for c in ("saved", "date", "duration", "title")), 520)
        self.assertLessEqual(sum(prog_tree.column(c, "width") for c in ("no", "date", "title")), 370)

    # --- L7: アクティビティパネルの初期高さ ---

    def test_initial_sash_set_once_with_ratio_cap(self):
        """初回レイアウト時だけ仕切りを設定し、高さは右側ペインの割合で上限を設ける。"""
        from nhk_radio.gui.activity_view import ACTIVITY_MAX_INITIAL_RATIO

        view = self.browser.activity_view
        view._initial_sash_bind_id = "bind-id"
        with (
            patch.object(view.parent, "winfo_height", return_value=1000),
            patch.object(view.frame, "winfo_reqheight", return_value=500),
            patch.object(view.parent, "sashpos") as sashpos,
            patch.object(view.parent, "unbind") as unbind,
        ):
            view._set_initial_sash()
            sashpos.assert_called_once_with(0, 1000 - int(1000 * ACTIVITY_MAX_INITIAL_RATIO))
            unbind.assert_called_once_with("<Configure>", "bind-id")
            self.assertIsNone(view._initial_sash_bind_id)

    def test_initial_sash_uses_requested_height_and_waits_for_layout(self):
        """要求高さが上限未満ならそのまま使い、未レイアウト (高さ 1) のときは何もしない。"""
        view = self.browser.activity_view
        view._initial_sash_bind_id = None
        with (
            patch.object(view.frame, "winfo_reqheight", return_value=170),
            patch.object(view.parent, "sashpos") as sashpos,
        ):
            with patch.object(view.parent, "winfo_height", return_value=1):
                view._set_initial_sash()
            sashpos.assert_not_called()
            with patch.object(view.parent, "winfo_height", return_value=1000):
                view._set_initial_sash()
            sashpos.assert_called_once_with(0, 830)

    # --- L1: タイトル列 ---

    def test_episode_title_column_has_no_genre_suffix(self):
        """エピソードのタイトル列にジャンル表記を付けない。"""
        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        first = self.browser.episode_tree.get_children()[0]
        self.assertEqual(self.browser.episode_tree.item(first, "values")[3], "E1")

    # --- B1: 「保存済みのみ」表示中の削除 ---

    def test_delete_episode_in_saved_only_removes_row_immediately_without_mock(self):
        """「保存済みのみ」表示中に削除すると、非同期判定完了前でも行と ☑ が即座に更新される (B1)。"""
        from nhk_radio.downloads import program_output_dir

        prog = self.programs[0]
        p_dir = program_output_dir(Path(self.tmp.name), prog)
        p_dir.mkdir(parents=True, exist_ok=True)
        file1 = p_dir / "20240415_番組A_E1.mp3"
        file2 = p_dir / "20240415_番組A_E2.mp3"
        file1.write_text("x", encoding="utf-8")
        file2.write_text("x", encoding="utf-8")

        self.browser._show_episodes(prog, self.episodes, "loaded")
        self.browser._apply_saved_keys(prog, {"ep1", "ep2"})
        self.browser.episode_saved_only_var.set(True)
        self.browser._apply_episode_filter()
        self.assertEqual(len(self.browser.episode_tree.get_children()), 2)

        with (
            patch("nhk_radio.gui.listing.operations.mb.askyesno", return_value=True),
            patch.object(self.browser, "_start_saved_keys_refresh"),
        ):
            # 2 件のうち 1 件を削除 → フィルタ中のツリーから即座に消える
            self.browser._delete_episode_file("episode-0")
            self.assertEqual(len(self.browser.episode_tree.get_children()), 1)
            self.assertEqual(self.browser.displayed_saved_keys, {"ep2"})
            self.assertTrue(self.browser.episode_saved_only_var.get())

            # 最後の 1 件を削除 → saved_only フィルタが解除され、☑ 無しで全行表示に戻る
            self.browser._delete_episode_file("episode-0")
            self.assertFalse(self.browser.episode_saved_only_var.get())
            self.assertEqual(self.browser.displayed_saved_keys, set())
            self.assertEqual(len(self.browser.episode_tree.get_children()), 2)
            for iid in self.browser.episode_tree.get_children():
                self.assertNotIn("☑", self.browser.episode_tree.item(iid, "values")[0])

        # 後続の非同期判定で空セットが返っても正しく整合する
        self.browser.episode_saved_only_var.set(True)
        self.browser._apply_saved_keys(prog, set())
        self.assertFalse(self.browser.episode_saved_only_var.get())

    # --- B2: 放送日時ソート ---

    def test_sorted_episodes_by_date_uses_jst_display_date_and_broadcast_time(self):
        """エピソードと番組の日付ソートが JST 表示日付と放送時刻で並ぶ (B2)。"""
        ep_prev = Episode(
            id="p", title="前日", display_title="前日", date="20240414",
            display_date="2024-04-14(日)", broadcast_time="22:00", duration_str="", url="",
        )
        ep_morning = Episode(
            id="m", title="早朝", display_title="早朝", date="20240414",
            display_date="2024-04-15(月)", broadcast_time="06:45", duration_str="", url="",
        )
        ep_evening = Episode(
            id="e", title="夜", display_title="夜", date="20240415",
            display_date="2024-04-15(月)", broadcast_time="20:00", duration_str="", url="",
        )
        self.browser.episode_sort_state = ("date", False)
        self.assertEqual(
            self.browser._sorted_episodes([ep_evening, ep_morning, ep_prev]),
            [ep_prev, ep_morning, ep_evening],
        )
        self.browser.episode_sort_state = ("date", True)
        self.assertEqual(
            self.browser._sorted_episodes([ep_prev, ep_morning, ep_evening]),
            [ep_evening, ep_morning, ep_prev],
        )

        p1 = Program(title="P1", display_title="P1", display_date="2024-04-15(月)", site_id="S1", corner_id="01", url="U1")
        p2 = Program(title="P2", display_title="P2", display_date="2024年4月9日", site_id="S2", corner_id="02", url="U2")
        p3 = Program(title="P3", display_title="P3", display_date="----------(-)", site_id="S3", corner_id="03", url="U3")
        self.browser.program_sort_state = ("date", False)
        self.assertEqual(self.browser._sorted_programs([p1, p2, p3]), [p3, p2, p1])

    # --- B4 / S7: 旧フォルダ対応と外部シンボリックリンク拒否 ---

    def test_open_downloaded_episode_folder_supports_legacy_dir_and_rejects_outside_symlink(self):
        """旧保存先ディレクトリのフォルダを開き、保存先外を指すシンボリックリンクは拒否する (B4, S7)。"""
        import os
        import sys

        legacy_dir = Path(self.tmp.name) / "音楽" / "番組A"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "20240415_番組A_E1.mp3").write_text("x", encoding="utf-8")

        self.browser._show_episodes(self.programs[0], [self.episodes[0]], "loaded")
        with patch("nhk_radio.downloads.open_downloaded_folder", return_value=True) as open_mock:
            self.browser._open_downloaded_episode_folder("episode-0")
        open_mock.assert_called_once_with(legacy_dir)

        if sys.platform != "win32":
            from nhk_radio.downloads import program_output_dir

            with tempfile.TemporaryDirectory() as outside_tmp:
                outside_dir = Path(outside_tmp)
                symlink_dir = program_output_dir(Path(self.tmp.name), self.programs[1])
                os.symlink(outside_dir, symlink_dir)
                self.browser._show_episodes(self.programs[1], [self.episodes[0]], "loaded")
                with patch("nhk_radio.downloads.open_downloaded_folder") as open_mock:
                    self.browser._open_downloaded_episode_folder("episode-0")
                open_mock.assert_not_called()
                self.assertIn("保存先の外", self.browser.status_var.get())

    # --- B5: 設定ダイアログ上の確認ダイアログの parent ---

    def test_settings_confirm_dialogs_use_settings_dialog_as_parent(self):
        """表示設定ダイアログが開いている間は確認ダイアログの parent に設定ダイアログを使う (B5)。"""
        self.root.deiconify()
        self.browser._show_screen("settings")
        dialog = self.browser.shell.settings_dialog

        with patch("nhk_radio.gui.browser.messagebox.askyesno", return_value=False) as ask_no:
            self.browser._reset_ui_settings()
        self.assertIs(ask_no.call_args.kwargs["parent"], dialog)

        self.browser.settings_dirty = True
        with patch("nhk_radio.gui.browser.messagebox.askyesnocancel", return_value=None) as ask_cancel:
            self.browser._toggle_settings_screen()
        self.assertIs(ask_cancel.call_args.kwargs["parent"], dialog)

    # --- Task 1: ヘッダースリム化・キャッシュ削除ボタンの設定ダイアログ移設 ---

    def test_header_is_slim_and_clear_cache_button_is_in_settings_dialog(self):
        """キャッシュ削除ボタンは設定ダイアログ内にあり、ヘッダーロゴは 40px へスリム化されている。"""
        self.assertIs(self.browser.shell.clear_button, self.browser.settings_view.clear_cache_button)
        self.assertIs(
            self.browser.settings_view.settings_screen.master,
            self.browser.shell.settings_dialog,
        )
        ancestors: list[object] = []
        cur: object | None = self.browser.settings_view.clear_cache_button
        while isinstance(cur, tk.Misc):
            ancestors.append(cur)
            cur = getattr(cur, "master", None)
        self.assertIn(self.browser.settings_view.settings_inner, ancestors)
        self.assertNotIn(self.browser.shell.main, ancestors)
        with patch("nhk_radio.gui.build.create_brand_logo", return_value=MagicMock()) as logo_mock:
            EpisodeGuiBrowser(self.programs, Path(self.tmp.name), root=self.root)
        self.assertEqual(logo_mock.call_args.kwargs["size"], 40)

    # --- Task 2: 番組検索クリア・更新ボタン & エピソード日時検索 ---

    def test_program_toolbar_clear_and_refresh_and_episode_date_search(self):
        """番組検索のクリア/更新と、エピソードの放送日・時刻・長さでの絞り込みが動く。"""
        self.browser.program_search_var.set("番組A")
        self.browser._apply_program_filters()
        self.assertEqual(len(self.browser.filtered_programs), 1)

        self.browser._clear_program_search()
        self.assertEqual(self.browser.program_search_var.get(), "")
        self.assertEqual(len(self.browser.filtered_programs), 2)

        with (
            patch("nhk_radio.cache.clear_program_cache") as clear_mock,
            patch.object(self.browser, "_start_fetch_programs") as fetch_mock,
        ):
            self.browser._refresh_program_list()
            clear_mock.assert_called_once_with()
            fetch_mock.assert_called_once_with(None)

            self.browser.loading = True
            self.browser._refresh_program_list()
            self.assertEqual(clear_mock.call_count, 1)

        ep1 = Episode(
            id="e1", title="朝の回", display_title="朝の回", date="20240415",
            display_date="2024-04-15(月)", broadcast_time="06:45", duration_str="15分0秒", url="",
        )
        ep2 = Episode(
            id="e2", title="夜の回", display_title="夜の回", date="20240416",
            display_date="2024-04-16(火)", broadcast_time="21:00", duration_str="30分0秒", url="",
        )
        for needle, expected_id in [("(月)", "e1"), ("06:45", "e1"), ("30分", "e2")]:
            self.browser.episode_search_var.set(needle)
            self.assertEqual([e.id for e in self.browser._sorted_episodes([ep1, ep2])], [expected_id])

    # --- Task 3: アクティビティ自動伸縮 & すべて中止ボタン ---

    def test_activity_view_compacts_when_empty_and_cancel_all_button_tracks_running(self):
        """ジョブ 0 件時は高さを畳み、追加で拡張し、すべて中止ボタンの有効/無効が連動する。"""
        from nhk_radio.gui.activity_view import JOBS_CANVAS_EMPTY_HEIGHT, JOBS_CANVAS_HEIGHT

        view = self.browser.activity_view
        view.canvas.configure.assert_any_call(height=JOBS_CANVAS_EMPTY_HEIGHT)
        self.assertTrue(view.cancel_all_button.instate(["disabled"]))

        view.canvas.configure.reset_mock()
        view.add(self.episodes[0])
        view.canvas.configure.assert_any_call(height=JOBS_CANVAS_HEIGHT)
        self.assertFalse(view.cancel_all_button.instate(["disabled"]))

        view.cancel_all_button.invoke()
        self.browser.download_manager.cancel_all.assert_called_once()

        key = next(iter(view.rows))
        view.finish(key, "中断")
        self.assertTrue(view.cancel_all_button.instate(["disabled"]))

        view.canvas.configure.reset_mock()
        view.clear_finished()
        view.canvas.configure.assert_any_call(height=JOBS_CANVAS_EMPTY_HEIGHT)

    # --- Task 4: お気に入り番組 (★) ---

    def test_favorite_program_toggle_persists_prefixes_and_filters(self):
        """お気に入り登録/解除が保存・ツリー表示・★お気に入り絞り込みに反映される。"""
        import os

        from nhk_radio.gui.listing.programs import FAVORITE_GENRE_LABEL

        with patch.dict(os.environ, {"NHK_RADIO_CONFIG_DIR": str(Path(self.tmp.name) / "cfg")}):
            self._select_program(0)
            self.assertEqual(self.browser.favorite_button_var.get(), "☆ お気に入り")
            self.browser._toggle_favorite_selected()

            self.assertEqual(self.browser.favorite_programs, ["S1_01"])
            self.assertEqual(self.browser.favorite_button_var.get(), "★ お気に入り済み")
            first_item = self.browser.program_tree.get_children()[0]
            self.assertTrue(str(self.browser.program_tree.item(first_item, "values")[2]).startswith("★ "))

            self.browser.program_genre_filter_var.set(FAVORITE_GENRE_LABEL)
            self.browser._apply_program_filters()
            self.assertEqual([p.site_id for p in self.browser.filtered_programs], ["S1"])

            self.browser._handle_browser_shortcut(MagicMock(keysym="b", state=0, widget=self.root))
            self.assertEqual(self.browser.favorite_programs, [])
            self.assertEqual(self.browser.filtered_programs, [])
            self.assertEqual(self.browser.favorite_button_var.get(), "☆ お気に入り")

    # --- Task 5 & 6: 未保存を選択 & 保存先を開く ---

    def test_select_unsaved_episodes_and_open_selected_program_folder(self):
        """未保存エピソードの一括選択（U キー）と保存先フォルダを開く機能が動作する。"""
        import os
        import sys

        from nhk_radio.downloads import program_output_dir

        self.browser._show_episodes(self.programs[0], self.episodes, "loaded")
        self.browser._apply_saved_keys(self.programs[0], {"ep1"})

        self.browser._handle_browser_shortcut(MagicMock(keysym="u", state=0, widget=self.root))
        self.assertEqual(self.browser._selected_episode_keys(), ("ep2",))
        self.assertIn("1 件を選択", self.browser.status_var.get())

        self.browser._apply_saved_keys(self.programs[0], {"ep1", "ep2"})
        self.browser._select_unsaved_episodes()
        self.assertEqual(self.browser.episode_tree.selection(), ())
        self.assertIn("すべて保存済み", self.browser.status_var.get())

        with patch("nhk_radio.downloads.open_downloaded_folder", return_value=True) as open_mock:
            self.browser._open_selected_program_folder()
        open_mock.assert_called_once_with(Path(self.tmp.name))

        prog_dir = program_output_dir(Path(self.tmp.name), self.programs[0])
        prog_dir.mkdir(parents=True)
        with patch("nhk_radio.downloads.open_downloaded_folder", return_value=True) as open_mock:
            self.browser._open_selected_program_folder()
        open_mock.assert_called_once_with(prog_dir)

        if sys.platform != "win32":
            with tempfile.TemporaryDirectory() as outside_tmp:
                symlink_dir = program_output_dir(Path(self.tmp.name), self.programs[1])
                os.symlink(Path(outside_tmp), symlink_dir)
                self.browser._show_episodes(self.programs[1], self.episodes, "loaded")
                with patch("nhk_radio.downloads.open_downloaded_folder") as open_mock:
                    self.browser._open_selected_program_folder()
                open_mock.assert_not_called()
                self.assertIn("保存先の外", self.browser.status_var.get())

    # --- 使い方の説明書：目次参照 & キーワード検索 ---

    def test_help_dialog_toc_navigation_and_search(self):
        """ヘルプダイアログで目次選択ジャンプとキーワード検索（前後移動・クリア・Esc）が動作する。"""
        self.browser._show_help_dialog()
        popup = self.browser.help_popup
        self.assertIsNotNone(popup)
        self.assertTrue(popup.winfo_exists())
        self.assertIsNotNone(self.browser.help_toc_tree)
        self.assertIsNotNone(self.browser.help_text)
        self.assertIsNotNone(self.browser.help_search_entry)
        self.assertIsNotNone(self.browser.help_search_var)
        self.assertIsNotNone(self.browser.help_search_count_var)

        toc_items = self.browser.help_toc_tree.get_children()
        self.assertGreater(len(toc_items), 5)

        # 目次の後半セクションを選択すると該当行へスクロールする
        target_item = toc_items[-2]
        target_index = self.browser.help_toc_section_map[target_item]
        with (
            patch.object(self.browser.help_text, "see", wraps=self.browser.help_text.see) as see_mock,
            patch.object(self.browser.help_text, "yview", wraps=self.browser.help_text.yview) as yview_mock,
        ):
            self.browser.help_toc_tree.selection_set(target_item)
            self.browser._on_help_toc_select()
        see_mock.assert_called_with(target_index)
        yview_mock.assert_called_with(target_index)

        # 検索語を入力すると一致件数・ハイライトが更新され、次へ/前へで移動できる
        self.browser.help_search_var.set("ダウンロード")
        matches = list(self.browser.help_search_matches)
        self.assertGreater(len(matches), 1)
        self.assertEqual(self.browser.help_search_index, 0)
        self.assertEqual(self.browser.help_search_count_var.get(), f"1 / {len(matches)} 件")
        self.assertTrue(self.browser.help_text.tag_ranges("search_match"))
        self.assertEqual(
            tuple(str(idx) for idx in self.browser.help_text.tag_ranges("search_current")),
            matches[0],
        )

        self.browser._help_search_next()
        self.assertEqual(self.browser.help_search_index, 1)
        self.assertEqual(self.browser.help_search_count_var.get(), f"2 / {len(matches)} 件")

        self.browser._help_search_prev()
        self.assertEqual(self.browser.help_search_index, 0)
        self.browser._help_search_prev()
        self.assertEqual(self.browser.help_search_index, len(matches) - 1)

        # 一致しない検索語では 0 件表示になる
        self.browser.help_search_var.set("存在しないキーワードXYZ")
        self.assertEqual(self.browser.help_search_matches, [])
        self.assertEqual(self.browser.help_search_count_var.get(), "0 件")

        # ヘルプ表示中の Ctrl/Cmd + F は説明書検索欄へフォーカスする
        with (
            patch.object(self.browser.help_search_entry, "focus_set") as focus_mock,
            patch.object(self.browser.program_search_entry, "focus_set") as prog_focus_mock,
        ):
            res = self.browser._focus_program_search()
        self.assertEqual(res, "break")
        focus_mock.assert_called_once()
        prog_focus_mock.assert_not_called()

        # すでに開いている状態で再度 _show_help_dialog を呼ぶと前面化して検索欄へフォーカス
        with patch.object(self.browser.help_popup, "lift") as lift_mock:
            self.browser._show_help_dialog()
        lift_mock.assert_called_once()

        # 検索語がある状態で Esc を押すと検索語だけクリアし、ダイアログは開いたまま
        self.browser._handle_escape()
        self.assertEqual(self.browser.help_search_var.get(), "")
        self.assertEqual(self.browser.help_search_count_var.get(), "")
        self.assertIsNotNone(self.browser.help_popup)
        self.assertTrue(self.browser.help_popup.winfo_exists())

        # 検索語が空の状態で Esc を押すとダイアログを閉じる
        self.browser._handle_escape()
        self.assertIsNone(self.browser.help_popup)
        self.assertIsNone(self.browser.help_toc_tree)
        self.assertEqual(self.browser.help_sections, [])


if __name__ == "__main__":
    unittest.main()

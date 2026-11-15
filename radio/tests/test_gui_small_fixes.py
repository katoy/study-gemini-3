"""レビュー G11・G12・G17（小さな UI 不具合と使われていない値）の回帰テスト。"""

import tempfile
import tkinter as tk
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.gui.download_manager import DownloadManager
from nhk_radio.gui.episode_view import context_menu_buttons
from nhk_radio.types import Episode, Program


def _episode(episode_id: str) -> Episode:
    """テスト用の Episode を作る。"""
    return Episode(
        id=episode_id, title=episode_id, display_title=episode_id, date="20240415",
        display_date="2024-04-15", broadcast_time="", duration_str="", url="",
    )


# ── G12: 右クリックに使うボタン ─────────────────────────


def test_context_menu_buttons_on_aqua() -> None:
    """macOS (aqua) では Button-2 と Button-3 の両方で右クリックメニューを開く。"""
    assert context_menu_buttons("aqua") == ("<Button-2>", "<Button-3>")


def test_context_menu_buttons_on_x11_and_windows() -> None:
    """Linux (x11) と Windows (win32) では、中ボタンの Button-2 にメニューを割り当てない。"""
    assert context_menu_buttons("x11") == ("<Button-3>",)
    assert context_menu_buttons("win32") == ("<Button-3>",)


# ── G17: 使われていない値 ───────────────────────────


def test_download_manager_has_no_unused_counters() -> None:
    """読まれていない started_count / finished_count を持たない。"""
    manager = DownloadManager(output_dir=Path("/tmp"), audio_only=True, on_result=MagicMock())

    assert not hasattr(manager, "started_count")
    assert not hasattr(manager, "finished_count")


# ── ブラウザを使うテスト ────────────────────────────


class GuiSmallFixesTest(unittest.TestCase):
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
                    site_id="S1", corner_id="01", url="U1"),
        ]
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            self.browser = EpisodeGuiBrowser(self.programs, Path(self.tmp.name))
        self.browser.download_manager = MagicMock()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()
        with suppress(Exception):
            self.root.destroy()

    # --- G11: 進捗表示 ---

    def test_activity_add_updates_summary(self):
        """ジョブ行を追加したら、概要の「実行中: N」を更新する。"""
        self.browser.activity_view.add(_episode("e1"))
        self.assertEqual(self.browser.progress_text_var.get(), "実行中: 1 / 全体: 1")

        self.browser.activity_view.add(_episode("e2"))
        self.assertEqual(self.browser.progress_text_var.get(), "実行中: 2 / 全体: 2")

    def test_fetch_episodes_does_not_overwrite_download_summary(self):
        """エピソード一覧の取得を始めても、ダウンロードの概要表示を " 0/1" で上書きしない。"""
        self.browser.activity_view.add(_episode("e1"))
        self.browser.data_manager = MagicMock()
        self.browser._select_program_item("program-0")

        self.browser._start_fetch_selected()

        self.assertEqual(self.browser.progress_text_var.get(), "実行中: 1 / 全体: 1")

    # --- G12: 右クリックメニュー ---

    def _open_context_menu(self) -> None:
        with patch.object(tk.Menu, "tk_popup"), patch.object(self.browser, "_is_saved_item", return_value=True):
            self.browser._show_episode_context_menu(MagicMock(x_root=0, y_root=0), "episode-0")

    def test_context_menu_is_reused(self):
        """右クリックのたびに Menu を作らず、1 つを使い回す。"""
        self._open_context_menu()
        first = self.browser.episode_context_menu
        menus_before = [w for w in self.root.winfo_children() if isinstance(w, tk.Menu)]
        self._open_context_menu()
        self._open_context_menu()
        menus_after = [w for w in self.root.winfo_children() if isinstance(w, tk.Menu)]

        self.assertIs(self.browser.episode_context_menu, first)
        self.assertEqual(len(menus_after), len(menus_before))

    def test_context_menu_entries_are_rebuilt(self):
        """使い回すメニューの項目は毎回作り直し、項目が増え続けない。"""
        self._open_context_menu()
        menu = self.browser.episode_context_menu
        assert menu is not None
        count = menu.index("end")
        self._open_context_menu()

        self.assertEqual(menu.index("end"), count)

    # --- G12: tooltip ---

    def test_show_tooltip_with_same_text_reuses_window(self):
        """同じ文言の tooltip を表示し直すときは、ウィンドウを作り直さず位置だけ動かす。"""
        event = MagicMock(x_root=10, y_root=20)
        self.browser._show_tooltip(event, "ヒント")
        first = self.browser.tooltip_window

        self.browser._show_tooltip(MagicMock(x_root=30, y_root=40), "ヒント")

        self.assertIs(self.browser.tooltip_window, first)
        self.browser._hide_tooltip()

    def test_show_tooltip_with_new_text_updates_label(self):
        """文言が変わったときは、新しい文言を表示する。"""
        event = MagicMock(x_root=10, y_root=20)
        self.browser._show_tooltip(event, "ヒント 1")
        self.browser._show_tooltip(event, "ヒント 2")

        label = self.browser.tooltip_label
        assert label is not None
        self.assertEqual(label.cget("text"), "ヒント 2")
        self.browser._hide_tooltip()

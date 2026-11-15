"""レビュー G13（UI スレッドでのファイル I/O）の回帰テスト。

表示中の番組の保存状態はバックグラウンドで判定してメモリに持ち、
描画・絞り込み・並べ替え・概要・ボタンの更新では UI スレッドからファイル I/O をしない。
"""

import tempfile
import time
import tkinter as tk
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.types import Episode, Program

PROGRAM_A = Program(title="番組A", display_title="番組A", display_date="", site_id="S1", corner_id="01", url="U1")
PROGRAM_B = Program(title="番組B", display_title="番組B", display_date="", site_id="S2", corner_id="01", url="U2")


def _episode(episode_id: str) -> Episode:
    """テスト用の Episode を作る。"""
    return Episode(id=episode_id, title=episode_id, display_title=episode_id, date="20240415",
                   display_date="2024-04-15(月)", broadcast_time="", duration_str="", url="")


EPISODES = [_episode("e1"), _episode("e2")]


def _no_io(*_args, **_kwargs):
    raise AssertionError("UI スレッドで保存状態をファイルから判定した")


class AsyncSavedStateTest(unittest.TestCase):
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
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            self.browser = EpisodeGuiBrowser([PROGRAM_A, PROGRAM_B], Path(self.tmp.name))
        self.browser.download_manager = MagicMock()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()
        with suppress(Exception):
            self.root.destroy()

    def _wait_saved_keys(self, timeout: float = 5.0) -> None:
        """保存状態の判定結果がキューに届くまで待ち、UI に反映する。"""
        deadline = time.monotonic() + timeout
        while self.browser.saved_keys_queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.browser._poll_saved_keys()

    def _show_with_saved(self, program: Program, saved: set[str]) -> None:
        """番組の一覧を表示し、バックグラウンドの判定結果 (saved) を反映するまで進める。"""
        with patch("nhk_radio.gui.listing.episodes.get_downloaded_episode_keys", return_value=saved):
            self.browser._show_episodes(program, EPISODES, "loaded")
            self._wait_saved_keys()

    def test_ui_operations_do_not_touch_filesystem(self):
        """判定結果が届いた後の描画・絞り込み・並べ替え・概要・ボタン更新は、ファイルから判定しない。"""
        self._show_with_saved(PROGRAM_A, {"e1"})

        with (
            patch("nhk_radio.gui.listing.episodes.get_downloaded_episode_keys", side_effect=_no_io),
            patch("nhk_radio.downloads.get_downloaded_episode_keys", side_effect=_no_io),
        ):
            self.browser.episode_saved_only_var.set(True)
            self.browser._apply_episode_filter()
            self.browser.episode_sort_state = ("saved", False)
            self.browser._rerender_displayed_episodes()
            self.browser._refresh_saved_only_button_state()
            self.browser._update_program_overview(PROGRAM_A, EPISODES, "キャッシュ表示")

        self.assertIn("保存済み 1", self.browser.selected_program_stats_var.get())

    def test_saved_only_filter_uses_cached_state(self):
        """「保存済みのみ」は、メモリ上の保存状態で絞り込む。"""
        self._show_with_saved(PROGRAM_A, {"e1"})
        self.browser.episode_saved_only_var.set(True)
        self.browser._apply_episode_filter()

        self.assertEqual(list(self.browser.displayed_episode_map.values()), [EPISODES[0]])

    def test_overview_shows_pending_until_result_arrives(self):
        """判定が終わるまで概要の保存済み件数は「確認中」とし、結果が届いたら件数を出す。"""
        self.browser._update_program_overview(PROGRAM_A, EPISODES, "キャッシュ表示")
        self.assertIn("保存済み 確認中", self.browser.selected_program_stats_var.get())

        self._show_with_saved(PROGRAM_A, {"e1", "e2"})
        self.assertIn("保存済み 2", self.browser.selected_program_stats_var.get())

    def test_switching_program_resets_saved_state(self):
        """別の番組に切り替えたら、前の番組の保存状態を使わない。"""
        self._show_with_saved(PROGRAM_A, {"e1"})
        with patch("nhk_radio.gui.listing.episodes.get_downloaded_episode_keys", return_value=set()):
            self.browser._show_episodes(PROGRAM_B, EPISODES, "loaded")
            self.assertEqual(self.browser.displayed_saved_keys, set())
            self.assertIsNone(self.browser.saved_keys_program_key)
            self._wait_saved_keys()

    def test_result_for_previous_program_is_ignored(self):
        """切り替える前の番組の判定結果が後から届いても反映しない。"""
        self.browser._show_episodes(PROGRAM_B, EPISODES, "loaded")
        self.browser.saved_keys_queue.put((PROGRAM_A, self.browser.saved_keys_generation, {"e1"}))
        self.browser._poll_saved_keys()

        self.assertEqual(self.browser.displayed_saved_keys, set())

    def test_refresh_downloaded_column_runs_in_background(self):
        """ダウンロード完了や削除の後の更新は、バックグラウンドで判定し直す。"""
        self._show_with_saved(PROGRAM_A, set())
        with patch("nhk_radio.gui.listing.episodes.get_downloaded_episode_keys", return_value={"e2"}):
            self.browser._refresh_downloaded_column(PROGRAM_A)
            self._wait_saved_keys()

        self.assertEqual(self.browser.displayed_saved_keys, {"e2"})
        self.assertTrue(any(self.browser._is_saved_item(iid) for iid in self.browser.displayed_episode_map))

    def test_refresh_without_displayed_program_does_nothing(self):
        """一覧を表示していなければ、判定を始めない。"""
        self.browser.displayed_program = None
        generation = self.browser.saved_keys_generation
        self.browser._refresh_downloaded_column(PROGRAM_A)
        self.browser._start_saved_keys_refresh()

        self.assertEqual(self.browser.saved_keys_generation, generation)

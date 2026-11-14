"""レビュー G16（状態の持ち主があいまい）の回帰テスト。"""

import tempfile
import tkinter as tk
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui import data_manager as data_manager_module
from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.gui.data_manager import EPISODE_CACHE_MAX_PROGRAMS, DataManager
from nhk_radio.types import Episode, Program


def _program(index: int) -> Program:
    """index 番目のテスト用 Program を作る。"""
    return Program(
        title=f"番組{index}", display_title=f"番組{index}", display_date="2024-04-15",
        site_id=f"S{index}", corner_id="01", url=f"U{index}",
    )


def _episode(episode_id: str) -> Episode:
    """テスト用の Episode を作る。"""
    return Episode(
        id=episode_id, title=episode_id, display_title=episode_id, date="20240415",
        display_date="2024-04-15", broadcast_time="", duration_str="", url="",
    )


class _ImmediateThread:
    """start() で target をその場で実行する Thread の代用品。"""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


# ── DataManager ─────────────────────────────────────


def test_data_manager_does_not_own_program_list() -> None:
    """番組リストはブラウザだけが持ち、DataManager は持たない。"""
    dm = DataManager(on_program_result=MagicMock(), on_episode_result=MagicMock())

    assert not hasattr(dm, "programs")
    assert not hasattr(dm, "filtered_programs")


def test_store_episodes_evicts_oldest_over_limit() -> None:
    """上限を超えたら、最も古く使われた番組のキャッシュを捨てる。"""
    dm = DataManager(on_program_result=MagicMock(), on_episode_result=MagicMock())
    for index in range(EPISODE_CACHE_MAX_PROGRAMS + 1):
        dm.store_episodes(_program(index), [_episode(f"e{index}")])

    assert len(dm.episodes_cache) == EPISODE_CACHE_MAX_PROGRAMS
    assert ("S0", "01") not in dm.episodes_cache
    assert (f"S{EPISODE_CACHE_MAX_PROGRAMS}", "01") in dm.episodes_cache


def test_store_episodes_moves_updated_entry_to_end() -> None:
    """既存の番組を保存し直すと、最も新しい扱いになり捨てられない。"""
    dm = DataManager(on_program_result=MagicMock(), on_episode_result=MagicMock())
    for index in range(EPISODE_CACHE_MAX_PROGRAMS):
        dm.store_episodes(_program(index), [])
    dm.store_episodes(_program(0), [_episode("new")])
    dm.store_episodes(_program(EPISODE_CACHE_MAX_PROGRAMS), [])

    assert ("S0", "01") in dm.episodes_cache
    assert ("S1", "01") not in dm.episodes_cache
    assert dm.episodes_cache[("S0", "01")][1] == [_episode("new")]


def test_start_fetch_episodes_worker_does_not_write_cache() -> None:
    """ワーカースレッドはキャッシュに書かず、結果をコールバックに渡すだけにする。"""
    on_episode_result = MagicMock()
    dm = DataManager(on_program_result=MagicMock(), on_episode_result=on_episode_result)
    episodes = [_episode("e1")]
    with (
        patch.object(data_manager_module, "refresh_episode_list", return_value=(episodes, "network")),
        patch.object(data_manager_module.threading, "Thread", _ImmediateThread),
    ):
        dm.start_fetch_episodes(_program(1))

    assert len(dm.episodes_cache) == 0
    on_episode_result.assert_called_once_with(_program(1), episodes, "network", None)


# ── ブラウザ ──────────────────────────────────────


class BrowserStateOwnershipTest(unittest.TestCase):
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
        self.programs = [_program(1), _program(2)]
        with patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root):
            self.browser = EpisodeGuiBrowser(self.programs, Path(self.tmp.name))
        self.browser.download_manager = MagicMock()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()
        with suppress(Exception):
            self.root.destroy()

    def test_filtered_programs_is_separate_list(self):
        """filtered_programs は programs と別のリストにし、片方の変更がもう片方に及ばない。"""
        self.assertIsNot(self.browser.filtered_programs, self.browser.programs)
        self.assertEqual(self.browser.filtered_programs, self.programs)

    def test_finish_fetch_programs_replaces_program_list(self):
        """番組一覧の取得結果で、ブラウザの番組リストを差し替える。"""
        new_programs = [_program(3)]
        self.browser._finish_fetch_programs(new_programs, None)

        self.assertEqual(self.browser.programs, new_programs)
        self.assertEqual(self.browser.filtered_programs, new_programs)

    def test_episodes_cache_is_owned_by_data_manager(self):
        """ブラウザの episodes_cache は DataManager のキャッシュそのもの。"""
        self.assertIs(self.browser.episodes_cache, self.browser.data_manager.episodes_cache)

    def test_finish_fetch_keeps_cache_within_limit(self):
        """取得結果をキャッシュに入れても、上限を超えない。"""
        for index in range(EPISODE_CACHE_MAX_PROGRAMS):
            self.browser.data_manager.store_episodes(_program(100 + index), [])

        self.browser._finish_fetch(self.programs[0], [_episode("e1")], "network", None)

        self.assertEqual(len(self.browser.episodes_cache), EPISODE_CACHE_MAX_PROGRAMS)
        self.assertIn(("S1", "01"), self.browser.episodes_cache)
        self.assertNotIn(("S100", "01"), self.browser.episodes_cache)

    def test_clear_cache_worker_does_not_touch_memory_state(self):
        """キャッシュ全削除のワーカーは、メモリ上の状態を書き換えない。"""
        self.browser.data_manager.store_episodes(self.programs[0], [_episode("e1")])
        with (
            patch("nhk_radio.gui.download_panel.clear_all_cache"),
            patch("nhk_radio.gui.download_panel.threading.Thread", _ImmediateThread),
            patch("tkinter.messagebox.askyesno", return_value=True),
            patch.object(self.browser.root, "after") as after_mock,
        ):
            self.browser._clear_cache()

        # UI スレッドへの引き渡し (root.after) の前は、キャッシュも番組リストもそのまま
        self.assertIn(("S1", "01"), self.browser.episodes_cache)
        self.assertEqual(self.browser.programs, self.programs)
        after_mock.assert_called_once()

    def test_cache_cleared_success_keeps_programs_and_clears_episodes(self):
        """キャッシュ全削除の完了後、エピソードキャッシュは空にし、番組一覧は表示したまま取り直す。"""
        self.browser.data_manager.store_episodes(self.programs[0], [_episode("e1")])
        self.browser._start_fetch_programs = MagicMock()

        self.browser._on_cache_cleared_success()

        self.assertEqual(len(self.browser.episodes_cache), 0)
        self.assertEqual(self.browser.programs, self.programs)
        self.browser._start_fetch_programs.assert_called_once()

import curses
import unittest
from unittest.mock import PropertyMock, patch

from tests import _support  # noqa: F401

from nhk_radio import tui


PROGRAMS = [
    {"site_id": "SITE", "corner_id": "01", "title": "番組A", "display_title": "番組A", "display_date": "2024-04-15(月)"},
    {"site_id": "SITE", "corner_id": "02", "title": "番組B", "display_title": "番組B", "display_date": "2024-04-16(火)"},
]

EPISODES = [
    {"id": "ep1", "title": "第1回", "display_title": "第1回", "display_date": "2024-04-15(月)", "broadcast_time": "07:00", "duration_str": "5分0秒"},
    {"id": "ep2", "title": "第2回", "display_title": "第2回", "display_date": "2024-04-16(火)", "broadcast_time": "", "duration_str": ""},
]


class _FakeStdScr:
    def __init__(self, keys=None, size=(24, 100)):
        self.keys = list(keys or [])
        self.size = size
        self.keypad_calls = []
        self.calls = []
        self.refreshed = 0
        self.erased = 0

    def keypad(self, flag):
        self.keypad_calls.append(flag)

    def getch(self):
        return self.keys.pop(0)

    def erase(self):
        self.erased += 1

    def getmaxyx(self):
        return self.size

    def refresh(self):
        self.refreshed += 1

    def addnstr(self, y, x, value, available, attr=0):
        self.calls.append((y, x, value, available, attr))


class EpisodeBrowserTest(unittest.TestCase):
    def test_run_quits_and_handles_curs_set_error(self):
        stdscr = _FakeStdScr(keys=[ord("q")])
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        with patch.object(tui.curses, "curs_set", side_effect=curses.error("no cursor")):
            result = browser.run()
        self.assertEqual(result, (None, None))
        self.assertEqual(stdscr.keypad_calls, [True])

    def test_run_switches_focus_and_returns_episode_result(self):
        stdscr = _FakeStdScr(keys=[9, ord("x")])
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.active_program_key = browser.current_key
        expected = (PROGRAMS[0], EPISODES)
        with (
            patch.object(tui.curses, "curs_set"),
            patch.object(browser, "_draw"),
            patch.object(browser, "_handle_episode_key", return_value=expected) as handler,
        ):
            result = browser.run()
        self.assertEqual(result, expected)
        handler.assert_called_once_with(ord("x"))

    def test_run_tabs_back_to_programs_and_dispatches_program_handler(self):
        stdscr = _FakeStdScr(keys=[9, ord("x"), ord("q")])
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.focus = "episodes"
        with (
            patch.object(tui.curses, "curs_set"),
            patch.object(browser, "_draw"),
            patch.object(browser, "_handle_program_key") as handler,
        ):
            result = browser.run()
        self.assertEqual(result, (None, None))
        handler.assert_called_once_with(ord("x"))

    def test_handle_program_key_branches(self):
        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        browser.active_program_key = browser.current_key
        with (
            patch.object(browser, "_move_program") as move_mock,
            patch.object(browser, "_activate_current_program") as activate_mock,
            patch.object(browser, "_clear_cache_and_reload") as clear_mock,
        ):
            browser._handle_program_key(curses.KEY_UP)
            move_mock.assert_called_with(-1)
            browser._handle_program_key(curses.KEY_DOWN)
            browser._handle_program_key(curses.KEY_PPAGE)
            browser._handle_program_key(curses.KEY_NPAGE)
            self.assertEqual(move_mock.call_count, 4)
            browser._handle_program_key(curses.KEY_HOME)
            self.assertEqual(browser.program_index, 0)
            browser._handle_program_key(curses.KEY_END)
            self.assertEqual(browser.program_index, len(PROGRAMS) - 1)
            browser._handle_program_key(10)
            activate_mock.assert_called_once()
            browser.focus = "programs"
            browser._handle_program_key(curses.KEY_RIGHT)
            self.assertEqual(browser.focus, "episodes")
            browser._handle_program_key(ord("C"))
            clear_mock.assert_called_once()

    def test_handle_episode_key_branches(self):
        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        browser.active_program_key = browser.current_key
        browser.focus = "episodes"
        browser.episodes_cache[browser.current_key] = (0, EPISODES)
        with (
            patch.object(browser, "_move_episode") as move_mock,
            patch.object(browser, "_toggle_all_episodes") as toggle_all_mock,
            patch.object(browser, "_toggle_current_episode") as toggle_one_mock,
            patch.object(browser, "_clear_cache_and_reload") as clear_mock,
        ):
            browser._handle_episode_key(curses.KEY_LEFT)
            self.assertEqual(browser.focus, "programs")
            browser.focus = "episodes"
            browser._handle_episode_key(curses.KEY_UP)
            move_mock.assert_called_with(-1)
            browser._handle_episode_key(curses.KEY_DOWN)
            browser._handle_episode_key(curses.KEY_PPAGE)
            browser._handle_episode_key(curses.KEY_NPAGE)
            self.assertEqual(move_mock.call_count, 4)
            browser._handle_episode_key(ord("a"))
            toggle_all_mock.assert_called_once()
            browser._handle_episode_key(ord(" "))
            toggle_one_mock.assert_called_once()
            with patch.object(browser, "_selected_episodes", return_value=[]):
                self.assertIsNone(browser._handle_episode_key(ord("d")))
                self.assertIn("選んでください", browser.status)
            with patch.object(browser, "_selected_episodes", return_value=EPISODES):
                self.assertEqual(browser._handle_episode_key(10), (PROGRAMS[0], EPISODES))
            browser._handle_episode_key(ord("C"))
            clear_mock.assert_called_once()

    def test_browser_properties_and_cache_accessors(self):
        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        self.assertEqual(browser.current_program, PROGRAMS[0])
        self.assertEqual(browser.current_key, ("SITE", "01"))
        self.assertEqual(browser.preview_program, PROGRAMS[0])
        self.assertEqual(browser.preview_key, ("SITE", "01"))
        self.assertEqual(browser.current_episodes, [])
        self.assertIsNone(browser.active_program)

        browser.active_program_key = ("SITE", "02")
        browser.focus = "episodes"
        self.assertEqual(browser.preview_program, PROGRAMS[1])
        self.assertEqual(browser.active_program, PROGRAMS[1])

        with patch.object(tui, "load_episode_cache", return_value=EPISODES), patch.object(tui.time, "time", return_value=100):
            self.assertEqual(browser.preview_episodes, EPISODES)
            self.assertIn(browser.preview_key, browser.episodes_cache)

        browser.episodes_cache[browser.preview_key] = (0, EPISODES)
        with patch.object(tui.time, "time", side_effect=[tui.CACHE_TTL_SECONDS + 1, 50]), patch.object(tui, "load_episode_cache", return_value=None):
            self.assertEqual(browser.preview_episodes, [])

        browser.episodes_cache[browser.preview_key] = (0, EPISODES)
        with patch.object(tui.time, "time", side_effect=[tui.CACHE_TTL_SECONDS + 1, 50]), patch.object(tui, "load_episode_cache", return_value=EPISODES):
            self.assertEqual(browser.preview_episodes, EPISODES)

        browser.active_program_key = browser.current_key
        self.assertEqual(browser.current_episodes, [])
        browser.episodes_cache[browser.current_key] = (0, EPISODES)
        with patch.object(tui.time, "time", return_value=tui.CACHE_TTL_SECONDS + 1):
            self.assertEqual(browser.current_episodes, [])

        browser.active_program_key = ("missing", "99")
        self.assertIsNone(browser.active_program)

    def test_load_current_program_paths(self):
        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        key = browser.current_key
        browser.active_program_key = key
        browser.episodes_cache[key] = (100, EPISODES)
        with patch.object(tui.time, "time", return_value=100), patch.object(tui, "get_episode_list") as get_mock:
            browser._load_current_program()
        get_mock.assert_not_called()

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        with (
            patch.object(tui.curses, "curs_set"),
            patch.object(browser, "_draw"),
            patch.object(tui, "get_episode_list", return_value=(EPISODES, "cache")),
            patch.object(tui.time, "time", return_value=200),
        ):
            browser._load_current_program()
        self.assertIn("キャッシュ", browser.status)
        self.assertEqual(browser.active_program_key, browser.current_key)

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        with (
            patch.object(tui.curses, "curs_set"),
            patch.object(browser, "_draw"),
            patch.object(tui, "get_episode_list", return_value=(EPISODES, "stale-cache")),
            patch.object(tui.time, "time", return_value=200),
        ):
            browser._load_current_program()
        self.assertIn("期限切れキャッシュ", browser.status)

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        with (
            patch.object(tui.curses, "curs_set"),
            patch.object(browser, "_draw"),
            patch.object(tui, "get_episode_list", return_value=(EPISODES, "network")),
            patch.object(tui.time, "time", return_value=200),
        ):
            browser._load_current_program()
        self.assertIn("最新取得", browser.status)

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        with (
            patch.object(tui.curses, "curs_set", side_effect=curses.error("x")),
            patch.object(browser, "_draw"),
            patch.object(tui, "get_episode_list", side_effect=RuntimeError("boom")),
            patch.object(tui.time, "time", return_value=200),
        ):
            browser._load_current_program()
        self.assertIn("取得失敗", browser.status)

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        with (
            patch.object(tui.curses, "curs_set"),
            patch.object(browser, "_draw"),
            patch.object(tui, "get_episode_list", return_value=([], "network")),
            patch.object(tui.time, "time", return_value=200),
        ):
            browser._load_current_program()
        self.assertEqual(browser.status, "エピソードが見つかりませんでした")

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        with patch.object(browser, "_load_current_program") as load_mock:
            browser._activate_current_program()
        self.assertEqual(browser.focus, "episodes")
        load_mock.assert_called_once()

    def test_episode_selection_helpers(self):
        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        browser.active_program_key = browser.current_key
        browser.episodes_cache[browser.current_key] = (100, EPISODES)
        with patch.object(tui.time, "time", return_value=100):
            browser._move_episode(1)
            self.assertEqual(browser.episode_index[browser.current_key], 1)
            browser._toggle_current_episode()
            self.assertEqual(browser.selected_episode_ids[browser.current_key], {"ep2"})
            browser._toggle_current_episode()
            self.assertEqual(browser.selected_episode_ids[browser.current_key], set())
            browser._toggle_all_episodes()
            self.assertEqual(browser.selected_episode_ids[browser.current_key], {"ep1", "ep2"})
            browser._toggle_all_episodes()
            self.assertEqual(browser.selected_episode_ids[browser.current_key], set())
            self.assertEqual(browser._selected_episodes(), [EPISODES[1]])
            browser.selected_episode_ids[browser.current_key] = {"ep1"}
            self.assertEqual(browser._selected_episodes(), [EPISODES[0]])

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        browser._move_episode(1)
        browser._toggle_current_episode()
        browser._toggle_all_episodes()
        self.assertEqual(browser._selected_episodes(), [])

        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        with patch.object(tui.EpisodeBrowser, "current_episodes", new_callable=PropertyMock, return_value=EPISODES):
            browser._move_episode(1)
            browser._toggle_current_episode()
            browser._toggle_all_episodes()
            self.assertEqual(browser._selected_episodes(), [])

    def test_move_program_and_clear_cache(self):
        browser = tui.EpisodeBrowser(_FakeStdScr(), PROGRAMS)
        browser._move_program(-1)
        self.assertEqual(browser.program_index, 0)

        browser.episodes_cache[("SITE", "02")] = (100, EPISODES)
        with patch.object(tui.time, "time", return_value=100):
            browser._move_program(1)
        self.assertEqual(browser.program_index, 1)
        self.assertIn("キャッシュを表示中", browser.status)

        browser.episodes_cache.clear()
        browser._move_program(-1)
        self.assertIn("未取得", browser.status)

        browser.active_program_key = browser.current_key
        browser.episodes_cache[browser.current_key] = (100, EPISODES)
        browser.episode_index[browser.current_key] = 1
        browser.episode_top[browser.current_key] = 1
        browser.selected_episode_ids[browser.current_key] = {"ep1"}
        with patch.object(tui, "clear_episode_cache", return_value=3), patch.object(browser, "_activate_current_program") as activate_mock:
            browser._clear_cache_and_reload()
        self.assertIn("3 件", browser.status)
        self.assertIsNone(browser.active_program_key)
        self.assertEqual(browser.episodes_cache, {})
        activate_mock.assert_called_once()

    def test_draw_and_subviews(self):
        stdscr = _FakeStdScr(size=(10, 60))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser._draw()
        self.assertGreater(stdscr.refreshed, 0)

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        with patch.object(browser, "_draw_programs") as draw_programs_mock, patch.object(browser, "_draw_episodes") as draw_episodes_mock:
            browser._draw()
        draw_programs_mock.assert_called_once()
        draw_episodes_mock.assert_called_once()

        stdscr = _FakeStdScr(size=(12, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser._draw()
        self.assertGreater(stdscr.refreshed, 0)

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser._draw_programs(0, 0, 6, 100)
        self.assertTrue(any("番組A" in call[2] for call in stdscr.calls))

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.program_top = 1
        browser.program_index = 0
        browser._draw_programs(0, 0, 4, 100)
        self.assertEqual(browser.program_top, 0)

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.program_top = 0
        browser.program_index = 1
        browser._draw_programs(0, 0, 4, 100)
        self.assertEqual(browser.program_top, 1)

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.focus = "programs"
        browser._draw_episodes(0, 0, 6, 100)
        self.assertTrue(any("未取得" in call[2] for call in stdscr.calls))

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.focus = "episodes"
        browser._draw_episodes(0, 0, 6, 100)
        self.assertTrue(any("未取得" in call[2] for call in stdscr.calls))

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.focus = "episodes"
        browser.active_program_key = browser.current_key
        browser.episodes_cache[browser.current_key] = (100, [])
        with patch.object(tui.time, "time", return_value=100):
            browser._draw_episodes(0, 0, 6, 100)
        self.assertTrue(any("利用可能なエピソード" in call[2] for call in stdscr.calls))

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.focus = "episodes"
        browser.active_program_key = browser.current_key
        browser.episodes_cache[browser.current_key] = (100, EPISODES)
        browser.selected_episode_ids[browser.current_key] = {"ep1"}
        with patch.object(tui.time, "time", return_value=100):
            browser._draw_episodes(0, 0, 6, 100)
        self.assertTrue(any("[x]" in call[2] for call in stdscr.calls))

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.focus = "episodes"
        browser.active_program_key = browser.current_key
        browser.episodes_cache[browser.current_key] = (100, EPISODES)
        browser.episode_top[browser.current_key] = 1
        browser.episode_index[browser.current_key] = 0
        with patch.object(tui.time, "time", return_value=100):
            browser._draw_episodes(0, 0, 3, 100)
        self.assertEqual(browser.episode_top[browser.current_key], 0)

        stdscr = _FakeStdScr(size=(20, 100))
        browser = tui.EpisodeBrowser(stdscr, PROGRAMS)
        browser.focus = "episodes"
        browser.active_program_key = browser.current_key
        browser.episodes_cache[browser.current_key] = (100, EPISODES)
        browser.episode_top[browser.current_key] = 0
        browser.episode_index[browser.current_key] = 1
        with patch.object(tui.time, "time", return_value=100):
            browser._draw_episodes(0, 0, 3, 100)
        self.assertEqual(browser.episode_top[browser.current_key], 1)

    def test_browse_programs_tui_success_and_error(self):
        with patch.object(tui.curses, "wrapper", return_value=(PROGRAMS[0], EPISODES)):
            self.assertEqual(tui.browse_programs_tui(PROGRAMS), (PROGRAMS[0], EPISODES))

        with patch.object(tui.curses, "wrapper", side_effect=curses.error("bad")):
            with self.assertRaisesRegex(RuntimeError, "bad"):
                tui.browse_programs_tui(PROGRAMS)


if __name__ == "__main__":
    unittest.main()

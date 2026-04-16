import curses
import unittest
from datetime import datetime
from unittest.mock import patch

from tests import _support  # noqa: F401

from nhk_radio import text


class _FakeWindow:
    def __init__(self, height=5, width=10, fail=False):
        self.height = height
        self.width = width
        self.fail = fail
        self.calls = []

    def getmaxyx(self):
        return self.height, self.width

    def addnstr(self, y, x, value, available, attr=0):
        if self.fail:
            raise curses.error("boom")
        self.calls.append((y, x, value, available, attr))


class TextHelpersTest(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(text._normalize_text("　 hello  "), "hello")

    def test_format_onair_date_normalizes_weekday(self):
        self.assertEqual(text._format_onair_date("2024年04月15日(月)放送"), "2024-04-15(月)")

    def test_format_onair_date_handles_empty_and_invalid_dates(self):
        self.assertEqual(text._format_onair_date(""), "----------(-)")
        self.assertEqual(text._format_onair_date("2024年4月5日特集"), "2024-04-05(金)")
        self.assertEqual(text._format_onair_date("2024年13月40日"), "2024年13月40日")
        self.assertEqual(text._format_onair_date("2024年02月30日"), "2024年02月30日")

    def test_format_episode_date_uses_yyyymmdd_prefix_or_fallback(self):
        self.assertEqual(text._format_episode_date("20240415extra"), "2024-04-15(月)")
        self.assertEqual(text._format_episode_date("2024/04/16"), "2024-04-16(火)")
        self.assertEqual(text._format_episode_date("20240230"), "20240230")

    def test_format_broadcast_time(self):
        self.assertEqual(text._format_broadcast_time(None), "")
        self.assertEqual(text._format_broadcast_time("bad"), "")
        self.assertEqual(text._format_broadcast_time(1713188400), datetime.fromtimestamp(1713188400).strftime("%H:%M"))

    def test_format_duration_handles_variants(self):
        self.assertEqual(text._format_duration(None), "")
        self.assertEqual(text._format_duration(0), "")
        self.assertEqual(text._format_duration(7), "7秒")
        self.assertEqual(text._format_duration(125), "2分5秒")
        self.assertEqual(text._format_duration(3661), "1時間1分1秒")
        self.assertEqual(text._format_duration("bad"), "")

    def test_sortable_day_value(self):
        self.assertEqual(text._sortable_day_value(""), (0, 0))
        self.assertEqual(text._sortable_day_value("20240415"), (1, 738991))
        self.assertEqual(text._sortable_day_value("20241340"), (0, 0))
        self.assertEqual(text._sortable_day_value("2024/04/16"), (1, 738992))
        self.assertEqual(text._sortable_day_value("2024年13月40日"), (0, 0))
        self.assertEqual(text._sortable_day_value("2024年02月30日"), (0, 0))

    def test_sortable_timestamp_value(self):
        valid_iso = text._sortable_timestamp_value("2024-04-15T07:00:00Z")
        self.assertEqual(valid_iso[0], 1)
        self.assertEqual(text._sortable_timestamp_value(None), (0, 0.0))
        self.assertEqual(text._sortable_timestamp_value(""), (0, 0.0))
        self.assertEqual(text._sortable_timestamp_value("1713164400"), (1, 1713164400.0))
        with patch("builtins.float", side_effect=ValueError("bad")):
            self.assertEqual(text._sortable_timestamp_value("1713164400"), (0, 0.0))
        self.assertEqual(text._sortable_timestamp_value("not-a-time"), (0, 0.0))

    def test_sortable_duration_value(self):
        self.assertEqual(text._sortable_duration_value("2分5秒"), (1, 125))
        self.assertEqual(text._sortable_duration_value(""), (0, 0))
        self.assertEqual(text._sortable_duration_value("0秒"), (0, 0))
        self.assertEqual(text._sortable_duration_value("abc"), (0, 0))

    def test_program_display_title_and_safe_name(self):
        self.assertEqual(text._program_display_title("番組", "コーナー"), "[番組] コーナー")
        self.assertEqual(text._program_display_title("", ""), "(無題)")
        self.assertEqual(text._safe_name('a/b:c*?"<>|'), "a_b_c______")

    def test_genre_label_and_width_helpers(self):
        self.assertEqual(text._genre_label("language"), "語学")
        self.assertEqual(text._genre_label("unknown"), "未分類")
        self.assertEqual(text._char_width("あ"), 2)
        self.assertEqual(text._display_width("abあ"), 4)

    def test_fit_text_adds_ellipsis_and_padding(self):
        self.assertEqual(text._fit_text("abcdefghijklmnopqrstuvwxyz", 8), "abcde...")
        self.assertEqual(text._fit_text("abc", 0), "")
        self.assertEqual(text._fit_text("abcdef", 2), "ab")
        self.assertEqual(text._fit_text("abc", 5), "abc  ")

    def test_safe_addnstr_bounds_bottom_row_and_curses_error(self):
        win = _FakeWindow(height=3, width=6)
        text._safe_addnstr(win, 2, 0, "abcdef", 6, 123)
        self.assertEqual(win.calls[0], (2, 0, "abcdef", 5, 123))

        text._safe_addnstr(win, -1, 0, "x", 1)
        self.assertEqual(len(win.calls), 1)

        text._safe_addnstr(win, 0, 10, "x", 1)
        text._safe_addnstr(win, 0, 9, "x", 0)
        self.assertEqual(len(win.calls), 1)

        zero = _FakeWindow(height=3, width=3)
        text._safe_addnstr(zero, 2, 2, "x", 1)
        self.assertEqual(zero.calls, [])

        failing = _FakeWindow(fail=True)
        text._safe_addnstr(failing, 0, 0, "x", 1)


if __name__ == "__main__":
    unittest.main()

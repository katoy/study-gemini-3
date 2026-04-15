import unittest

from tests import _support  # noqa: F401

from nhk_radio import text


class TextHelpersTest(unittest.TestCase):
    def test_format_onair_date_normalizes_weekday(self):
        self.assertEqual(text._format_onair_date("2024年04月15日(月)放送"), "2024-04-15(月)")

    def test_format_duration_handles_hours(self):
        self.assertEqual(text._format_duration(3661), "1時間1分1秒")

    def test_sortable_duration_value(self):
        self.assertEqual(text._sortable_duration_value("2分5秒"), (1, 125))

    def test_fit_text_adds_ellipsis(self):
        self.assertEqual(text._fit_text("abcdefghijklmnopqrstuvwxyz", 8), "abcde...")


if __name__ == "__main__":
    unittest.main()

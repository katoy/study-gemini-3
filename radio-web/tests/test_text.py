import unittest
from datetime import datetime
from unittest.mock import patch

from nhk_radio_web import text


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
        self.assertEqual(
            text._format_broadcast_time(1713188400),
            datetime.fromtimestamp(1713188400).strftime("%H:%M:%S"),
        )

    def test_format_duration_handles_variants(self):
        self.assertEqual(text._format_duration(None), "")
        self.assertEqual(text._format_duration(0), "")
        self.assertEqual(text._format_duration(7), "--:--:07")
        self.assertEqual(text._format_duration(125), "--:02:05")
        self.assertEqual(text._format_duration(3661), "01:01:01")
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

    def test_fixed_display_date(self):
        dt = datetime(2024, 4, 15)
        self.assertEqual(text._fixed_display_date(dt), "2024-04-15(月)")

    def test_format_onair_date_variants(self):
        self.assertEqual(text._format_onair_date("2024-04-15"), "2024-04-15(月)")
        self.assertEqual(text._format_onair_date("2024/04/16"), "2024-04-16(火)")
        self.assertEqual(text._format_onair_date("20240417"), "2024-04-17(水)")
        self.assertEqual(text._format_onair_date("2024年4月18日"), "2024-04-18(木)")
        self.assertEqual(text._format_onair_date("不明な日付"), "不明な日付")

    def test_sortable_day_value_invalid_cases(self):
        self.assertEqual(text._sortable_day_value("20240230"), (0, 0))
        self.assertEqual(text._sortable_day_value("2024年13月01日"), (0, 0))
        self.assertEqual(text._sortable_day_value("放送"), (0, 0))

    def test_sortable_timestamp_value_iso(self):
        ts = text._sortable_timestamp_value("2024-04-15T00:00:00Z")
        self.assertEqual(ts[0], 1)
        self.assertEqual(ts[1], 1713139200.0)
        ts_jst = text._sortable_timestamp_value("2024-04-15T09:00:00+09:00")
        self.assertEqual(ts_jst[1], 1713139200.0)

    def test_program_display_title_cases(self):
        self.assertEqual(text._program_display_title("番組", "番組"), "番組")
        self.assertEqual(text._program_display_title("", "コーナー"), "コーナー")
        self.assertEqual(text._program_display_title("番組", ""), "番組")

    def test_genre_label_and_width_helpers(self):
        self.assertEqual(text._genre_label("language"), "語学")
        self.assertEqual(text._genre_label("unknown"), "未分類")
        self.assertEqual(text._char_width("あ"), 2)
        self.assertEqual(text._char_width("a"), 1)
        self.assertEqual(text._display_width("abあ"), 4)
        self.assertEqual(text._display_width(""), 0)


if __name__ == "__main__":
    unittest.main()

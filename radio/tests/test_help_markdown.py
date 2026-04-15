import unittest

from tests import _support  # noqa: F401

from nhk_radio.gui import help_markdown


class HelpMarkdownTest(unittest.TestCase):
    def test_genre_markdown_contains_english_and_japanese(self):
        rendered = help_markdown._render_genre_list_markdown()
        self.assertIn("- `language`: 語学", rendered)
        self.assertIn("- `variety`: バラエティ", rendered)

    def test_corner_markdown_deduplicates_loaded_programs(self):
        programs = [
            {"site_id": "AAA", "corner_id": "01", "corner_name": "入門ビジネス英語"},
            {"site_id": "AAA", "corner_id": "01", "corner_name": "入門ビジネス英語"},
            {"site_id": "BBB", "corner_id": "02", "corner_name": "ニュースで学ぶ現代英語"},
        ]
        rendered = help_markdown._render_corner_list_markdown(programs)
        self.assertIn("- `AAA_01`: 入門ビジネス英語", rendered)
        self.assertIn("- `BBB_02`: ニュースで学ぶ現代英語", rendered)
        self.assertEqual(rendered.count("AAA_01"), 1)

    def test_build_help_markdown_replaces_template_placeholders(self):
        markdown = help_markdown.build_help_markdown(
            [{"site_id": "AAA", "corner_id": "01", "corner_name": "入門ビジネス英語"}]
        )
        self.assertIn("# NHK ラジオ 聞き逃し ヘルプ", markdown)
        self.assertIn("- `language`: 語学", markdown)
        self.assertIn("- `AAA_01`: 入門ビジネス英語", markdown)
        self.assertNotIn("{{GENRE_LIST}}", markdown)
        self.assertNotIn("{{CORNER_LIST}}", markdown)

    def test_split_inline_markdown_detects_strong_and_code(self):
        segments = help_markdown._split_inline_markdown("**重要** と `Ctrl/Cmd + F` を確認")
        self.assertEqual(
            segments,
            [("strong", "重要"), ("text", " と "), ("code", "Ctrl/Cmd + F"), ("text", " を確認")],
        )


if __name__ == "__main__":
    unittest.main()

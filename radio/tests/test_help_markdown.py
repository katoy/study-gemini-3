import unittest

from nhk_radio.gui import help_markdown
from nhk_radio.types import Program
from tests import _support  # noqa: F401


def _make_program(site_id: str, corner_id: str, corner_name: str) -> Program:
    return Program(
        title=corner_name or f"{site_id}_{corner_id}",
        display_title=corner_name or f"{site_id}_{corner_id}",
        display_date="----",
        site_id=site_id,
        corner_id=corner_id,
        url="",
        corner_name=corner_name,
    )


class HelpMarkdownTest(unittest.TestCase):
    def test_genre_markdown_contains_english_and_japanese(self):
        rendered = help_markdown._render_genre_list_markdown()
        self.assertIn("- `language`: 語学", rendered)
        self.assertIn("- `variety`: バラエティ", rendered)

    def test_corner_markdown_deduplicates_loaded_programs(self):
        programs = [
            _make_program("AAA", "01", "入門ビジネス英語"),
            _make_program("AAA", "01", "入門ビジネス英語"),
            _make_program("BBB", "02", "ニュースで学ぶ現代英語"),
        ]
        rendered = help_markdown._render_corner_list_markdown(programs)
        self.assertIn("- `AAA_01`: 入門ビジネス英語", rendered)
        self.assertIn("- `BBB_02`: ニュースで学ぶ現代英語", rendered)
        self.assertEqual(rendered.count("AAA_01"), 1)

    def test_build_help_markdown_replaces_template_placeholders(self):
        markdown = help_markdown.build_help_markdown(
            [_make_program("AAA", "01", "入門ビジネス英語")]
        )
        self.assertIn("# NHK ラジオ 聞き逃し ヘルプ", markdown)
        self.assertIn("- `language`: 語学", markdown)
        self.assertIn("- `AAA_01`: 入門ビジネス英語", markdown)
        self.assertNotIn("{{GENRE_LIST}}", markdown)
        self.assertNotIn("{{CORNER_LIST}}", markdown)
        # 操作説明や説明書検索・CLI・保存先の章が含まれ、検索対象リファレンスより先頭に配置されている
        self.assertIn("## 説明書の検索と目次移動", markdown)
        self.assertIn("## コマンドライン (CLI) の使い方", markdown)
        self.assertIn("## 保存先と設定ファイルの場所", markdown)
        self.assertLess(markdown.index("## 基本操作の流れ"), markdown.index("## 検索対象の一覧"))

    def test_split_inline_markdown_detects_strong_and_code(self):
        segments = help_markdown._split_inline_markdown("**重要** と `Ctrl/Cmd + F` を確認")
        self.assertEqual(
            segments,
            [("strong", "重要"), ("text", " と "), ("code", "Ctrl/Cmd + F"), ("text", " を確認")],
        )

    def test_find_help_matches_supports_nfkc_casefold_and_multiple_hits(self):
        text = "Ｆ１キーで Help を開く\nhelp の設定と ﬁle 確認\n"
        self.assertEqual(help_markdown.find_help_matches(text, ""), [])
        self.assertEqual(help_markdown.find_help_matches("", "help"), [])
        self.assertEqual(help_markdown.find_help_matches(text, "見つからない語"), [])

        f1_matches = help_markdown.find_help_matches(text, "f1")
        self.assertEqual(f1_matches, [("1.0", "1.2")])

        help_matches = help_markdown.find_help_matches(text, "HELP")
        self.assertEqual(help_matches, [("1.6", "1.10"), ("2.0", "2.4")])

        ligature_matches = help_markdown.find_help_matches(text, "file")
        self.assertEqual(ligature_matches, [("2.10", "2.13")])


if __name__ == "__main__":
    unittest.main()

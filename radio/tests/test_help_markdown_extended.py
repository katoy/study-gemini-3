import unittest
from unittest.mock import MagicMock, call, patch

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


class HelpMarkdownExtendedTest(unittest.TestCase):
    def test_render_corner_list_empty(self):
        rendered = help_markdown._render_corner_list_markdown([])
        self.assertIn("(no loaded corner_name data)", rendered)

    def test_render_corner_list_invalid_data(self):
        programs = [
            _make_program("", "01", "A"),  # site_id missing
            _make_program("S", "", "A"),  # corner_id missing
            _make_program("S", "01", ""),  # corner_name missing
        ]
        rendered = help_markdown._render_corner_list_markdown(programs)
        self.assertIn("(no loaded corner_name data)", rendered)

    def test_render_help_markdown_full_flow(self):
        # Mocking Text widget and its dependencies
        text_widget = MagicMock()
        palette = {
            "surface": "#111", "text": "#eee", "selected_bg": "#333", "selected_fg": "#fff",
            "accent": "#00f", "accent_dark": "#008", "accent_soft": "#eef", "surface_alt": "#222"
        }
        fonts = {
            "body": ("sans", 10), "strong": ("sans", 10, "bold"), "mono": ("mono", 10),
            "h1": ("sans", 16), "h2": ("sans", 14), "h3": ("sans", 12)
        }

        markdown = """# H1 Title
## H2 Subtitle
### H3 Small

- Bullet item
1. Numbered item

```
code block line 1
code block line 2
```

Normal paragraph with **strong** and `code`.
"""

        help_markdown.render_help_markdown(text_widget, markdown, palette, fonts)

        # Basic verification of calls
        self.assertTrue(text_widget.insert.called)
        
        # Check H1
        text_widget.insert.assert_any_call("end", "H1 Title", ("h1",))
        # Check Bullet
        text_widget.insert.assert_any_call("end", "• ", ("bullet_marker",))
        # Check Numbered
        text_widget.insert.assert_any_call("end", "1. ", ("bullet_marker",))
        # Check Code Block
        text_widget.insert.assert_any_call("end", "code block line 1\ncode block line 2\n\n", ("codeblock",))
        # Check Paragraph inline
        text_widget.insert.assert_any_call("end", "strong", ("strong",))
        text_widget.insert.assert_any_call("end", "code", ("inline_code",))

    def test_render_help_markdown_empty_lines(self):
        text_widget = MagicMock()
        palette = MagicMock()
        fonts = MagicMock()
        
        markdown = "\n\n\n"
        help_markdown.render_help_markdown(text_widget, markdown, palette, fonts)
        text_widget.insert.assert_any_call("end", "\n")

    def test_render_help_markdown_multi_line_paragraph(self):
        text_widget = MagicMock()
        palette = MagicMock()
        fonts = MagicMock()
        
        markdown = "Line 1\nLine 2\nLine 3"
        help_markdown.render_help_markdown(text_widget, markdown, palette, fonts)
        # "Line 1 Line 2 Line 3" as a single call to _insert_inline_segments
        text_widget.insert.assert_any_call("end", "Line 1 Line 2 Line 3", ("body",))

    def test_split_inline_markdown_fallback(self):
        # Current regex (\*\*.+?\*\*|`.+?`) always starts/ends with markers,
        # but if it matched something else, the else branch would be hit.
        # We can't easily hit it with the current regex, but we can test the function logic.
        with patch("re.compile") as compile_mock:
            # Mock match to return something not starting with ** or `
            match_mock = MagicMock()
            match_mock.span.return_value = (0, 5)
            match_mock.group.return_value = "dummy"
            
            pattern_mock = MagicMock()
            pattern_mock.finditer.return_value = [match_mock]
            compile_mock.return_value = pattern_mock
            
            segments = help_markdown._split_inline_markdown("dummy")
            self.assertEqual(segments, [("text", "dummy")])

if __name__ == "__main__":
    unittest.main()

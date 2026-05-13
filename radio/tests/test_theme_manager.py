import unittest
from unittest.mock import MagicMock

from nhk_radio.gui.theme_manager import ThemeManager


class ThemeManagerTest(unittest.TestCase):
    def setUp(self):
        # root はモックでOK (Tkinterの初期化を避けるため)
        self.root = MagicMock()
        self.tm = ThemeManager(self.root)

    def test_palette_keys_consistency(self):
        """UIが期待する全てのカラーキーがパレットに存在することを検証する。"""
        # UI (styling.py 等) が参照している主要なキーのリスト
        required_keys = [
            "bg", "surface", "surface_alt", "text", "text_sub", "primary",
            "accent", "row_odd", "dl_even", "dl_odd", "border", "selected_bg"
        ]

        for theme in ["light", "dark"]:
            palette = self.tm._get_palette(theme)
            for key in required_keys:
                with self.subTest(theme=theme, key=key):
                    self.assertIn(key, palette, f"Theme '{theme}' is missing required key '{key}'")

    def test_font_profile_keys_consistency(self):
        """UIが期待する全てのフォントキーが存在することを検証する。"""
        required_keys = [
            "ui_base", "ui_bold", "ui_small", "mono", "app_title",
            "heading", "card_title", "rowheight"
        ]

        profile = self.tm._get_font_profile(11)
        for key in required_keys:
            with self.subTest(key=key):
                self.assertIn(key, profile, f"Font profile is missing required key '{key}'")

    def test_apply_theme_execution(self):
        """apply_theme が例外なく実行され、基本属性が設定されることを検証する。"""
        # 実際に適用を試みる (style.theme_use 等の副作用を確認)
        try:
            self.tm.apply_theme("dark", 12)
        except Exception as e:
            self.fail(f"apply_theme raised {type(e).__name__} unexpectedly: {e}")

        self.assertEqual(self.tm.current_theme, "dark")
        self.assertEqual(self.tm.current_font_size, 12)

if __name__ == "__main__":
    unittest.main()

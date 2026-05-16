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

    def test_wcag_accent_button_contrast(self):
        """アクセントボタンの on_accent / accent 組み合わせが WCAG AA (4.5:1) を満たす。"""
        def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
            hex_color = hex_color.lstrip("#")
            return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore

        def relative_luminance(rgb: tuple[float, float, float]) -> float:
            r, g, b = rgb
            rsrgb = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
            gsrgb = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
            bsrgb = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
            return 0.2126 * rsrgb + 0.7152 * gsrgb + 0.0722 * bsrgb

        def contrast_ratio(fg: str, bg: str) -> float:
            fg_lum = relative_luminance(hex_to_rgb(fg))
            bg_lum = relative_luminance(hex_to_rgb(bg))
            lighter = max(fg_lum, bg_lum)
            darker = min(fg_lum, bg_lum)
            return (lighter + 0.05) / (darker + 0.05)

        # ライトテーマの検証
        light_palette = self.tm._get_palette("light")
        light_ratio = contrast_ratio(light_palette["on_accent"], light_palette["accent"])
        self.assertGreaterEqual(light_ratio, 4.5, f"Light theme accent button contrast {light_ratio:.2f} is below WCAG AA (4.5:1)")

        # ダークテーマの検証
        dark_palette = self.tm._get_palette("dark")
        dark_ratio = contrast_ratio(dark_palette["on_accent"], dark_palette["accent"])
        self.assertGreaterEqual(dark_ratio, 4.5, f"Dark theme accent button contrast {dark_ratio:.2f} is below WCAG AA (4.5:1)")

if __name__ == "__main__":
    unittest.main()

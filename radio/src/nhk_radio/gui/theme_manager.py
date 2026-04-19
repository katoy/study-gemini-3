"""UI Theme and Style management decoupled from main logic."""

import logging
from typing import Any

from .. import config
from .toolkit import tk, ttk
from .logo import update_brand_logo

logger = logging.getLogger(__name__)


class ThemeManager:
    """Manages UI themes, colors, and fonts."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.style = ttk.Style(root)
        self.settings = config._load_ui_settings()
        self.current_theme = str(self.settings.get("theme", config.DEFAULT_UI_THEME))
        # _load_ui_settings が int を返すようになったので直接取得
        self.current_font_size = int(self.settings.get("font_size_pt", int(config.DEFAULT_UI_FONT_SIZE_PT)))
        
        self.font_family = self._resolve_ui_font_family()
        self.mono_family = self._resolve_mono_font_family()
        self.palette = self._get_palette(self.current_theme)
        self.font_profile = self._get_font_profile(self.current_font_size)

    def save_settings(self, theme: str, font_size: int, search_history: list[str]):
        """Persists UI settings to disk."""
        self.current_theme = theme
        self.current_font_size = font_size
        self.palette = self._get_palette(theme)
        
        config._save_ui_settings(theme, font_size, search_history)
        self.settings = {
            "theme": theme,
            "font_size_pt": font_size,
            "program_search_history": search_history,
        }

    def apply_theme(self, theme_name: str | None = None, font_size: int | None = None):
        """Applies current palette and fonts to the ttk.Style and root window."""
        if theme_name:
            self.current_theme = theme_name
            self.palette = self._get_palette(theme_name)
        if font_size:
            self.current_font_size = font_size
            self.font_profile = self._get_font_profile(font_size)

        p = self.palette
        f = self.font_profile

        self.root.configure(background=p["bg"])
        self.style.theme_use("clam")
        self.style.configure(".", background=p["bg"], foreground=p["text"], font=f["ui_base"])
        self.style.configure("TFrame", background=p["bg"])
        self.style.configure("TLabel", background=p["bg"], foreground=p["text"], font=f["ui_base"])
        
        self._configure_cards(p, f)
        self._configure_treeviews(p, f)
        self._configure_buttons(p, f)
        self._configure_inputs(p, f)
        self._configure_labels(p, f)
        self._configure_progressbars(p, f)

    def _get_palette(self, theme_name: str) -> dict[str, str]:
        if theme_name == "dark":
            return {
                "bg": "#121212", "surface": "#1E1E1E", "surface_alt": "#242424",
                "text": "#E0E0E0", "text_sub": "#AAAAAA", "primary": "#4dabf7",
                "accent": "#ff922b", "accent_soft": "#2C2014", "accent_dark": "#D97706",
                "border": "#333333", "border_strong": "#404040", "head_bg": "#252525",
                "selected_bg": "#2B5A8C", "selected_fg": "#FFFFFF",
                "row_odd": "#1A1A1A", "dl_even": "#121212", "dl_odd": "#1A1A1A", 
                "input_bg": "#2D2D2D", "on_accent": "#FFFFFF",
            }
        return {
            "bg": "#F8F9FA", "surface": "#FFFFFF", "surface_alt": "#F1F3F5",
            "text": "#212529", "text_sub": "#495057", "primary": "#1971C2",
            "accent": "#E8590C", "accent_soft": "#FFF4E6", "accent_dark": "#D9480F",
            "border": "#DEE2E6", "border_strong": "#CED4DA", "head_bg": "#E9ECEF",
            "selected_bg": "#E7F5FF", "selected_fg": "#000000",
            "row_odd": "#F1F3F5", "dl_even": "#F8F9FA", "dl_odd": "#F1F3F5", 
            "input_bg": "#FFFFFF", "on_accent": "#FFFFFF",
        }

    def _get_font_profile(self, size_pt: int | str) -> dict[str, Any]:
        base = int(size_pt)
        ui = self._resolve_ui_font_family()
        mono = self._resolve_mono_font_family()
        return {
            "ui_base": (ui, base + 1),
            "ui_bold": (ui, base + 1, "bold"),
            "ui_small": (ui, base),
            "mono": (mono, base + 1),
            "app_title": (ui, base + 8, "bold"),
            "heading": (ui, base + 3, "bold"),
            "card_title": (ui, base + 2, "bold"),
            "hero_title": (ui, base + 5, "bold"),
            "popup_title": (ui, base + 2, "bold"),
            "rowheight": base + 20,
        }

    def _resolve_ui_font_family(self) -> str:
        import sys
        if sys.platform == "darwin": return ".AppleSystemUIFont"
        if sys.platform == "win32": return "Yu Gothic UI"
        return "sans-serif"

    def _resolve_mono_font_family(self) -> str:
        import sys
        if sys.platform == "darwin": return "Menlo"
        if sys.platform == "win32": return "Consolas"
        return "monospace"

    def _configure_cards(self, p, f):
        self.style.configure("Card.TFrame", background=p["surface"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("CardInner.TFrame", background=p["surface"])
        self.style.configure("Sidebar.TFrame", background=p["surface_alt"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("SidebarInner.TFrame", background=p["surface_alt"])
        self.style.configure("Hero.TFrame", background=p["accent_soft"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("HeroInner.TFrame", background=p["accent_soft"])

    def _configure_treeviews(self, p, f):
        self.style.configure("Treeview", 
            font=f["ui_base"], 
            rowheight=f["rowheight"] + 2,
            background=p["surface"], 
            foreground=p["text"], 
            fieldbackground=p["surface"],
            borderwidth=0,
            highlightthickness=0,
            focuscolor="", 
            focusthickness=0
        )
        self.style.layout("Treeview.Item",
            [('Treeitem.padding', {'sticky': 'nswe', 'children': [
                ('Treeitem.text', {'sticky': 'nswe'})
            ]})]
        )
        self.style.configure("Treeview.Heading", font=f["ui_bold"], background=p["surface_alt"], foreground=p["text"])
        self.style.map("Treeview", 
            background=[("selected", p["selected_bg"])], 
            foreground=[("selected", p["selected_fg"])]
        )

    def _configure_buttons(self, p, f):
        self.style.configure("TButton", font=f["ui_base"], padding=(14, 8), relief="flat")
        self.style.configure("Accent.TButton", font=f["ui_bold"], padding=(16, 9), background=p["accent"], foreground=p["on_accent"])
        self.style.map("Accent.TButton", background=[("active", p["accent_dark"]), ("disabled", p["head_bg"])])
        sec_bg = p["accent_soft"] if self.current_theme == "light" else p["surface_alt"]
        sec_fg = p["accent_dark"] if self.current_theme == "light" else p["text"]
        for name in ["Quiet.TButton", "RajiruLink.TButton", "Toggle.TButton", "FontStep.TButton", "DownloadJobAction.TButton"]:
            self.style.configure(name, background=sec_bg, foreground=sec_fg, relief="solid" if self.current_theme == "light" else "flat")

    def _configure_inputs(self, p, f):
        self.style.configure("TEntry", fieldbackground=p["input_bg"], foreground=p["text"], insertcolor=p["text"])
        self.style.configure("TCombobox", fieldbackground=p["input_bg"], background=p["input_bg"], foreground=p["text"], arrowcolor=p["text"])
        self.style.map("TCombobox",
            fieldbackground=[("readonly", p["input_bg"])],
            foreground=[("readonly", p["text"])]
        )
        self.style.configure("Search.TCombobox", fieldbackground=p["input_bg"], background=p["input_bg"], foreground=p["text"], arrowcolor=p["text"])
        
        self.root.option_add("*TCombobox*Listbox.background", p["input_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["selected_bg"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["selected_fg"])

    def _configure_progressbars(self, p, f):
        # 進捗バーの視認性向上: 暗い溝 (trough) に鮮やかなバー (background)
        self.style.configure("TProgressbar", 
            troughcolor=p["bg"], 
            background=p["primary"], 
            borderwidth=1, 
            lightcolor=p["primary"], 
            darkcolor=p["primary"]
        )

    def _configure_labels(self, p, f):
        self.style.configure("AppTitle.TLabel", font=f["app_title"], foreground=p["text"], background=p["surface"])
        self.style.configure("Heading.TLabel", font=f["heading"], foreground=p["accent"], background=p["bg"])
        self.style.configure("CardTitle.TLabel", font=f["card_title"], foreground=p["text"], background=p["surface"])
        self.style.configure("HeroTitle.TLabel", font=f["hero_title"], foreground=p["text"], background=p["accent_soft"])
        self.style.configure("Status.TLabel", font=f["ui_small"], foreground=p["text_sub"], background=p["bg"])

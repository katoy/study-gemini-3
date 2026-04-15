"""Styling and settings helpers for EpisodeGuiBrowser."""

from ..config import DEFAULT_UI_FONT_SIZE_PT, DEFAULT_UI_THEME, _save_ui_settings
from .toolkit import tk, tkfont, ttk


class GuiStylingMixin:
    def _resolve_mono_font_family(self) -> str:
        candidates = (
            "Osaka-Mono",
            "Bizin Gothic",
            "Migu 1M",
            "Noto Sans Mono CJK JP",
            "UDEV Gothic",
            "SF Mono",
            "Menlo",
            "Monaco",
            "MS Gothic",
            "Courier New",
            "Courier",
        )
        if tkfont is None:
            return "Menlo"

        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:
            return "Menlo"

        for family in candidates:
            if family in available:
                return family
        return "TkFixedFont"
    def _resolve_ui_font_family(self) -> str:
        candidates = (
            "SF Pro Display",
            "SF Pro Text",
            ".SF NS Display",
            ".SF NS Text",
            "Helvetica Neue",
            "Helvetica",
            "Yu Gothic UI",
            "Hiragino Sans",
            "Noto Sans CJK JP",
            "Arial",
            "Segoe UI",
        )
        if tkfont is None:
            return "Helvetica"
        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:
            return "Helvetica"
        for family in candidates:
            if family in available:
                return family
        return "TkDefaultFont"
    def _theme_palette(self, theme_name: str) -> dict[str, str]:
        if theme_name == "dark":
            return {
                "bg": "#1C1C1E",
                "surface": "#2C2C2E",
                "surface_alt": "#3A3A3C",
                "accent": "#0A84FF",
                "accent_dark": "#0066CC",
                "accent_soft": "#0A2744",
                "on_accent": "#FFFFFF",
                "selected_bg": "#3B9BFF",
                "selected_fg": "#FFFFFF",
                "text": "#F5F5F7",
                "text_sub": "#98989D",
                "border": "#3A3A3C",
                "border_strong": "#48484A",
                "head_bg": "#2C2C2E",
                "row_odd": "#252527",
                "dl_even": "#1C2E22",
                "dl_odd": "#1F3326",
                "input_bg": "#1C1C1E",
            }
        return {
            "bg": "#F2F2F7",
            "surface": "#FFFFFF",
            "surface_alt": "#F5F5F7",
            "accent": "#007AFF",
            "accent_dark": "#0055B3",
            "accent_soft": "#E5F1FF",
            "on_accent": "#FFFFFF",
            "selected_bg": "#007AFF",
            "selected_fg": "#FFFFFF",
            "text": "#1D1D1F",
            "text_sub": "#6E6E73",
            "border": "#E0E0E5",
            "border_strong": "#C7C7CC",
            "head_bg": "#F2F2F7",
            "row_odd": "#F9F9FB",
            "dl_even": "#F0FBF4",
            "dl_odd": "#E5F7EC",
            "input_bg": "#FFFFFF",
        }
    def _font_profile(self, size_name: str) -> dict[str, tuple | int]:
        try:
            base = int(size_name)
        except ValueError:
            base = 11
        ui = self.ui_font_family
        mono = self.font_family
        return {
            "mono_sm": (mono, base),
            "mono": (mono, base + 1),
            "mono_bold": (mono, base + 1, "bold"),
            "ui_small": (ui, base),
            "ui_base": (ui, base + 1),
            "ui_bold": (ui, base + 1, "bold"),
            "app_title": (ui, base + 8, "bold"),
            "heading": (ui, base + 3, "bold"),
            "card_title": (ui, base + 2, "bold"),
            "hero_title": (ui, base + 5, "bold"),
            "popup_title": (ui, base + 2, "bold"),
            "rowheight": base + 18,
        }
    def _load_font_profile(self):
        profile = self._font_profile(self.current_font_size)
        self._mono_sm = profile["mono_sm"]
        self._mono = profile["mono"]
        self._mono_bold = profile["mono_bold"]
        self._ui_small = profile["ui_small"]
        self._ui_base = profile["ui_base"]
        self._ui_bold = profile["ui_bold"]
        self._app_title_font = profile["app_title"]
        self._heading_font = profile["heading"]
        self._card_title_font = profile["card_title"]
        self._hero_title_font = profile["hero_title"]
        self._popup_title_font = profile["popup_title"]
        self._tree_rowheight = profile["rowheight"]
    def _configure_theme_styles(self):
        p = self._palette
        self.root.configure(background=p["bg"])
        sec = self._secondary_button_props(p)
        self._configure_base_styles(p)
        self._configure_treeview_styles(p)
        self._configure_button_styles(p, sec)
        self._configure_label_styles(p, sec)
        self._configure_live_widget_styles(p)
    def _secondary_button_props(self, p: dict) -> dict:
        tinted = self.current_theme == "light"
        return {
            "bg": p["accent_soft"] if tinted else p["surface_alt"],
            "fg": p["accent_dark"] if tinted else p["text"],
            "border": p["accent"] if tinted else p["border_strong"],
            "hover_bg": p["accent"] if tinted else p["head_bg"],
            "hover_fg": p["on_accent"] if tinted else p["text"],
            "relief": "solid" if tinted else "flat",
            "borderwidth": 1 if tinted else 0,
        }
    def _configure_base_styles(self, p: dict) -> None:
        self.style.configure(".", background=p["bg"], foreground=p["text"], font=self._ui_base)
        self.style.configure("TFrame", background=p["bg"])
        self.style.configure("TLabel", background=p["bg"], foreground=p["text"], font=self._ui_base)
        self.style.configure("Card.TFrame", background=p["surface"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("CardInner.TFrame", background=p["surface"])
        self.style.configure("Sidebar.TFrame", background=p["surface_alt"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("SidebarInner.TFrame", background=p["surface_alt"])
        self.style.configure("Hero.TFrame", background=p["accent_soft"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("HeroInner.TFrame", background=p["accent_soft"])
        self.style.configure("TLabelframe", background=p["surface"], bordercolor=p["border"], relief="solid", borderwidth=1)
        self.style.configure("TLabelframe.Label", background=p["surface"], foreground=p["text_sub"], font=self._ui_small)
        self.style.configure("TSeparator", background=p["border"])
        self.style.configure(
            "TScrollbar",
            background=p["head_bg"],
            troughcolor=p["bg"],
            bordercolor=p["border"],
            arrowcolor=p["text_sub"],
        )
    def _configure_treeview_styles(self, p: dict) -> None:
        self.style.configure(
            "Treeview",
            font=self._mono,
            rowheight=self._tree_rowheight,
            background=p["surface"],
            foreground=p["text"],
            fieldbackground=p["surface"],
            bordercolor=p["border_strong"],
            lightcolor=p["border_strong"],
            darkcolor=p["border_strong"],
        )
        self.style.configure(
            "Treeview.Heading",
            font=self._ui_bold,
            background=p["surface_alt"],
            foreground=p["text"],
            relief="solid",
            padding=(10, 9),
            bordercolor=p["border_strong"],
            lightcolor=p["border_strong"],
            darkcolor=p["border_strong"],
            borderwidth=1,
        )
        self.style.map(
            "Treeview",
            background=[("selected", p["selected_bg"])],
            foreground=[("selected", p["selected_fg"])],
        )
        self.style.map(
            "Treeview.Heading",
            background=[("active", p["head_bg"])],
            foreground=[("active", p["text"])],
        )
    def _configure_button_styles(self, p: dict, sec: dict) -> None:
        self.style.configure("TButton", font=self._ui_base, padding=(14, 8), relief="flat")
        self.style.configure(
            "Accent.TButton",
            font=self._ui_bold,
            padding=(16, 9),
            background=p["accent"],
            foreground=p["on_accent"],
            bordercolor=p["accent_dark"],
            relief="flat",
        )
        self.style.map(
            "Accent.TButton",
            background=[("active", p["accent_dark"]), ("disabled", p["head_bg"])],
            foreground=[("active", p["on_accent"]), ("disabled", p["text_sub"])],
        )
        for name, font, padding in [
            ("Quiet.TButton", self._ui_base, (14, 8)),
            ("RajiruLink.TButton", self._ui_bold, (10, 5)),
            ("Toggle.TButton", self._ui_base, (14, 8)),
            ("FontStep.TButton", self._ui_bold, (10, 6)),
            ("DownloadJobAction.TButton", self._ui_base, (12, 6)),
        ]:
            self.style.configure(
                name,
                font=font,
                padding=padding,
                background=sec["bg"],
                foreground=sec["fg"],
                bordercolor=sec["border"],
                relief=sec["relief"],
                borderwidth=sec["borderwidth"],
            )
            self.style.map(
                name,
                background=[("active", sec["hover_bg"]), ("disabled", p["surface_alt"])],
                foreground=[("active", sec["hover_fg"]), ("disabled", p["text_sub"])],
            )
        self.style.configure(
            "SavedCell.TButton",
            font=self._ui_bold,
            padding=(0, 0),
            background=p["accent"],
            foreground=p["on_accent"],
            bordercolor=p["accent_dark"],
            relief="flat",
        )
        self.style.map(
            "SavedCell.TButton",
            background=[("active", p["accent_dark"]), ("pressed", p["accent_dark"])],
            foreground=[("active", p["on_accent"]), ("pressed", p["on_accent"])],
        )
        self._configure_settings_controls(p, sec)
        self._configure_input_styles(p)
    def _configure_settings_controls(self, p: dict, sec: dict) -> None:
        self.style.configure(
            "Settings.TRadiobutton",
            background=p["surface"],
            foreground=p["text"],
            font=self._ui_base,
        )
        self.style.map(
            "Settings.TRadiobutton",
            background=[("active", p["surface"])],
            foreground=[("disabled", p["text_sub"])],
        )
        self.style.configure(
            "Settings.Horizontal.TScale",
            background=p["surface"],
            troughcolor=p["head_bg"],
            bordercolor=p["border_strong"],
        )
        for preset in (9, 11, 13, 15):
            self.style.configure(
                f"FontPreset{preset}.TButton",
                font=(self.ui_font_family, preset, "bold"),
                padding=(10, 6),
                background=sec["bg"],
                foreground=sec["fg"],
                bordercolor=sec["border"],
                relief=sec["relief"],
                borderwidth=sec["borderwidth"],
            )
            self.style.map(
                f"FontPreset{preset}.TButton",
                background=[("active", sec["hover_bg"]), ("disabled", p["surface_alt"])],
                foreground=[("active", sec["hover_fg"]), ("disabled", p["text_sub"])],
            )
    def _configure_input_styles(self, p: dict) -> None:
        self.style.configure(
            "TEntry",
            fieldbackground=p["input_bg"],
            foreground=p["text"],
            insertcolor=p["text"],
            bordercolor=p["border_strong"],
            lightcolor=p["border_strong"],
            darkcolor=p["border_strong"],
        )
        self.style.map(
            "TEntry",
            fieldbackground=[("readonly", p["input_bg"])],
            foreground=[("readonly", p["text"])],
        )
        self.style.configure(
            "Search.TCombobox",
            fieldbackground=p["input_bg"],
            background=p["input_bg"],
            foreground=p["text"],
            insertcolor=p["text"],
            arrowcolor=p["text_sub"],
            bordercolor=p["border_strong"],
            lightcolor=p["border_strong"],
            darkcolor=p["border_strong"],
            padding=(4, 2),
        )
        self.style.map(
            "Search.TCombobox",
            fieldbackground=[("readonly", p["input_bg"]), ("disabled", p["head_bg"])],
            foreground=[("disabled", p["text_sub"])],
            arrowcolor=[("disabled", p["text_sub"]), ("active", p["text"])],
        )
        self.root.option_add("*TCombobox*Listbox.background", p["input_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["on_accent"])
        self.style.configure("TProgressbar", background=p["accent"], troughcolor=p["head_bg"], bordercolor=p["border"])
    def _configure_label_styles(self, p: dict, sec: dict) -> None:  # noqa: ARG002
        self.style.configure("AppTitle.TLabel", font=self._app_title_font, foreground=p["text"], background=p["surface"])
        self.style.configure("AppSub.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("SettingLabel.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("Heading.TLabel", font=self._heading_font, foreground=p["accent"], background=p["bg"])
        self.style.configure("CardTitle.TLabel", font=self._card_title_font, foreground=p["text"], background=p["surface"])
        self.style.configure("CardTitleAlt.TLabel", font=self._card_title_font, foreground=p["text"], background=p["surface_alt"])
        self.style.configure("CardMeta.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("CardMetaAlt.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["surface_alt"])
        self.style.configure(
            "DownloadJob.TFrame",
            background=p["surface_alt"],
            relief="solid",
            borderwidth=1,
            bordercolor=p["border"],
        )
        self.style.configure("DownloadJobTitle.TLabel", font=self._ui_bold, foreground=p["text"], background=p["surface_alt"])
        self.style.configure("DownloadJobMeta.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["surface_alt"])
        self.style.configure("DownloadJobStatus.TLabel", font=self._ui_bold, foreground=p["accent"], background=p["surface_alt"])
        self.style.configure("HeroTitle.TLabel", font=self._hero_title_font, foreground=p["text"], background=p["accent_soft"])
        self.style.configure("HeroMeta.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["accent_soft"])
        self.style.configure("HeroStats.TLabel", font=self._ui_bold, foreground=p["accent"], background=p["accent_soft"])
        self.style.configure("Status.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["bg"])
        self.style.configure("PopupTitle.TLabel", font=self._popup_title_font, foreground=p["text"], background=p["surface"])
        self.style.configure("PopupLabel.TLabel", font=self._ui_bold, foreground=p["text"], background=p["surface"])
        self.style.configure("PopupValue.TLabel", font=self._ui_small, foreground=p["text_sub"], background=p["surface"])
        self.style.configure("SettingsValue.TLabel", font=self._ui_bold, foreground=p["accent"], background=p["surface"])
        self.style.configure("SettingsPreview.TLabel", font=self._ui_base, foreground=p["text"], background=p["surface"])
        self.style.configure("FontPreview.TFrame", background=p["surface_alt"], relief="solid", borderwidth=1, bordercolor=p["border"])
        self.style.configure("FontPreviewTitle.TLabel", font=self._ui_bold, foreground=p["text"], background=p["surface_alt"])
        self.style.configure("FontPreviewBody.TLabel", font=self._ui_base, foreground=p["text"], background=p["surface_alt"])
    def _configure_live_widget_styles(self, p: dict) -> None:
        if hasattr(self, "download_jobs_canvas"):
            self.download_jobs_canvas.configure(
                background=p["surface"],
                highlightbackground=p["border"],
                highlightcolor=p["border"],
            )
        if hasattr(self, "settings_canvas"):
            self.settings_canvas.configure(
                background=p["surface"],
                highlightbackground=p["border"],
                highlightcolor=p["border"],
            )
        if self.tooltip_window is not None and self.tooltip_window.winfo_exists():
            self.tooltip_window.configure(background=p["border_strong"])
        if self.tooltip_label is not None and self.tooltip_label.winfo_exists():
            self.tooltip_label.configure(
                background=p["surface_alt"],
                foreground=p["text"],
            )
    def _refresh_treeview_theme(self):
        p = self._palette
        self.program_tree.tag_configure("even", background=p["surface"], foreground=p["text"])
        self.program_tree.tag_configure("odd", background=p["row_odd"], foreground=p["text"])
        self.episode_tree.tag_configure("even", background=p["surface"], foreground=p["text"])
        self.episode_tree.tag_configure("odd", background=p["row_odd"], foreground=p["text"])
        self.episode_tree.tag_configure("dl_even", background=p["dl_even"], foreground=p["text"])
        self.episode_tree.tag_configure("dl_odd", background=p["dl_odd"], foreground=p["text"])
        self._schedule_saved_button_refresh()
    def _update_settings_ui(self):
        theme_label = "ダーク" if self.current_theme == "dark" else "ライト"
        self.settings_summary_var.set(f"{theme_label} / 文字 {self.current_font_size}pt")
        self.font_size_display_var.set(f"{self.current_font_size} pt")
        self.settings_button_var.set("番組一覧" if self.current_screen == "settings" else "表示設定")
        self.settings_save_button_var.set("保存済み" if not self.settings_dirty else "保存")
        self.theme_var.set(self.current_theme)
        self.font_size_var.set(int(self.current_font_size))
        if hasattr(self, "settings_save_button"):
            if self.settings_dirty:
                self.settings_save_button.state(["!disabled"])
            else:
                self.settings_save_button.state(["disabled"])
        if hasattr(self, "clear_button"):
            if self.current_screen == "settings":
                self.clear_button.grid_remove()
            else:
                self.clear_button.grid()
    def _mark_settings_dirty(self):
        self.settings_dirty = (
            self.current_theme != self.saved_theme or self.current_font_size != self.saved_font_size
        )
        self._update_settings_ui()
    def _discard_unsaved_settings(self):
        if not self.settings_dirty:
            return False
        self.current_theme = self.saved_theme
        self.current_font_size = self.saved_font_size
        self._palette = self._theme_palette(self.current_theme)
        self._load_font_profile()
        self._configure_theme_styles()
        self._refresh_treeview_theme()
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.configure(background=self._palette["surface"])
        self.settings_dirty = False
        self._update_settings_ui()
        return True
    def _save_ui_settings_from_screen(self):
        self.saved_theme = self.current_theme
        self.saved_font_size = self.current_font_size
        self.settings_dirty = False
        self._persist_ui_settings()
        self._update_settings_ui()
        self.status_var.set("表示設定を保存しました。")
    def _update_selected_cell_ui(self):
        if self.current_screen == "settings":
            self.selected_cell_area.grid_remove()
            return

        self.selected_cell_area.grid()
        if self.selected_cell_value_var.get():
            self.copy_cell_button.state(["!disabled"])
        else:
            self.copy_cell_button.state(["disabled"])
    def _show_screen(self, screen_name: str, announce: bool = True):
        previous_screen = self.current_screen
        discarded_settings = False
        if previous_screen == "settings" and screen_name != "settings":
            discarded_settings = self._discard_unsaved_settings()
        self.current_screen = screen_name
        if screen_name == "settings":
            self.browser_screen.grid_remove()
            self.settings_screen.grid()
            self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all"))
            if announce:
                self.status_var.set("表示設定画面を開きました。")
        else:
            self.settings_screen.grid_remove()
            self.browser_screen.grid()
            if announce:
                if discarded_settings:
                    self.status_var.set("未保存の表示設定を破棄してブラウザ画面に戻りました。")
                else:
                    self.status_var.set("ブラウザ画面に戻りました。")
        self._update_selected_cell_ui()
        self._update_settings_ui()
    def _toggle_settings_screen(self):
        next_screen = "browser" if self.current_screen == "settings" else "settings"
        self._show_screen(next_screen)
    def _persist_ui_settings(self):
        _save_ui_settings(self.current_theme, self.current_font_size, self.program_search_history)
    def _apply_theme(self, theme_name: str, announce: bool = True):
        self.current_theme = theme_name
        self._palette = self._theme_palette(theme_name)
        self._configure_theme_styles()
        self._refresh_treeview_theme()
        self._mark_settings_dirty()
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.configure(background=self._palette["surface"])
        if announce:
            theme_label = "ダーク" if theme_name == "dark" else "ライト"
            self.status_var.set(f"{theme_label}テーマに切り替えました。")
    def _apply_font_size(self, size_name: str, announce: bool = True):
        self.current_font_size = size_name
        self._load_font_profile()
        self._configure_theme_styles()
        self._refresh_treeview_theme()
        self._mark_settings_dirty()
        if announce:
            self.status_var.set(f"文字サイズを {size_name}pt に変更しました。")
    def _set_font_size_value(self, size_pt: int, announce: bool = False):
        normalized = min(max(size_pt, 9), 18)
        normalized_text = str(normalized)
        self.font_size_var.set(normalized)
        if normalized_text == self.current_font_size:
            self.font_size_display_var.set(f"{normalized_text} pt")
            return
        self._apply_font_size(normalized_text, announce=announce)
    def _on_font_size_scale(self, value):
        self._set_font_size_value(int(round(float(value))), announce=False)
    def _adjust_font_size_scale(self, delta: int):
        current = int(round(float(self.font_size_var.get())))
        self._set_font_size_value(current + delta, announce=False)
    def _on_font_size_scale_left(self, _event=None):
        self._adjust_font_size_scale(-1)
        return "break"
    def _on_font_size_scale_right(self, _event=None):
        self._adjust_font_size_scale(1)
        return "break"
    def _on_font_size_scale_home(self, _event=None):
        self._set_font_size_value(9, announce=False)
        return "break"
    def _on_font_size_scale_end(self, _event=None):
        self._set_font_size_value(18, announce=False)
        return "break"
    def _decrease_font_size(self):
        self._adjust_font_size_scale(-1)
    def _increase_font_size(self):
        self._adjust_font_size_scale(1)
    def _apply_font_size_preset(self, size_pt: int):
        self._set_font_size_value(size_pt, announce=False)
    def _reset_ui_settings(self):
        self._apply_theme(DEFAULT_UI_THEME, announce=False)
        self._apply_font_size(DEFAULT_UI_FONT_SIZE_PT, announce=False)
        if self.settings_dirty:
            self.status_var.set("表示設定を規定値に戻しました。保存すると次回起動時にも反映されます。")
        else:
            self.status_var.set("表示設定を規定値に戻しました。")

    def _reset_ui_state_after_cache_clear(self):
        self.current_theme = DEFAULT_UI_THEME
        self.current_font_size = DEFAULT_UI_FONT_SIZE_PT
        self.saved_theme = DEFAULT_UI_THEME
        self.saved_font_size = DEFAULT_UI_FONT_SIZE_PT
        self.program_search_history = []
        self.settings_dirty = False
        self.program_search_var.set("")
        self._palette = self._theme_palette(self.current_theme)
        self._load_font_profile()
        self._configure_theme_styles()
        self._refresh_treeview_theme()
        self._update_program_search_history_values()
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.configure(background=self._palette["surface"])
        self._update_settings_ui()

__all__ = ['GuiStylingMixin']

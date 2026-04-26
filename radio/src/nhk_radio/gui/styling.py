"""UI Styling and Theme management for EpisodeGuiBrowser."""

import logging
from tkinter import ttk
from .theme_manager import ThemeManager
from ..config import DEFAULT_UI_THEME, DEFAULT_UI_FONT_SIZE_PT

logger = logging.getLogger(__name__)


class GuiStylingMixin:
    """Handles UI styling, theme switching, and font adjustments."""

    # Mixin properties to help type checker
    if False:
        from .browser import EpisodeGuiBrowser
        self = EpisodeGuiBrowser()

    def _initialize_theme(self):
        """Initializes ThemeManager and initial styles."""
        self.theme_manager = ThemeManager(self.root)
        self.style = self.theme_manager.style
        
        # Manager がロードした最新の状態を Mixin 側へ同期
        self.current_theme = self.theme_manager.current_theme
        self.current_font_size = str(self.theme_manager.current_font_size)
        
        self._apply_current_theme()

    @property
    def _palette(self) -> dict[str, str]:
        return self.theme_manager.palette

    def _apply_current_theme(self):
        """Updates the style using current theme and font size."""
        self.theme_manager.apply_theme(self.current_theme, int(self.current_font_size))
        self._load_font_profile()
        self._refresh_treeview_theme()
        self._update_settings_ui()

    def _load_font_profile(self):
        """Loads font references for the UI."""
        f = self.theme_manager.font_profile
        self._ui_base = f["ui_base"]
        self._ui_bold = f["ui_bold"]
        self._ui_small = f["ui_small"]
        self._mono = f["mono"]
        self._app_title_font = f["app_title"]
        self._heading_font = f["heading"]
        self._card_title_font = f["card_title"]
        self._hero_title_font = f["hero_title"]
        self._popup_title_font = f["popup_title"]
        self._tree_rowheight = f["rowheight"]

    def _refresh_treeview_theme(self):
        """Applies theme tags to treeview rows (Safety first version)."""
        # すべての装飾を ThemeManager 側に任せ、ここでは追加のタグ設定を行わない
        self._schedule_saved_button_refresh()


    def _save_ui_settings_from_screen(self):
        """Saves current settings via ThemeManager."""
        self.theme_manager.save_settings(
            self.current_theme, 
            int(self.current_font_size), 
            self.program_search_history
        )
        self.settings_dirty = False
        self._update_settings_ui()
        self.status_var.set("表示設定を保存しました。")

    def _apply_theme(self, theme_name: str, announce: bool = True):
        self.current_theme = theme_name
        self._apply_current_theme()
        self._mark_settings_dirty()
        if announce:
            label = "ダーク" if theme_name == "dark" else "ライト"
            self.status_var.set(f"{label}テーマに切り替えました。")

    def _apply_font_size(self, size_name: str, announce: bool = True):
        self.current_font_size = size_name
        self._apply_current_theme()
        self._mark_settings_dirty()
        if announce:
            self.status_var.set(f"文字サイズを {size_name}pt に変更しました。")

    def _set_font_size_value(self, size_pt: int, announce: bool = False):
        normalized = min(max(size_pt, 9), 18)
        normalized_text = str(normalized)
        if normalized_text == self.current_font_size:
            return
        self._apply_font_size(normalized_text, announce=announce)

    def _decrease_font_size(self):
        current = int(self.current_font_size)
        self._set_font_size_value(current - 1, announce=True)

    def _increase_font_size(self):
        current = int(self.current_font_size)
        self._set_font_size_value(current + 1, announce=True)

    def _apply_font_size_preset(self, size_pt: int):
        self._set_font_size_value(size_pt, announce=True)

    def _on_font_size_scale(self, value):
        self._set_font_size_value(int(float(value)))

    def _on_font_size_scale_left(self, _event):
        self._decrease_font_size()

    def _on_font_size_scale_right(self, _event):
        self._increase_font_size()

    def _on_font_size_scale_home(self, _event):
        self._set_font_size_value(9, announce=True)

    def _on_font_size_scale_end(self, _event):
        self._set_font_size_value(18, announce=True)

    def _mark_settings_dirty(self):
        s = self.theme_manager.settings
        self.settings_dirty = (
            self.current_theme != s.get("theme") or 
            int(self.current_font_size) != s.get("font_size_pt")
        )
        self._update_settings_ui()

    def _update_settings_ui(self):
        """Updates StringVar values for settings UI based on current theme/font."""
        if not hasattr(self, "settings_summary_var"):
            return
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

    def _on_settings_inner_configure(self, _event):
        self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all"))

    def _on_settings_canvas_configure(self, event):
        self.settings_canvas.itemconfig(self.settings_window, width=event.width)

    def _on_settings_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.settings_canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.settings_canvas.yview_scroll(1, "units")

    def _on_download_jobs_inner_configure(self, _event):
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))

    def _on_download_jobs_canvas_configure(self, event):
        self.download_jobs_canvas.itemconfig(self.download_jobs_window, width=event.width)

    def _on_download_jobs_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.download_jobs_canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.download_jobs_canvas.yview_scroll(1, "units")

    def _on_episode_tree_yscroll(self, *args):
        self.episode_scroll.set(*args)


__all__ = ["GuiStylingMixin"]

"""Tkinter GUI browser for NHK radio programs."""

import contextlib
import queue
import subprocess
import threading
from pathlib import Path

from ..config import DEFAULT_UI_FONT_SIZE_PT, DEFAULT_UI_THEME, _load_ui_settings
from ..types import Episode, Program
from .build import GuiBuildMixin
from .downloads import GuiDownloadsMixin
from .help_markdown import build_help_markdown, render_help_markdown
from .listing import GuiListingMixin
from .styling import GuiStylingMixin
from .toolkit import messagebox, tk, ttk


class EpisodeGuiBrowser(GuiStylingMixin, GuiBuildMixin, GuiListingMixin, GuiDownloadsMixin):
    def __init__(self, programs: list[Program] | None, output_dir: Path, *, audio_only: bool = True, genre: str | None = None):
        if tk is None or ttk is None:
            raise RuntimeError("tkinter が利用できません")

        self.programs = programs or []
        self.output_dir = output_dir
        self.audio_only = audio_only
        self.genre = genre
        self._initialize_runtime_state(self.programs)
        self._initialize_root_window()
        self._initialize_ui_state(self.programs)

        self._build_widgets()
        self._populate_programs()

        if programs is None:
            # 起動後に非同期取得を開始
            self.root.after(100, lambda: self._start_fetch_programs(genre))

    def _initialize_runtime_state(self, programs: list[Program]) -> None:
        self.result: tuple[Program, list[Episode]] | tuple[None, None] = (None, None)
        self.loading = False
        self.fetch_result_queue: queue.Queue | None = None
        self.program_fetch_queue: queue.Queue | None = None
        self.download_result_queue: queue.Queue = queue.Queue()
        self.download_polling = False
        self.download_cancel_events: dict[str, threading.Event] = {}
        self.download_processes: dict[str, subprocess.Popen] = {}
        self.download_process_lock = threading.Lock()
        self.active_download_rows: dict[str, dict] = {}
        self.active_download_meta: dict[str, tuple[Program, Episode]] = {}
        self.download_started_count = 0
        self.download_finished_count = 0
        self.episodes_cache: dict[tuple[str, str], tuple[float, list[Episode]]] = {}
        self.filtered_programs = list(programs)
        self.program_tree_programs: dict[str, Program] = {}
        self.displayed_program: Program | None = None
        self.displayed_episodes: list[Episode] = []
        self.displayed_episode_map: dict[str, Episode] = {}
        self.program_sort_column: str | None = None
        self.program_sort_reverse = False
        self.episode_sort_column: str | None = None
        self.episode_sort_reverse = False
        self.saved_episode_buttons: dict[str, ttk.Button] = {}
        self.saved_button_refresh_pending = False
        self.saved_episode_popup: tk.Toplevel | None = None
        self.help_popup: tk.Toplevel | None = None
        self.help_text: tk.Text | None = None
        self.help_markdown_content: str | None = None
        self.tooltip_window: tk.Toplevel | None = None
        self.tooltip_label: tk.Label | None = None
        self.program_order_map = {self._program_key(program): index for index, program in enumerate(programs, 1)}

    def _initialize_root_window(self) -> None:
        self.root = tk.Tk()
        self.root.title("NHK ラジオ 聞き逃しブラウザ")

        # macOS でのイベントループ初期化エラーを抑制するためのヒント
        with contextlib.suppress(tk.TclError):
            self.root.update_idletasks()

        # デモモード時は録画しやすいように位置を固定
        import os

        if os.environ.get("NHK_RADIO_DEMO_MODE"):
            self.root.geometry("1360x840+0+0")
        else:
            self.root.geometry("1360x840")
        self.root.minsize(1040, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

    def _initialize_ui_state(self, programs: list[Program]) -> None:
        self.current_theme = DEFAULT_UI_THEME
        self.current_font_size = DEFAULT_UI_FONT_SIZE_PT
        self.current_screen = "browser"
        saved_ui_settings = _load_ui_settings()
        self.current_theme = saved_ui_settings.get("theme", self.current_theme)
        self.current_font_size = saved_ui_settings.get("font_size_pt", self.current_font_size)
        self.saved_theme = self.current_theme
        self.saved_font_size = self.current_font_size
        self.settings_dirty = False
        self.program_search_history = list(saved_ui_settings.get("program_search_history", []))
        self.font_family = self._resolve_mono_font_family()
        self.ui_font_family = self._resolve_ui_font_family()

        self.status_var = tk.StringVar(value="番組を選択してください。")
        self.selected_cell_meta_var = tk.StringVar(value="")
        self.selected_cell_value_var = tk.StringVar(value="")
        self.program_list_summary_var = tk.StringVar(value=f"{len(programs)} 番組")
        self.program_search_var = tk.StringVar()
        self.program_genre_filter_var = tk.StringVar(value="すべて")
        self.selected_program_title_var = tk.StringVar(value="")
        self.selected_program_meta_var = tk.StringVar(value="")
        self.selected_program_stats_var = tk.StringVar(value="")
        self.episode_message_var = tk.StringVar(value="")
        self.episode_filter_summary_var = tk.StringVar(value="表示中 0 件")
        self.episode_selection_summary_var = tk.StringVar(value="選択 0 件")
        self.episode_search_var = tk.StringVar()
        self.episode_saved_only_var = tk.BooleanVar(value=False)
        self.progress_text_var = tk.StringVar(value="")
        self.settings_button_var = tk.StringVar()
        self.settings_summary_var = tk.StringVar()
        self.font_size_display_var = tk.StringVar()
        self.settings_save_button_var = tk.StringVar()
        self.theme_var = tk.StringVar(value=self.current_theme)
        self.font_size_var = tk.IntVar(value=int(self.current_font_size))
        self.program_search_var.trace_add("write", self._on_program_search_change)
        self.program_genre_filter_var.trace_add("write", self._on_program_filter_change)
        self.episode_search_var.trace_add("write", self._on_episode_filter_change)
        self.episode_saved_only_var.trace_add("write", self._on_episode_filter_change)

    def run(self) -> tuple[Program, list[Episode]] | tuple[None, None]:
        self.root.mainloop()
        return self.result

    def _cancel(self):
        if self.help_popup is not None and self.help_popup.winfo_exists():
            self.help_popup.destroy()
            return
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.destroy()
            return
        if self.current_screen == "settings" and self.settings_dirty:
            if messagebox is None or not messagebox.askyesno(
                "未保存の表示設定", "未保存の表示設定を破棄して終了しますか？", parent=self.root
            ):
                return
            self._discard_unsaved_settings()
        has_running_download = any(row["state"] == "running" for row in self.active_download_rows.values())
        if self.loading or has_running_download:
            if messagebox is not None:
                messagebox.showwarning(
                    "処理中です",
                    "一覧取得またはダウンロード処理が実行中です。完了または中断してから閉じてください。",
                    parent=self.root,
                )
            return
        self.result = (None, None)
        self.root.destroy()

    def _is_text_input_focus(self) -> bool:
        widget = self.root.focus_get()
        if widget is None:
            return False
        return widget in {
            getattr(self, "program_search_entry", None),
            getattr(self, "episode_search_entry", None),
            getattr(self, "selected_cell_entry", None),
        }

    def _focus_program_search(self, _event=None):
        if hasattr(self, "program_search_entry"):
            self.program_search_entry.focus_set()
            self.program_search_entry.icursor("end")
        return "break"

    def _focus_episode_search(self, _event=None):
        if hasattr(self, "episode_search_entry"):
            self.episode_search_entry.focus_set()
            self.episode_search_entry.icursor("end")
        return "break"

    def _show_help_dialog(self, _event=None):
        if self.help_popup is not None and self.help_popup.winfo_exists():
            self.help_popup.lift()
            self.help_popup.focus_force()
            return "break"

        popup = tk.Toplevel(self.root)
        popup.title("ヘルプ / ショートカット")
        popup.geometry("840x640")
        popup.minsize(700, 500)
        popup.transient(self.root)
        popup.configure(background=self._palette["surface"])
        popup.bind("<Escape>", lambda _event: popup.destroy())
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)

        main = ttk.Frame(popup, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        body = ttk.Frame(main)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.help_text = tk.Text(
            body,
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=1,
            cursor="arrow",
        )
        self.help_text.grid(row=0, column=0, sticky="nsew")
        help_scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.help_text.yview)
        help_scrollbar.grid(row=0, column=1, sticky="ns")
        self.help_text.configure(yscrollcommand=help_scrollbar.set)
        self.help_markdown_content = build_help_markdown(self.programs)
        render_help_markdown(self.help_text, self.help_markdown_content, self._palette, self._help_markdown_fonts())

        actions = ttk.Frame(main)
        actions.grid(row=1, column=0, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="閉じる", command=popup.destroy, style="Accent.TButton").grid(row=0, column=0)

        popup.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        popup_w = popup.winfo_width()
        popup_h = popup.winfo_height()
        popup.geometry(f"+{root_x + max((root_w - popup_w) // 2, 0)}+{root_y + max((root_h - popup_h) // 2, 0)}")
        popup.lift()
        popup.focus_force()
        self.help_popup = popup
        popup.bind(
            "<Destroy>",
            lambda _event: (
                setattr(self, "help_popup", None),
                setattr(self, "help_text", None),
                setattr(self, "help_markdown_content", None),
            ),
            add="+",
        )
        return "break"

    def _help_markdown_fonts(self) -> dict[str, tuple]:
        return {
            "h1": self._app_title_font,
            "h2": self._heading_font,
            "h3": self._card_title_font,
            "body": self._ui_base,
            "strong": self._ui_bold,
            "mono": self._mono,
        }

    def _handle_escape(self, _event=None):
        if self.help_popup is not None and self.help_popup.winfo_exists():
            self.help_popup.destroy()
            return "break"
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.destroy()
            return "break"
        if self.current_screen == "settings":
            self._show_screen("browser")
            return "break"
        if self._is_text_input_focus():
            widget = self.root.focus_get()
            if widget is self.program_search_entry:
                return self._clear_program_search()
            if widget is self.episode_search_entry:
                return self._clear_episode_search()
        return None

    def _handle_browser_shortcut(self, event):
        if self.current_screen != "browser" or self.loading or self._is_text_input_focus():
            return None
        key = (event.keysym or "").lower()
        if key == "f":
            return self._start_fetch_selected()
        if key == "d":
            return self._start_download_selected()
        if key in {"question", "slash"} and bool(event.state & 0x1):
            return self._show_help_dialog()
        return None


def browse_programs(
    programs: list[Program] | None, output_dir: Path, *, audio_only: bool = True, genre: str | None = None
) -> tuple[Program, list[Episode]] | tuple[None, None]:

    try:
        return EpisodeGuiBrowser(programs, output_dir, audio_only=audio_only, genre=genre).run()
    except tk.TclError as e:
        raise RuntimeError(str(e)) from e



# ──────────────────────────────────────────────────────
# 対話型選択 UI
# ──────────────────────────────────────────────────────

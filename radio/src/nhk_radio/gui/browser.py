"""Tkinter GUI browser for NHK radio programs."""

import queue
import subprocess
import threading
from pathlib import Path

from ..config import DEFAULT_UI_FONT_SIZE_PT, DEFAULT_UI_THEME, _load_ui_settings
from .build import GuiBuildMixin
from .downloads import GuiDownloadsMixin
from .listing import GuiListingMixin
from .styling import GuiStylingMixin
from .toolkit import tk, ttk



class EpisodeGuiBrowser(GuiStylingMixin, GuiBuildMixin, GuiListingMixin, GuiDownloadsMixin):
    def __init__(self, programs: list[dict], output_dir: Path, *, audio_only: bool = True):
        if tk is None or ttk is None:
            raise RuntimeError("tkinter が利用できません")

        self.programs = programs
        self.output_dir = output_dir
        self.audio_only = audio_only
        self._initialize_runtime_state(programs)
        self._initialize_root_window()
        self._initialize_ui_state(programs)

        self._build_widgets()
        self._populate_programs()

    def _initialize_runtime_state(self, programs: list[dict]) -> None:
        self.result: tuple[dict, list[dict]] | tuple[None, None] = (None, None)
        self.loading = False
        self.fetch_result_queue: queue.Queue | None = None
        self.download_result_queue: queue.Queue = queue.Queue()
        self.download_polling = False
        self.download_cancel_events: dict[str, threading.Event] = {}
        self.download_processes: dict[str, subprocess.Popen] = {}
        self.download_process_lock = threading.Lock()
        self.active_download_rows: dict[str, dict] = {}
        self.active_download_meta: dict[str, tuple[dict, dict]] = {}
        self.download_started_count = 0
        self.download_finished_count = 0
        self.episodes_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
        self.filtered_programs = list(programs)
        self.program_tree_programs: dict[str, dict] = {}
        self.displayed_program: dict | None = None
        self.displayed_episodes: list[dict] = []
        self.displayed_episode_map: dict[str, dict] = {}
        self.program_sort_column: str | None = None
        self.program_sort_reverse = False
        self.episode_sort_column: str | None = None
        self.episode_sort_reverse = False
        self.saved_episode_buttons: dict[str, ttk.Button] = {}
        self.saved_button_refresh_pending = False
        self.saved_episode_popup: tk.Toplevel | None = None
        self.tooltip_window: tk.Toplevel | None = None
        self.tooltip_label: tk.Label | None = None
        self.program_order_map = {
            self._program_key(program): index
            for index, program in enumerate(programs, 1)
        }

    def _initialize_root_window(self) -> None:
        self.root = tk.Tk()
        self.root.title("NHK ラジオ 聞き逃しブラウザ")
        self.root.geometry("1360x840")
        self.root.minsize(1040, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

    def _initialize_ui_state(self, programs: list[dict]) -> None:
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
        self.selected_cell_meta_var = tk.StringVar(value="セルをクリックすると、ここで値を選択・コピーできます。")
        self.selected_cell_value_var = tk.StringVar(value="")
        self.program_list_summary_var = tk.StringVar(value=f"{len(programs)} 番組")
        self.program_search_var = tk.StringVar()
        self.selected_program_title_var = tk.StringVar(value="番組を選択してください")
        self.selected_program_meta_var = tk.StringVar(value="左の番組一覧から選択すると、ここに番組の概要が表示されます。")
        self.selected_program_stats_var = tk.StringVar(value="エピソード一覧は未取得です。")
        self.episode_message_var = tk.StringVar(value="一覧は未取得です。")
        self.progress_text_var = tk.StringVar(value="")
        self.settings_button_var = tk.StringVar()
        self.settings_summary_var = tk.StringVar()
        self.font_size_display_var = tk.StringVar()
        self.settings_save_button_var = tk.StringVar()
        self.theme_var = tk.StringVar(value=self.current_theme)
        self.font_size_var = tk.IntVar(value=int(self.current_font_size))
        self.program_search_var.trace_add("write", self._on_program_search_change)

    def run(self) -> tuple[dict, list[dict]] | tuple[None, None]:
        self.root.mainloop()
        return self.result

    def _cancel(self):
        has_running_download = any(row["state"] == "running" for row in self.active_download_rows.values())
        if self.loading or has_running_download:
            return
        self.result = (None, None)
        self.root.destroy()


def browse_programs(programs: list[dict], output_dir: Path, *, audio_only: bool = True) -> tuple[dict, list[dict]] | tuple[None, None]:
    try:
        return EpisodeGuiBrowser(programs, output_dir, audio_only=audio_only).run()
    except tk.TclError as e:
        raise RuntimeError(str(e)) from e


# ──────────────────────────────────────────────────────
# 対話型選択 UI
# ──────────────────────────────────────────────────────

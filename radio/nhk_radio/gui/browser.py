"""Tkinter GUI browser for NHK radio programs."""

from ..core import *  # noqa: F403
from .build import _build_widgets, _build_header, _build_sidebar, _build_sidebar_header, _build_sidebar_search, _build_program_tree, _build_detail_panel, _build_hero_section, _build_episode_tree, _build_activity_panel, _build_settings_screen, _build_settings_canvas_frame, _build_settings_header, _build_theme_group, _build_font_group, _build_font_quick_actions, _build_font_preset_row, _build_font_size_scale, _build_settings_preview_section, _build_status_bar, _bind_all_events
from .styling import _resolve_mono_font_family, _resolve_ui_font_family, _theme_palette, _font_profile, _load_font_profile, _configure_theme_styles, _secondary_button_props, _configure_base_styles, _configure_treeview_styles, _configure_button_styles, _configure_settings_controls, _configure_input_styles, _configure_label_styles, _configure_live_widget_styles, _refresh_treeview_theme, _update_settings_ui, _mark_settings_dirty, _discard_unsaved_settings, _save_ui_settings_from_screen, _update_selected_cell_ui, _show_screen, _toggle_settings_screen, _persist_ui_settings, _apply_theme, _apply_font_size, _set_font_size_value, _on_font_size_scale, _adjust_font_size_scale, _on_font_size_scale_left, _on_font_size_scale_right, _on_font_size_scale_home, _on_font_size_scale_end, _decrease_font_size, _increase_font_size, _apply_font_size_preset, _reset_ui_settings
from .downloads import _update_download_row_progress, _update_fetch_button_state, _set_loading, _open_ondemand_site, _set_progress, _show_progress_window, _hide_progress_window, _on_download_jobs_inner_configure, _on_download_jobs_canvas_configure, _on_download_jobs_mousewheel, _on_settings_inner_configure, _on_settings_canvas_configure, _on_settings_mousewheel, _reflow_download_rows, _update_download_job_title_wrap, _remove_download_row, _update_download_summary, _add_download_row, _create_download_job_widgets, _finish_download_row, _cancel_download_job, _start_fetch_selected, _fetch_worker, _poll_fetch_result, _finish_fetch, _clear_cache, _start_download_selected, _download_one_worker, _monitor_download_process, _poll_download_result
from .listing import _populate_programs, _selected_program, _select_program_item, _program_key, _heading_text, _update_program_tree_headings, _update_episode_tree_headings, _toggle_program_sort, _toggle_episode_sort, _sorted_programs, _program_sort_key, _normalized_search_text, _program_search_target, _program_list_summary_text, _program_search_history_values, _update_program_search_history_values, _remember_program_search, _clear_program_selection, _on_program_search_change, _clear_program_search, _commit_program_search, _on_program_search_history_selected, _on_program_search_focus_in, _on_program_search_focus_out, _focus_program_tree_from_search, _cached_episodes_for, _update_program_overview, _on_program_select, _on_program_double_click, _tree_label, _bind_tooltip, _show_tooltip, _move_tooltip, _hide_tooltip, _tree_cell_from_event, _set_selected_tree_cell, _on_program_tree_click, _show_episodes, _sorted_episodes, _render_episode_rows, _rerender_displayed_episodes, _refresh_downloaded_column, _downloaded_cell_text, _is_saved_item, _schedule_saved_button_refresh, _refresh_saved_episode_buttons, _on_episode_tree_scroll, _on_episode_tree_yscroll, _on_episode_tree_configure, _is_saved_cell_clickable, _on_episode_tree_motion, _on_episode_tree_leave, _on_episode_tree_click, _open_saved_episode_from_item, _show_saved_episode_popup, _build_saved_episode_popup_content, _copy_path_to_clipboard, _copy_selected_cell_to_clipboard, _open_saved_folder



class EpisodeGuiBrowser:
    def __init__(self, programs: list[dict], output_dir: Path):
        if tk is None or ttk is None:
            raise RuntimeError("tkinter が利用できません")

        self.programs = programs
        self.output_dir = output_dir
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

        self.root = tk.Tk()
        self.root.title("NHK ラジオ 聞き逃しブラウザ")
        self.root.geometry("1360x840")
        self.root.minsize(1040, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
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

        self._build_widgets()
        self._populate_programs()

    def run(self) -> tuple[dict, list[dict]] | tuple[None, None]:
        self.root.mainloop()
        return self.result

    def _cancel(self):
        has_running_download = any(row["state"] == "running" for row in self.active_download_rows.values())
        if self.loading or has_running_download:
            return
        self.result = (None, None)
        self.root.destroy()


EpisodeGuiBrowser._resolve_mono_font_family = _resolve_mono_font_family
EpisodeGuiBrowser._resolve_ui_font_family = _resolve_ui_font_family
EpisodeGuiBrowser._theme_palette = _theme_palette
EpisodeGuiBrowser._font_profile = _font_profile
EpisodeGuiBrowser._load_font_profile = _load_font_profile
EpisodeGuiBrowser._configure_theme_styles = _configure_theme_styles
EpisodeGuiBrowser._secondary_button_props = _secondary_button_props
EpisodeGuiBrowser._configure_base_styles = _configure_base_styles
EpisodeGuiBrowser._configure_treeview_styles = _configure_treeview_styles
EpisodeGuiBrowser._configure_button_styles = _configure_button_styles
EpisodeGuiBrowser._configure_settings_controls = _configure_settings_controls
EpisodeGuiBrowser._configure_input_styles = _configure_input_styles
EpisodeGuiBrowser._configure_label_styles = _configure_label_styles
EpisodeGuiBrowser._configure_live_widget_styles = _configure_live_widget_styles
EpisodeGuiBrowser._refresh_treeview_theme = _refresh_treeview_theme
EpisodeGuiBrowser._update_settings_ui = _update_settings_ui
EpisodeGuiBrowser._mark_settings_dirty = _mark_settings_dirty
EpisodeGuiBrowser._discard_unsaved_settings = _discard_unsaved_settings
EpisodeGuiBrowser._save_ui_settings_from_screen = _save_ui_settings_from_screen
EpisodeGuiBrowser._update_selected_cell_ui = _update_selected_cell_ui
EpisodeGuiBrowser._show_screen = _show_screen
EpisodeGuiBrowser._toggle_settings_screen = _toggle_settings_screen
EpisodeGuiBrowser._persist_ui_settings = _persist_ui_settings
EpisodeGuiBrowser._apply_theme = _apply_theme
EpisodeGuiBrowser._apply_font_size = _apply_font_size
EpisodeGuiBrowser._set_font_size_value = _set_font_size_value
EpisodeGuiBrowser._on_font_size_scale = _on_font_size_scale
EpisodeGuiBrowser._adjust_font_size_scale = _adjust_font_size_scale
EpisodeGuiBrowser._on_font_size_scale_left = _on_font_size_scale_left
EpisodeGuiBrowser._on_font_size_scale_right = _on_font_size_scale_right
EpisodeGuiBrowser._on_font_size_scale_home = _on_font_size_scale_home
EpisodeGuiBrowser._on_font_size_scale_end = _on_font_size_scale_end
EpisodeGuiBrowser._decrease_font_size = _decrease_font_size
EpisodeGuiBrowser._increase_font_size = _increase_font_size
EpisodeGuiBrowser._apply_font_size_preset = _apply_font_size_preset
EpisodeGuiBrowser._reset_ui_settings = _reset_ui_settings
EpisodeGuiBrowser._build_widgets = _build_widgets
EpisodeGuiBrowser._build_header = _build_header
EpisodeGuiBrowser._build_sidebar = _build_sidebar
EpisodeGuiBrowser._build_sidebar_header = _build_sidebar_header
EpisodeGuiBrowser._build_sidebar_search = _build_sidebar_search
EpisodeGuiBrowser._build_program_tree = _build_program_tree
EpisodeGuiBrowser._build_detail_panel = _build_detail_panel
EpisodeGuiBrowser._build_hero_section = _build_hero_section
EpisodeGuiBrowser._build_episode_tree = _build_episode_tree
EpisodeGuiBrowser._build_activity_panel = _build_activity_panel
EpisodeGuiBrowser._build_settings_screen = _build_settings_screen
EpisodeGuiBrowser._build_settings_canvas_frame = _build_settings_canvas_frame
EpisodeGuiBrowser._build_settings_header = _build_settings_header
EpisodeGuiBrowser._build_theme_group = _build_theme_group
EpisodeGuiBrowser._build_font_group = _build_font_group
EpisodeGuiBrowser._build_font_quick_actions = _build_font_quick_actions
EpisodeGuiBrowser._build_font_preset_row = _build_font_preset_row
EpisodeGuiBrowser._build_font_size_scale = _build_font_size_scale
EpisodeGuiBrowser._build_settings_preview_section = _build_settings_preview_section
EpisodeGuiBrowser._build_status_bar = _build_status_bar
EpisodeGuiBrowser._bind_all_events = _bind_all_events

EpisodeGuiBrowser._populate_programs = _populate_programs
EpisodeGuiBrowser._selected_program = _selected_program
EpisodeGuiBrowser._select_program_item = _select_program_item
EpisodeGuiBrowser._program_key = _program_key
EpisodeGuiBrowser._heading_text = _heading_text
EpisodeGuiBrowser._update_program_tree_headings = _update_program_tree_headings
EpisodeGuiBrowser._update_episode_tree_headings = _update_episode_tree_headings
EpisodeGuiBrowser._toggle_program_sort = _toggle_program_sort
EpisodeGuiBrowser._toggle_episode_sort = _toggle_episode_sort
EpisodeGuiBrowser._sorted_programs = _sorted_programs
EpisodeGuiBrowser._program_sort_key = _program_sort_key
EpisodeGuiBrowser._normalized_search_text = _normalized_search_text
EpisodeGuiBrowser._program_search_target = _program_search_target
EpisodeGuiBrowser._program_list_summary_text = _program_list_summary_text
EpisodeGuiBrowser._program_search_history_values = _program_search_history_values
EpisodeGuiBrowser._update_program_search_history_values = _update_program_search_history_values
EpisodeGuiBrowser._remember_program_search = _remember_program_search
EpisodeGuiBrowser._clear_program_selection = _clear_program_selection
EpisodeGuiBrowser._on_program_search_change = _on_program_search_change
EpisodeGuiBrowser._clear_program_search = _clear_program_search
EpisodeGuiBrowser._commit_program_search = _commit_program_search
EpisodeGuiBrowser._on_program_search_history_selected = _on_program_search_history_selected
EpisodeGuiBrowser._on_program_search_focus_in = _on_program_search_focus_in
EpisodeGuiBrowser._on_program_search_focus_out = _on_program_search_focus_out
EpisodeGuiBrowser._focus_program_tree_from_search = _focus_program_tree_from_search
EpisodeGuiBrowser._cached_episodes_for = _cached_episodes_for
EpisodeGuiBrowser._update_program_overview = _update_program_overview
EpisodeGuiBrowser._on_program_select = _on_program_select
EpisodeGuiBrowser._on_program_double_click = _on_program_double_click
EpisodeGuiBrowser._tree_label = _tree_label
EpisodeGuiBrowser._bind_tooltip = _bind_tooltip
EpisodeGuiBrowser._show_tooltip = _show_tooltip
EpisodeGuiBrowser._move_tooltip = _move_tooltip
EpisodeGuiBrowser._hide_tooltip = _hide_tooltip
EpisodeGuiBrowser._tree_cell_from_event = _tree_cell_from_event
EpisodeGuiBrowser._set_selected_tree_cell = _set_selected_tree_cell
EpisodeGuiBrowser._on_program_tree_click = _on_program_tree_click
EpisodeGuiBrowser._show_episodes = _show_episodes
EpisodeGuiBrowser._sorted_episodes = _sorted_episodes
EpisodeGuiBrowser._render_episode_rows = _render_episode_rows
EpisodeGuiBrowser._rerender_displayed_episodes = _rerender_displayed_episodes
EpisodeGuiBrowser._refresh_downloaded_column = _refresh_downloaded_column
EpisodeGuiBrowser._downloaded_cell_text = _downloaded_cell_text
EpisodeGuiBrowser._is_saved_item = _is_saved_item
EpisodeGuiBrowser._schedule_saved_button_refresh = _schedule_saved_button_refresh
EpisodeGuiBrowser._refresh_saved_episode_buttons = _refresh_saved_episode_buttons
EpisodeGuiBrowser._on_episode_tree_scroll = _on_episode_tree_scroll
EpisodeGuiBrowser._on_episode_tree_yscroll = _on_episode_tree_yscroll
EpisodeGuiBrowser._on_episode_tree_configure = _on_episode_tree_configure
EpisodeGuiBrowser._is_saved_cell_clickable = _is_saved_cell_clickable
EpisodeGuiBrowser._on_episode_tree_motion = _on_episode_tree_motion
EpisodeGuiBrowser._on_episode_tree_leave = _on_episode_tree_leave
EpisodeGuiBrowser._on_episode_tree_click = _on_episode_tree_click
EpisodeGuiBrowser._open_saved_episode_from_item = _open_saved_episode_from_item
EpisodeGuiBrowser._show_saved_episode_popup = _show_saved_episode_popup
EpisodeGuiBrowser._build_saved_episode_popup_content = _build_saved_episode_popup_content
EpisodeGuiBrowser._copy_path_to_clipboard = _copy_path_to_clipboard
EpisodeGuiBrowser._copy_selected_cell_to_clipboard = _copy_selected_cell_to_clipboard
EpisodeGuiBrowser._open_saved_folder = _open_saved_folder
EpisodeGuiBrowser._update_download_row_progress = _update_download_row_progress
EpisodeGuiBrowser._update_fetch_button_state = _update_fetch_button_state
EpisodeGuiBrowser._set_loading = _set_loading
EpisodeGuiBrowser._open_ondemand_site = _open_ondemand_site
EpisodeGuiBrowser._set_progress = _set_progress
EpisodeGuiBrowser._show_progress_window = _show_progress_window
EpisodeGuiBrowser._hide_progress_window = _hide_progress_window
EpisodeGuiBrowser._on_download_jobs_inner_configure = _on_download_jobs_inner_configure
EpisodeGuiBrowser._on_download_jobs_canvas_configure = _on_download_jobs_canvas_configure
EpisodeGuiBrowser._on_download_jobs_mousewheel = _on_download_jobs_mousewheel
EpisodeGuiBrowser._on_settings_inner_configure = _on_settings_inner_configure
EpisodeGuiBrowser._on_settings_canvas_configure = _on_settings_canvas_configure
EpisodeGuiBrowser._on_settings_mousewheel = _on_settings_mousewheel
EpisodeGuiBrowser._reflow_download_rows = _reflow_download_rows
EpisodeGuiBrowser._update_download_job_title_wrap = _update_download_job_title_wrap
EpisodeGuiBrowser._remove_download_row = _remove_download_row
EpisodeGuiBrowser._update_download_summary = _update_download_summary
EpisodeGuiBrowser._add_download_row = _add_download_row
EpisodeGuiBrowser._create_download_job_widgets = _create_download_job_widgets
EpisodeGuiBrowser._finish_download_row = _finish_download_row
EpisodeGuiBrowser._cancel_download_job = _cancel_download_job
EpisodeGuiBrowser._start_fetch_selected = _start_fetch_selected
EpisodeGuiBrowser._fetch_worker = _fetch_worker
EpisodeGuiBrowser._poll_fetch_result = _poll_fetch_result
EpisodeGuiBrowser._finish_fetch = _finish_fetch
EpisodeGuiBrowser._clear_cache = _clear_cache
EpisodeGuiBrowser._start_download_selected = _start_download_selected
EpisodeGuiBrowser._download_one_worker = _download_one_worker
EpisodeGuiBrowser._monitor_download_process = _monitor_download_process
EpisodeGuiBrowser._poll_download_result = _poll_download_result

def browse_programs(programs: list[dict], output_dir: Path) -> tuple[dict, list[dict]] | tuple[None, None]:
    try:
        return EpisodeGuiBrowser(programs, output_dir).run()
    except tk.TclError as e:
        raise RuntimeError(str(e)) from e


# ──────────────────────────────────────────────────────
# 対話型選択 UI
# ──────────────────────────────────────────────────────

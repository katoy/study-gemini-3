"""Widget construction helpers for EpisodeGuiBrowser."""

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .protocols import GuiBrowserProtocol

from .activity_view import ActivityView
from .episode_view import EpisodeActions, EpisodeDetailView
from .logo import create_brand_logo
from .program_view import ProgramListActions, ProgramListView
from .settings_view import SettingsActions, SettingsView
from .toolkit import tk, ttk


def _set_tree_heading(tree: Any, column: str, *, text: str, anchor: str, command: Any) -> None:
    tree.heading(column, text=text, anchor=anchor, command=command)


class GuiBuildMixin:
    if TYPE_CHECKING:
        self: "GuiBrowserProtocol"

    def _build_scrollable_frame(self, parent, inner_style, padding=0):
        """Canvas + Scrollbar + 内部 Frame の共通パターンを構築して返す。"""
        canvas = tk.Canvas(parent, background=self._palette["surface"], highlightthickness=1, bd=0, relief="flat")
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = ttk.Frame(canvas, style=inner_style, padding=padding)
        inner.columnconfigure(0, weight=1)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        mousewheel_handler = self._make_canvas_mousewheel_handler(canvas)
        inner_configure_handler = self._make_canvas_inner_configure_handler(canvas)
        canvas_configure_handler = self._make_canvas_configure_handler(canvas, window_id)

        for widget in (canvas, inner):
            for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(event, mousewheel_handler)
        inner.bind("<Configure>", inner_configure_handler)
        canvas.bind("<Configure>", canvas_configure_handler)

        return canvas, scrollbar, inner, window_id

    def _build_widgets(self):
        # ウィジェット構築開始。テーマとフォントは既に初期化済み。
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        self._build_header(main)

        self.screen_container = ttk.Frame(main)
        self.screen_container.grid(row=1, column=0, sticky="nsew")
        self.screen_container.columnconfigure(0, weight=1)
        self.screen_container.rowconfigure(0, weight=1)

        self.browser_screen = ttk.Frame(self.screen_container)
        self.browser_screen.grid(row=0, column=0, sticky="nsew")
        self.browser_screen.columnconfigure(0, weight=1)
        self.browser_screen.rowconfigure(0, weight=1)

        self.browser_panes = ttk.Panedwindow(self.browser_screen, orient="horizontal")
        self.browser_panes.grid(row=0, column=0, sticky="nsew")

        self._build_sidebar()

        right_panes = ttk.Panedwindow(self.browser_panes, orient="vertical")
        self.browser_panes.add(right_panes, weight=23)

        self._build_detail_panel(right_panes)
        self._build_activity_panel(right_panes)
        self._build_settings_screen()
        self._build_status_bar(main)
        self._bind_all_events()

        self.download_button.state(["disabled"])
        self._refresh_treeview_theme()
        self._update_settings_ui()
        self._show_screen("browser", announce=False)

    def _build_header(self, main: "ttk.Frame") -> None:
        header = ttk.Frame(main, style="Card.TFrame", padding=18)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)
        header_left = ttk.Frame(header, style="CardInner.TFrame")
        header_left.grid(row=0, column=0, sticky="nw")
        header_left.columnconfigure(1, weight=1)
        self.logo_canvas = create_brand_logo(header_left, self._palette, size=60)
        self.logo_canvas.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        ttk.Label(header_left, text="NHK ラジオ 聞き逃し", style="AppTitle.TLabel").grid(row=0, column=1, sticky="w")

        header_right = ttk.Frame(header, style="CardInner.TFrame")
        header_right.grid(row=0, column=1, sticky="ne")
        header_right.columnconfigure(0, weight=1)

        header_actions = ttk.Frame(header_right, style="CardInner.TFrame")
        header_actions.grid(row=0, column=0, sticky="e")
        ttk.Button(header_actions, text="ヘルプ", command=self._show_help_dialog, style="Quiet.TButton").grid(
            row=0, column=0, padx=(0, 8)
        )
        self.clear_button = ttk.Button(
            header_actions, text="キャッシュを全削除", command=self._clear_cache, style="Quiet.TButton"
        )
        self.clear_button.grid(row=0, column=1, padx=(0, 8))
        self.settings_button = ttk.Button(
            header_actions,
            textvariable=self.settings_button_var,
            command=self._toggle_settings_screen,
            style="Toggle.TButton",
        )
        self.settings_button.grid(row=0, column=2)

    def _build_sidebar(self) -> None:
        self.program_view = ProgramListView(
            self.browser_panes,
            cast(ProgramListActions, self),
            self.program_search_var,
            self.program_genre_filter_var,
            self.program_list_summary_var,
            self.program_search_history,
            self._program_genre_filter_values,
        )
        self.ondemand_link_button = self.program_view.ondemand_link_button
        self.program_genre_filter_combo = self.program_view.genre_combo
        self.program_search_entry = self.program_view.search_entry
        self.program_tree = self.program_view.tree
        self._update_program_tree_headings()

    def _build_detail_panel(self, right_panes: "ttk.Panedwindow") -> None:
        self.episode_view = EpisodeDetailView(
            right_panes,
            cast(EpisodeActions, self),
            title_var=self.selected_program_title_var,
            meta_var=self.selected_program_meta_var,
            stats_var=self.selected_program_stats_var,
            fetch_var=self.fetch_button_var,
            message_var=self.episode_message_var,
            search_var=self.episode_search_var,
            saved_only_var=self.episode_saved_only_var,
            filter_summary_var=self.episode_filter_summary_var,
            selection_summary_var=self.episode_selection_summary_var,
        )
        self.fetch_button = self.episode_view.fetch_button
        self.download_button = self.episode_view.download_button
        self.episode_title_var = self.episode_view.episode_title_var
        self.episode_search_entry = self.episode_view.search_entry
        self.episode_saved_only_check = self.episode_view.saved_only_check
        self.error_banner_frame = self.episode_view.error_banner_frame
        self.error_banner_label = self.episode_view.error_banner_label
        self.error_retry_button = self.episode_view.error_retry_button
        self.episode_tree = self.episode_view.tree
        self.episode_scroll = self.episode_view.scrollbar
        self._update_episode_tree_headings()

    def _build_activity_panel(self, right_panes: "ttk.Panedwindow") -> None:
        self.activity_view = ActivityView(
            self.root, right_panes, self.progress_text_var, self._build_scrollable_frame, self._on_cancel_one
        )
        self.active_download_rows = self.activity_view.rows
        self.progress_label = self.activity_view.progress_label
        self.download_jobs_frame = self.activity_view.jobs_frame
        self.download_jobs_canvas = self.activity_view.canvas
        self.download_jobs_scrollbar = self.activity_view.scrollbar
        self.download_jobs_inner = self.activity_view.inner
        self.download_jobs_window = self.activity_view.window
        self.download_jobs_empty = self.activity_view.empty_label

    def _build_settings_screen(self) -> None:
        self.settings_view = SettingsView(
            self.screen_container,
            cast(SettingsActions, self),
            self._build_scrollable_frame,
            theme_var=self.theme_var,
            font_size_var=self.font_size_var,
            font_size_display_var=self.font_size_display_var,
            settings_save_button_var=self.settings_save_button_var,
            settings_summary_var=self.settings_summary_var,
        )
        self.settings_screen = self.settings_view.settings_screen
        self.settings_canvas = self.settings_view.settings_canvas
        self.settings_scrollbar = self.settings_view.settings_scrollbar
        self.settings_inner = self.settings_view.settings_inner
        self.settings_window = self.settings_view.settings_window
        self.settings_save_button = self.settings_view.settings_save_button
        self.font_size_scale = self.settings_view.font_size_scale

    def _build_status_bar(self, main: "ttk.Frame") -> None:
        status_area = ttk.Frame(main)
        status_area.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        status_area.columnconfigure(1, weight=1)
        status_area.columnconfigure(2, weight=0)

        ttk.Label(status_area, textvariable=self.status_var, anchor="w", style="Status.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="ew"
        )
        ttk.Label(
            status_area,
            text="Ctrl/Cmd+F: 番組検索  Ctrl/Cmd+L: エピソード検索  F: 一覧取得  D: DL  F1: ヘルプ",
            style="StatusHint.TLabel",
            anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.selected_cell_area = ttk.Frame(status_area)
        self.selected_cell_area.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.selected_cell_area.columnconfigure(1, weight=1)
        ttk.Label(self.selected_cell_area, textvariable=self.selected_cell_meta_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        self.selected_cell_entry = ttk.Entry(self.selected_cell_area, textvariable=self.selected_cell_value_var)
        self.selected_cell_entry.grid(row=0, column=1, sticky="ew")
        self.selected_cell_entry.state(["readonly"])
        self.copy_cell_button = ttk.Button(
            self.selected_cell_area,
            text="セル値をコピー",
            command=self._copy_selected_cell_to_clipboard,
            style="Quiet.TButton",
        )
        self.copy_cell_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.copy_cell_button.state(["disabled"])

    def _bind_all_events(self) -> None:
        self.root.bind_all("<Control-f>", self._focus_program_search, add="+")
        self.root.bind_all("<Command-f>", self._focus_program_search, add="+")
        self.root.bind_all("<Control-l>", self._focus_episode_search, add="+")
        self.root.bind_all("<Command-l>", self._focus_episode_search, add="+")
        self.root.bind_all("<F1>", self._show_help_dialog, add="+")
        self.root.bind_all("<Escape>", self._handle_escape, add="+")
        self.root.bind_all("<KeyPress>", self._handle_browser_shortcut, add="+")


__all__ = ["GuiBuildMixin"]

"""Composition of the application's Tk screens and shared chrome."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .activity_view import ActivityView
from .episode_view import EpisodeActions, EpisodeDetailView
from .logo import create_brand_logo
from .program_view import ProgramListActions, ProgramListView
from .settings_view import SettingsActions, SettingsView
from .toolkit import tk, ttk

logger = logging.getLogger(__name__)

# 表示設定ダイアログの初期サイズと最小サイズ (px)
SETTINGS_DIALOG_SIZE = "900x640"
SETTINGS_DIALOG_MIN_SIZE = (720, 480)


@dataclass(frozen=True)
class UiVars:
    status: tk.StringVar
    selected_cell_meta: tk.StringVar
    selected_cell_value: tk.StringVar
    settings_button: tk.StringVar
    program_search: tk.StringVar
    program_genre: tk.StringVar
    program_summary: tk.StringVar
    program_title: tk.StringVar
    program_meta: tk.StringVar
    program_stats: tk.StringVar
    fetch_button: tk.StringVar
    episode_message: tk.StringVar
    episode_search: tk.StringVar
    episode_saved_only: tk.BooleanVar
    episode_filter_summary: tk.StringVar
    episode_selection_summary: tk.StringVar
    progress: tk.StringVar
    theme: tk.StringVar
    font_size: tk.IntVar
    font_size_display: tk.StringVar
    settings_save_button: tk.StringVar
    settings_summary: tk.StringVar


class ShellActions(ProgramListActions, EpisodeActions, SettingsActions, Protocol):
    def _show_help_dialog(self, event=None): ...
    def _clear_cache(self): ...
    def _toggle_settings_screen(self): ...
    def _copy_selected_cell_to_clipboard(self, event=None): ...
    def _focus_program_search(self, event=None): ...
    def _focus_episode_search(self, event=None): ...
    def _handle_escape(self, event=None): ...
    def _handle_browser_shortcut(self, event): ...
    def _on_cancel_one(self, episode_key: str): ...


class AppShell:
    """Own the layout, screen switching, and global event bindings."""

    def __init__(
        self,
        root: tk.Tk,
        actions: ShellActions,
        palette: dict[str, str],
        variables: UiVars,
        search_history: list[str],
        genre_values: Callable[[], list[str]],
    ) -> None:
        self.root = root
        self.actions = actions
        self.palette = palette
        self.variables = variables
        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        self.main = main

        self._build_header()

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

        self.program_view = ProgramListView(
            root,
            self.browser_panes,
            actions,
            variables.program_search,
            variables.program_genre,
            variables.program_summary,
            search_history,
            genre_values,
        )
        right_panes = ttk.Panedwindow(self.browser_panes, orient="vertical")
        self.browser_panes.add(right_panes, weight=23)
        self.episode_view = EpisodeDetailView(
            right_panes,
            actions,
            title_var=variables.program_title,
            meta_var=variables.program_meta,
            stats_var=variables.program_stats,
            fetch_var=variables.fetch_button,
            message_var=variables.episode_message,
            search_var=variables.episode_search,
            saved_only_var=variables.episode_saved_only,
            filter_summary_var=variables.episode_filter_summary,
            selection_summary_var=variables.episode_selection_summary,
        )
        self.activity_view = ActivityView(
            root, right_panes, variables.progress, self._build_scrollable_frame, actions._on_cancel_one
        )
        # 表示設定はメイン画面を切り替えず、モーダルダイアログで開く (L3)
        self.settings_dialog = self._build_settings_dialog()
        self.settings_view = SettingsView(
            self.settings_dialog,
            actions,
            self._build_scrollable_frame,
            theme_var=variables.theme,
            font_size_var=variables.font_size,
            font_size_display_var=variables.font_size_display,
            settings_save_button_var=variables.settings_save_button,
            settings_summary_var=variables.settings_summary,
        )
        self._build_status_bar()
        self._bind_root_events()

    def _build_settings_dialog(self) -> tk.Toplevel:
        """表示設定ダイアログを非表示の状態で作る。"""
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.title("表示設定")
        dialog.transient(self.root)
        dialog.geometry(SETTINGS_DIALOG_SIZE)
        dialog.minsize(*SETTINGS_DIALOG_MIN_SIZE)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        # 閉じるボタンも「番組一覧に戻る」と同じ扱いにし、未保存の確認を通す
        dialog.protocol("WM_DELETE_WINDOW", self.actions._toggle_settings_screen)
        return dialog

    def _center_settings_dialog(self) -> None:
        """表示設定ダイアログをメインウィンドウの中央に置く。"""
        dialog = self.settings_dialog
        width, height = (int(v) for v in SETTINGS_DIALOG_SIZE.split("x"))
        x = self.root.winfo_rootx() + max((self.root.winfo_width() - width) // 2, 0)
        y = self.root.winfo_rooty() + max((self.root.winfo_height() - height) // 2, 0)
        dialog.geometry(f"+{x}+{y}")

    def show_screen(self, screen_name: str) -> None:
        dialog = self.settings_dialog
        if screen_name == "settings":
            self._center_settings_dialog()
            dialog.deiconify()
            dialog.lift()
            dialog.focus_set()
            try:
                # 設定中はメイン画面を操作できないようにする
                dialog.grab_set()
            except tk.TclError as e:
                # 表示前などで grab できない場合はモードレスのまま開く
                logger.debug("表示設定ダイアログの grab に失敗: %s", e)
        else:
            dialog.grab_release()
            dialog.withdraw()

    def _build_scrollable_frame(self, parent, inner_style, padding=0):
        canvas = tk.Canvas(parent, background=self.palette["surface"], highlightthickness=1, bd=0, relief="flat")
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = ttk.Frame(canvas, style=inner_style, padding=padding)
        inner.columnconfigure(0, weight=1)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_mousewheel(event):
            if event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")

        for widget in (canvas, inner):
            for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(event, on_mousewheel)
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfig(window_id, width=event.width))
        return canvas, scrollbar, inner, window_id

    def _build_header(self) -> None:
        header = ttk.Frame(self.main, style="Card.TFrame", padding=18)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)
        header_left = ttk.Frame(header, style="CardInner.TFrame")
        header_left.grid(row=0, column=0, sticky="nw")
        header_left.columnconfigure(1, weight=1)
        self.logo_canvas = create_brand_logo(header_left, self.palette, size=60)
        self.logo_canvas.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        ttk.Label(header_left, text="NHK ラジオ 聞き逃し", style="AppTitle.TLabel").grid(row=0, column=1, sticky="w")
        header_right = ttk.Frame(header, style="CardInner.TFrame")
        header_right.grid(row=0, column=1, sticky="ne")
        header_right.columnconfigure(0, weight=1)
        header_actions = ttk.Frame(header_right, style="CardInner.TFrame")
        header_actions.grid(row=0, column=0, sticky="e")
        ttk.Button(
            header_actions, text="ヘルプ", command=self.actions._show_help_dialog, style="Quiet.TButton"
        ).grid(row=0, column=0, padx=(0, 8))
        self.clear_button = ttk.Button(
            header_actions, text="キャッシュを全削除", command=self.actions._clear_cache, style="Quiet.TButton"
        )
        self.clear_button.grid(row=0, column=1, padx=(0, 8))
        self.settings_button = ttk.Button(
            header_actions,
            textvariable=self.variables.settings_button,
            command=self.actions._toggle_settings_screen,
            style="Toggle.TButton",
        )
        self.settings_button.grid(row=0, column=2)

    def _build_status_bar(self) -> None:
        status_area = ttk.Frame(self.main)
        status_area.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        status_area.columnconfigure(1, weight=1)
        status_area.columnconfigure(2, weight=0)
        ttk.Label(status_area, textvariable=self.variables.status, anchor="w", style="Status.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="ew"
        )
        ttk.Label(
            status_area,
            text="Ctrl/Cmd+F: 番組検索  Ctrl/Cmd+L: エピソード検索  F: 一覧取得  D: DL  F1 / ?: ヘルプ",
            style="StatusHint.TLabel",
            anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.selected_cell_area = ttk.Frame(status_area)
        self.selected_cell_area.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.selected_cell_area.columnconfigure(1, weight=1)
        ttk.Label(
            self.selected_cell_area, textvariable=self.variables.selected_cell_meta, style="Status.TLabel"
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.selected_cell_entry = ttk.Entry(
            self.selected_cell_area, textvariable=self.variables.selected_cell_value
        )
        self.selected_cell_entry.grid(row=0, column=1, sticky="ew")
        self.selected_cell_entry.state(["readonly"])
        self.copy_cell_button = ttk.Button(
            self.selected_cell_area,
            text="セル値をコピー",
            command=self.actions._copy_selected_cell_to_clipboard,
            style="Quiet.TButton",
        )
        self.copy_cell_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.copy_cell_button.state(["disabled"])

    def _bind_root_events(self) -> None:
        for sequence, callback in (
            ("<Control-f>", self.actions._focus_program_search),
            ("<Command-f>", self.actions._focus_program_search),
            ("<Control-l>", self.actions._focus_episode_search),
            ("<Command-l>", self.actions._focus_episode_search),
            ("<F1>", self.actions._show_help_dialog),
            ("<Escape>", self.actions._handle_escape),
            ("<KeyPress>", self.actions._handle_browser_shortcut),
        ):
            self.root.bind_all(sequence, callback, add="+")

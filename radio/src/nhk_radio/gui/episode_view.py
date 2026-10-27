"""Episode detail widgets and local interactions."""

from typing import Protocol

from .toolkit import tk, ttk


class EpisodeActions(Protocol):
    def _start_fetch_selected(self, event=None): ...
    def _start_download_selected(self, event=None): ...
    def _clear_episode_search(self, event=None): ...
    def _hide_error_banner(self): ...
    def _toggle_episode_sort(self, column: str): ...
    def _update_episode_tree_headings(self): ...
    def _on_episode_tree_scroll(self, *args): ...
    def _on_episode_tree_yscroll(self, *args): ...
    def _on_episode_tree_click(self, event): ...
    def _on_episode_tree_motion(self, event): ...
    def _on_episode_tree_leave(self, event): ...
    def _on_episode_selection_change(self, event=None): ...
    def _copy_selected_cell_to_clipboard(self, event=None): ...
    def _on_episode_tree_right_click(self, event): ...


class EpisodeDetailView:
    def __init__(
        self,
        parent: ttk.Panedwindow,
        actions: EpisodeActions,
        *,
        title_var: tk.StringVar,
        meta_var: tk.StringVar,
        stats_var: tk.StringVar,
        fetch_var: tk.StringVar,
        message_var: tk.StringVar,
        search_var: tk.StringVar,
        saved_only_var: tk.BooleanVar,
        filter_summary_var: tk.StringVar,
        selection_summary_var: tk.StringVar,
    ) -> None:
        detail = ttk.Frame(parent, style="Card.TFrame", padding=18, width=860, height=300)
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(3, weight=1)

        hero = ttk.Frame(detail, style="Hero.TFrame", padding=16)
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)
        ttk.Label(hero, textvariable=title_var, style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hero, textvariable=meta_var, style="HeroMeta.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Label(hero, textvariable=stats_var, style="HeroStats.TLabel").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        hero_actions = ttk.Frame(hero, style="HeroInner.TFrame")
        hero_actions.grid(row=0, column=1, rowspan=3, sticky="ne", padx=(18, 0))
        self.fetch_button = ttk.Button(
            hero_actions, textvariable=fetch_var, command=actions._start_fetch_selected, style="Quiet.TButton"
        )
        self.fetch_button.grid(row=0, column=0, sticky="e")
        self.download_button = ttk.Button(
            hero_actions,
            text="選択エピソードをダウンロード",
            command=actions._start_download_selected,
            style="Accent.TButton",
        )
        self.download_button.grid(row=1, column=0, sticky="e", pady=(8, 0))

        self.episode_title_var = tk.StringVar(value="エピソード一覧")
        section = ttk.Frame(detail, style="CardInner.TFrame")
        section.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        section.columnconfigure(0, weight=1)
        ttk.Label(section, textvariable=self.episode_title_var, style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(section, textvariable=message_var, style="CardMeta.TLabel").grid(row=0, column=1, sticky="e")
        tools = ttk.Frame(section, style="CardInner.TFrame")
        tools.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        tools.columnconfigure(1, weight=1)
        ttk.Label(tools, text="絞り込み", style="CardMeta.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.search_entry = ttk.Entry(tools, textvariable=search_var)
        self.search_entry.grid(row=0, column=1, sticky="ew")
        self.search_entry.bind("<Escape>", actions._clear_episode_search)
        ttk.Button(tools, text="クリア", command=actions._clear_episode_search, style="Quiet.TButton").grid(
            row=0, column=2, padx=(8, 0)
        )
        self.saved_only_check = ttk.Checkbutton(
            tools, text="保存済みのみ", variable=saved_only_var, style="Filter.TCheckbutton"
        )
        self.saved_only_check.grid(row=0, column=3, padx=(12, 0))
        filter_summary = ttk.Frame(section, style="CardInner.TFrame")
        filter_summary.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        filter_summary.columnconfigure(0, weight=1)
        ttk.Label(filter_summary, textvariable=filter_summary_var, style="CardMeta.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(filter_summary, textvariable=selection_summary_var, style="CardMeta.TLabel").grid(
            row=0, column=1, sticky="e"
        )

        self.error_banner_frame = ttk.Frame(detail, style="ErrorBanner.TFrame")
        self.error_banner_frame.grid(row=2, column=0, sticky="ew", pady=(16, 8))
        self.error_banner_frame.columnconfigure(0, weight=1)
        self.error_banner_label = ttk.Label(self.error_banner_frame, text="", style="ErrorBanner.TLabel")
        self.error_banner_label.grid(row=0, column=0, sticky="w", padx=(10, 8), pady=6)
        self.error_retry_button = ttk.Button(
            self.error_banner_frame, text="↺ 再試行", style="Quiet.TButton", command=actions._start_fetch_selected
        )
        self.error_retry_button.grid(row=0, column=1, padx=(0, 4), pady=4)
        ttk.Button(
            self.error_banner_frame, text="✕", style="Quiet.TButton", command=actions._hide_error_banner
        ).grid(row=0, column=2, padx=(0, 8), pady=4)
        self.error_banner_frame.grid_remove()

        self.tree = ttk.Treeview(
            detail, columns=("saved", "date", "duration", "title"), show="headings", selectmode="extended"
        )
        for column, text, anchor in (
            ("saved", "DL", "center"),
            ("date", "放送日時", "w"),
            ("duration", "長さ", "e"),
            ("title", "タイトル", "w"),
        ):
            self.tree.heading(column, text=text, anchor=anchor, command=lambda col=column: actions._toggle_episode_sort(col))
        self.tree.column("saved", width=60, anchor="center", stretch=False)
        self.tree.column("date", width=190, anchor="w", stretch=False)
        self.tree.column("duration", width=100, anchor="e", stretch=False)
        self.tree.column("title", width=560, anchor="w")
        self.scrollbar = ttk.Scrollbar(detail, orient="vertical", command=actions._on_episode_tree_scroll)
        self.tree.configure(yscrollcommand=actions._on_episode_tree_yscroll)
        self.tree.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        self.scrollbar.grid(row=3, column=1, sticky="ns", pady=(8, 0))
        parent.add(detail, weight=1)
        self.frame = detail

        for sequence, callback in (
            ("<ButtonRelease-1>", actions._on_episode_tree_click),
            ("<Motion>", actions._on_episode_tree_motion),
            ("<Leave>", actions._on_episode_tree_leave),
            ("<Double-1>", actions._start_download_selected),
            ("<Return>", actions._start_download_selected),
            ("<<TreeviewSelect>>", actions._on_episode_selection_change),
            ("<Control-c>", actions._copy_selected_cell_to_clipboard),
            ("<Command-c>", actions._copy_selected_cell_to_clipboard),
            ("<Button-2>", actions._on_episode_tree_right_click),
            ("<Button-3>", actions._on_episode_tree_right_click),
        ):
            self.tree.bind(sequence, callback)

    def show_error(self, message: str) -> None:
        self.error_banner_label.config(text=message)
        self.error_banner_frame.grid()

    def hide_error(self) -> None:
        self.error_banner_frame.grid_remove()

"""Widget construction helpers for EpisodeGuiBrowser."""

from .toolkit import tk, ttk


class GuiBuildMixin:
    def _build_widgets(self):
        self._load_font_profile()
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self._palette = self._theme_palette(self.current_theme)
        self._configure_theme_styles()

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
        ttk.Label(header, text="NHK ラジオ 聞き逃し", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")

        header_right = ttk.Frame(header, style="CardInner.TFrame")
        header_right.grid(row=0, column=1, sticky="ne")
        header_right.columnconfigure(0, weight=1)

        header_actions = ttk.Frame(header_right, style="CardInner.TFrame")
        header_actions.grid(row=0, column=0, sticky="e")
        self.clear_button = ttk.Button(header_actions, text="キャッシュを全削除", command=self._clear_cache, style="Quiet.TButton")
        self.clear_button.grid(row=0, column=0, padx=(0, 8))
        self.settings_button = ttk.Button(
            header_actions,
            textvariable=self.settings_button_var,
            command=self._toggle_settings_screen,
            style="Toggle.TButton",
        )
        self.settings_button.grid(row=0, column=1)
    def _build_sidebar(self) -> None:
        sidebar = ttk.Frame(self.browser_panes, style="Sidebar.TFrame", padding=16, width=430)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)
        self._build_sidebar_header(sidebar)
        self._build_sidebar_search(sidebar)
        self._build_program_tree(sidebar)
        self.browser_panes.add(sidebar, weight=11)
    def _build_sidebar_header(self, sidebar: "ttk.Frame") -> None:
        sidebar_header = ttk.Frame(sidebar, style="SidebarInner.TFrame")
        sidebar_header.grid(row=0, column=0, sticky="ew")
        sidebar_header.columnconfigure(0, weight=1)
        ttk.Label(sidebar_header, text="番組一覧", style="CardTitleAlt.TLabel").grid(row=0, column=0, sticky="w")
        self.ondemand_link_button = ttk.Button(
            sidebar_header,
            text="らじる★らじる",
            command=self._open_ondemand_site,
            style="RajiruLink.TButton",
            cursor="hand2",
        )
        self.ondemand_link_button.grid(row=0, column=1, sticky="e")
        self._bind_tooltip(self.ondemand_link_button, "聞き逃し検索の公式サイト")
    def _build_sidebar_search(self, sidebar: "ttk.Frame") -> None:
        sidebar_actions = ttk.Frame(sidebar, style="SidebarInner.TFrame")
        sidebar_actions.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        sidebar_actions.columnconfigure(0, weight=1)
        ttk.Label(
            sidebar_actions,
            text="Enter・ダブルクリック・右側の「一覧を取得」でエピソード一覧を更新",
            style="CardMetaAlt.TLabel",
            wraplength=360,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        search_row = ttk.Frame(sidebar_actions, style="SidebarInner.TFrame")
        search_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="検索", style="CardMetaAlt.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.program_search_entry = ttk.Combobox(
            search_row,
            textvariable=self.program_search_var,
            values=self.program_search_history,
            style="Search.TCombobox",
        )
        self.program_search_entry.grid(row=0, column=1, sticky="ew")
        self.program_search_entry.bind("<Escape>", self._clear_program_search)
        self.program_search_entry.bind("<Down>", self._focus_program_tree_from_search)
        self.program_search_entry.bind("<Return>", self._commit_program_search)
        self.program_search_entry.bind("<<ComboboxSelected>>", self._on_program_search_history_selected)
        self.program_search_entry.bind("<FocusIn>", self._on_program_search_focus_in)
        self.program_search_entry.bind("<FocusOut>", self._on_program_search_focus_out)
        ttk.Button(search_row, text="クリア", command=self._clear_program_search, style="Quiet.TButton").grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Label(sidebar_actions, textvariable=self.program_list_summary_var, style="CardMetaAlt.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )
    def _build_program_tree(self, sidebar: "ttk.Frame") -> None:
        self.program_tree = ttk.Treeview(
            sidebar,
            columns=("no", "date", "title"),
            show="headings",
            selectmode="browse",
        )
        self.program_tree.heading("no", text="No.", anchor="e", command=lambda: self._toggle_program_sort("no"))
        self.program_tree.heading("date", text="更新日", anchor="w", command=lambda: self._toggle_program_sort("date"))
        self.program_tree.heading("title", text="番組", anchor="w", command=lambda: self._toggle_program_sort("title"))
        self.program_tree.column("no", width=60, anchor="e", stretch=False)
        self.program_tree.column("date", width=140, anchor="w", stretch=False)
        self.program_tree.column("title", width=360, anchor="w")
        self._update_program_tree_headings()
        program_scroll = ttk.Scrollbar(sidebar, orient="vertical", command=self.program_tree.yview)
        self.program_tree.configure(yscrollcommand=program_scroll.set)
        self.program_tree.grid(row=2, column=0, sticky="nsew")
        program_scroll.grid(row=2, column=1, sticky="ns")
    def _build_detail_panel(self, right_panes: "ttk.Panedwindow") -> None:
        detail = ttk.Frame(right_panes, style="Card.TFrame", padding=18, width=860, height=520)
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(2, weight=1)
        self._build_hero_section(detail)
        self._build_episode_tree(detail)
        right_panes.add(detail, weight=5)
    def _build_hero_section(self, detail: "ttk.Frame") -> None:
        hero = ttk.Frame(detail, style="Hero.TFrame", padding=16)
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)
        ttk.Label(hero, textvariable=self.selected_program_title_var, style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(hero, textvariable=self.selected_program_meta_var, style="HeroMeta.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Label(hero, textvariable=self.selected_program_stats_var, style="HeroStats.TLabel").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        hero_actions = ttk.Frame(hero, style="HeroInner.TFrame")
        hero_actions.grid(row=0, column=1, rowspan=3, sticky="ne", padx=(18, 0))
        self.fetch_button = ttk.Button(
            hero_actions,
            text="一覧を取得",
            command=self._start_fetch_selected,
            style="Quiet.TButton",
        )
        self.fetch_button.grid(row=0, column=0, sticky="e")
        self.download_button = ttk.Button(
            hero_actions,
            text="選択エピソードをダウンロード",
            command=self._start_download_selected,
            style="Accent.TButton",
        )
        self.download_button.grid(row=1, column=0, sticky="e", pady=(8, 0))
    def _build_episode_tree(self, detail: "ttk.Frame") -> None:
        self.episode_title_var = tk.StringVar(value="エピソード一覧")
        section = ttk.Frame(detail, style="CardInner.TFrame")
        section.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        section.columnconfigure(0, weight=1)
        ttk.Label(section, textvariable=self.episode_title_var, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(section, textvariable=self.episode_message_var, style="CardMeta.TLabel").grid(row=0, column=1, sticky="e")
        self.episode_tree = ttk.Treeview(
            detail,
            columns=("saved", "date", "duration", "title"),
            show="headings",
            selectmode="extended",
        )
        self.episode_tree.heading("saved", text="DL", anchor="center", command=lambda: self._toggle_episode_sort("saved"))
        self.episode_tree.heading("date", text="放送日時", anchor="w", command=lambda: self._toggle_episode_sort("date"))
        self.episode_tree.heading("duration", text="長さ", anchor="e", command=lambda: self._toggle_episode_sort("duration"))
        self.episode_tree.heading("title", text="タイトル", anchor="w", command=lambda: self._toggle_episode_sort("title"))
        self.episode_tree.column("saved", width=82, anchor="center", stretch=False)
        self.episode_tree.column("date", width=190, anchor="w", stretch=False)
        self.episode_tree.column("duration", width=100, anchor="e", stretch=False)
        self.episode_tree.column("title", width=560, anchor="w")
        self._update_episode_tree_headings()
        self.episode_scroll = ttk.Scrollbar(detail, orient="vertical", command=self._on_episode_tree_scroll)
        self.episode_tree.configure(yscrollcommand=self._on_episode_tree_yscroll)
        self.episode_tree.grid(row=2, column=0, sticky="nsew")
        self.episode_scroll.grid(row=2, column=1, sticky="ns")
    def _build_activity_panel(self, right_panes: "ttk.Panedwindow") -> None:
        activity = ttk.Frame(right_panes, style="Card.TFrame", padding=14, height=180)
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(2, weight=1)
        ttk.Label(activity, text="ダウンロード状況", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.progress_label = ttk.Label(activity, textvariable=self.progress_text_var, anchor="w", style="CardMeta.TLabel")
        self.progress_label.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        self.download_jobs_frame = ttk.LabelFrame(activity, text="ジョブ一覧", padding=10)
        self.download_jobs_frame.grid(row=2, column=0, sticky="nsew")
        self.download_jobs_frame.columnconfigure(0, weight=1)
        self.download_jobs_frame.rowconfigure(0, weight=1)
        self.download_jobs_canvas = tk.Canvas(
            self.download_jobs_frame,
            background=self._palette["surface"],
            highlightthickness=1,
            bd=0,
            relief="flat",
        )
        self.download_jobs_canvas.grid(row=0, column=0, sticky="nsew")
        self.download_jobs_scrollbar = ttk.Scrollbar(
            self.download_jobs_frame,
            orient="vertical",
            command=self.download_jobs_canvas.yview,
        )
        self.download_jobs_scrollbar.grid(row=0, column=1, sticky="ns")
        self.download_jobs_canvas.configure(yscrollcommand=self.download_jobs_scrollbar.set)
        self.download_jobs_inner = ttk.Frame(self.download_jobs_canvas, style="CardInner.TFrame")
        self.download_jobs_window = self.download_jobs_canvas.create_window((0, 0), window=self.download_jobs_inner, anchor="nw")
        self.download_jobs_inner.columnconfigure(0, weight=1)
        self.download_jobs_inner.bind("<Configure>", self._on_download_jobs_inner_configure)
        self.download_jobs_canvas.bind("<Configure>", self._on_download_jobs_canvas_configure)
        self.download_jobs_canvas.bind("<MouseWheel>", self._on_download_jobs_mousewheel)
        self.download_jobs_canvas.bind("<Button-4>", self._on_download_jobs_mousewheel)
        self.download_jobs_canvas.bind("<Button-5>", self._on_download_jobs_mousewheel)
        self.download_jobs_inner.bind("<MouseWheel>", self._on_download_jobs_mousewheel)
        self.download_jobs_inner.bind("<Button-4>", self._on_download_jobs_mousewheel)
        self.download_jobs_inner.bind("<Button-5>", self._on_download_jobs_mousewheel)
        self.download_jobs_empty = ttk.Label(self.download_jobs_inner, text="実行中のダウンロードはありません。", style="CardMeta.TLabel")
        self.download_jobs_empty.grid(row=0, column=0, sticky="w")
        right_panes.add(activity, weight=2)
    def _build_settings_screen(self) -> None:
        self._build_settings_canvas_frame()
        self._build_settings_header()
        settings_body = ttk.Frame(self.settings_inner, style="CardInner.TFrame")
        settings_body.grid(row=2, column=0, sticky="nsew")
        settings_body.columnconfigure(0, weight=1)
        settings_body.columnconfigure(1, weight=1)
        self._build_theme_group(settings_body)
        self._build_font_group(settings_body)
        self._build_settings_preview_section()
    def _build_settings_canvas_frame(self) -> None:
        self.settings_screen = ttk.Frame(self.screen_container, style="Card.TFrame")
        self.settings_screen.grid(row=0, column=0, sticky="nsew")
        self.settings_screen.columnconfigure(0, weight=1)
        self.settings_screen.rowconfigure(0, weight=1)
        self.settings_canvas = tk.Canvas(
            self.settings_screen,
            background=self._palette["surface"],
            highlightthickness=1,
            bd=0,
            relief="flat",
        )
        self.settings_canvas.grid(row=0, column=0, sticky="nsew")
        self.settings_scrollbar = ttk.Scrollbar(
            self.settings_screen,
            orient="vertical",
            command=self.settings_canvas.yview,
        )
        self.settings_scrollbar.grid(row=0, column=1, sticky="ns")
        self.settings_canvas.configure(yscrollcommand=self.settings_scrollbar.set)
        self.settings_inner = ttk.Frame(self.settings_canvas, style="Card.TFrame", padding=24)
        self.settings_window = self.settings_canvas.create_window((0, 0), window=self.settings_inner, anchor="nw")
        self.settings_inner.columnconfigure(0, weight=1)
        self.settings_inner.bind("<Configure>", self._on_settings_inner_configure)
        self.settings_canvas.bind("<Configure>", self._on_settings_canvas_configure)
        self.settings_canvas.bind("<MouseWheel>", self._on_settings_mousewheel)
        self.settings_canvas.bind("<Button-4>", self._on_settings_mousewheel)
        self.settings_canvas.bind("<Button-5>", self._on_settings_mousewheel)
        self.settings_inner.bind("<MouseWheel>", self._on_settings_mousewheel)
        self.settings_inner.bind("<Button-4>", self._on_settings_mousewheel)
        self.settings_inner.bind("<Button-5>", self._on_settings_mousewheel)
    def _build_settings_header(self) -> None:
        settings_header = ttk.Frame(self.settings_inner, style="CardInner.TFrame")
        settings_header.grid(row=0, column=0, sticky="ew")
        settings_header.columnconfigure(0, weight=1)
        ttk.Label(settings_header, text="表示設定", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        settings_actions = ttk.Frame(settings_header, style="CardInner.TFrame")
        settings_actions.grid(row=0, column=1, sticky="e")
        ttk.Button(settings_actions, text="規定値にリセット", command=self._reset_ui_settings, style="Quiet.TButton").grid(
            row=0, column=0, padx=(0, 8)
        )
        self.settings_save_button = ttk.Button(
            settings_actions,
            textvariable=self.settings_save_button_var,
            command=self._save_ui_settings_from_screen,
            style="Accent.TButton",
        )
        self.settings_save_button.grid(row=0, column=1)
        ttk.Label(
            self.settings_inner,
            text="テーマと文字サイズはこの画面でまとめて変更できます。選択内容はその場で反映され、保存すると次回起動時にも引き継がれます。",
            style="AppSub.TLabel",
            wraplength=880,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 18))
    def _build_theme_group(self, settings_body: "ttk.Frame") -> None:
        theme_group = ttk.LabelFrame(settings_body, text="テーマ", padding=16)
        theme_group.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        theme_group.columnconfigure(0, weight=1)
        ttk.Label(theme_group, text="画面全体の配色を切り替えます。", style="CardMeta.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        ttk.Radiobutton(
            theme_group,
            text="ライト",
            value="light",
            variable=self.theme_var,
            command=lambda: self._apply_theme(self.theme_var.get()),
            style="Settings.TRadiobutton",
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Radiobutton(
            theme_group,
            text="ダーク",
            value="dark",
            variable=self.theme_var,
            command=lambda: self._apply_theme(self.theme_var.get()),
            style="Settings.TRadiobutton",
        ).grid(row=2, column=0, sticky="w")
    def _build_font_group(self, settings_body: "ttk.Frame") -> None:
        font_group = ttk.LabelFrame(settings_body, text="文字サイズ", padding=16)
        font_group.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        font_group.columnconfigure(0, weight=1)
        ttk.Label(font_group, text="一覧、カード、設定ラベルの文字サイズを変更します。", style="CardMeta.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        self._build_font_quick_actions(font_group)
        self._build_font_preset_row(font_group)
        self._build_font_size_scale(font_group)
        ttk.Label(
            font_group,
            text="細かい調整はスライダー、すばやい変更はボタンで行えます。左右キーでも 1pt ずつ調整できます。",
            style="CardMeta.TLabel",
            wraplength=380,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(8, 0))
        font_preview = ttk.Frame(font_group, style="FontPreview.TFrame", padding=14)
        font_preview.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        font_preview.columnconfigure(0, weight=1)
        ttk.Label(font_preview, text="プレビュー", style="FontPreviewTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            font_preview,
            text="番組一覧、詳細カード、設定ラベルにこのサイズがそのまま反映されます。",
            style="FontPreviewBody.TLabel",
            wraplength=380,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
    def _build_font_quick_actions(self, font_group: "ttk.LabelFrame") -> None:
        font_quick_actions = ttk.Frame(font_group, style="CardInner.TFrame")
        font_quick_actions.grid(row=1, column=0, sticky="ew")
        font_quick_actions.columnconfigure(1, weight=1)
        ttk.Button(font_quick_actions, text="小さく", command=self._decrease_font_size, style="FontStep.TButton").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(font_quick_actions, textvariable=self.font_size_display_var, style="SettingsValue.TLabel").grid(
            row=0, column=1
        )
        ttk.Button(font_quick_actions, text="大きく", command=self._increase_font_size, style="FontStep.TButton").grid(
            row=0, column=2, sticky="e"
        )
    def _build_font_preset_row(self, font_group: "ttk.LabelFrame") -> None:
        preset_row = ttk.Frame(font_group, style="CardInner.TFrame")
        preset_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(preset_row, text="よく使うサイズ", style="CardMeta.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        for index, preset in enumerate((9, 11, 13, 15), start=1):
            ttk.Button(
                preset_row,
                text=f"{preset} pt",
                command=lambda value=preset: self._apply_font_size_preset(value),
                style=f"FontPreset{preset}.TButton",
                width=5,
            ).grid(row=0, column=index, padx=(0, 8))
    def _build_font_size_scale(self, font_group: "ttk.LabelFrame") -> None:
        font_control = ttk.Frame(font_group, style="CardInner.TFrame")
        font_control.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        font_control.columnconfigure(1, weight=1)
        ttk.Label(font_control, text="小", style="CardMeta.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.font_size_scale = ttk.Scale(
            font_control,
            from_=9,
            to=18,
            variable=self.font_size_var,
            command=self._on_font_size_scale,
            style="Settings.Horizontal.TScale",
            takefocus=True,
        )
        self.font_size_scale.grid(row=0, column=1, sticky="ew")
        self.font_size_scale.bind("<Left>", self._on_font_size_scale_left)
        self.font_size_scale.bind("<Right>", self._on_font_size_scale_right)
        self.font_size_scale.bind("<Home>", self._on_font_size_scale_home)
        self.font_size_scale.bind("<End>", self._on_font_size_scale_end)
        ttk.Label(font_control, text="大", style="CardMeta.TLabel").grid(row=0, column=2, sticky="e", padx=(12, 0))
    def _build_settings_preview_section(self) -> None:
        preview_group = ttk.LabelFrame(self.settings_inner, text="プレビュー", padding=16)
        preview_group.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        preview_group.columnconfigure(0, weight=1)
        ttk.Label(preview_group, textvariable=self.settings_summary_var, style="SettingsValue.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            preview_group,
            text="ラジオ英会話 / 4月13日(月) 06:45 / エピソード 12 件 / 保存済み 3 件",
            style="SettingsPreview.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
    def _build_status_bar(self, main: "ttk.Frame") -> None:
        status_area = ttk.Frame(main)
        status_area.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        status_area.columnconfigure(1, weight=1)

        ttk.Label(status_area, textvariable=self.status_var, anchor="w", style="Status.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="ew"
        )
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
        self.program_tree.bind("<<TreeviewSelect>>", self._on_program_select)
        self.program_tree.bind("<ButtonRelease-1>", self._on_program_tree_click)
        self.program_tree.bind("<Double-1>", self._on_program_double_click)
        self.program_tree.bind("<Return>", self._start_fetch_selected)
        self.program_tree.bind("<Control-c>", self._copy_selected_cell_to_clipboard)
        self.program_tree.bind("<Command-c>", self._copy_selected_cell_to_clipboard)
        self.episode_tree.bind("<ButtonRelease-1>", self._on_episode_tree_click)
        self.episode_tree.bind("<Motion>", self._on_episode_tree_motion)
        self.episode_tree.bind("<Leave>", self._on_episode_tree_leave)
        self.episode_tree.bind("<Configure>", self._on_episode_tree_configure)
        self.episode_tree.bind("<Double-1>", self._start_download_selected)
        self.episode_tree.bind("<Return>", self._start_download_selected)
        self.episode_tree.bind("<Control-c>", self._copy_selected_cell_to_clipboard)
        self.episode_tree.bind("<Command-c>", self._copy_selected_cell_to_clipboard)

__all__ = ['GuiBuildMixin']

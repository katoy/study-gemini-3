"""Display settings screen widgets."""

from collections.abc import Callable
from typing import Any, Protocol

from .toolkit import tk, ttk


class SettingsActions(Protocol):
    def _toggle_settings_screen(self): ...
    def _reset_ui_settings(self): ...
    def _save_ui_settings_from_screen(self): ...
    def _apply_theme(self, theme_name: str): ...
    def _decrease_font_size(self): ...
    def _increase_font_size(self): ...
    def _apply_font_size_preset(self, size_pt: int): ...
    def _on_font_size_scale(self, value): ...
    def _on_font_size_scale_left(self, event): ...
    def _on_font_size_scale_right(self, event): ...
    def _on_font_size_scale_home(self, event): ...
    def _on_font_size_scale_end(self, event): ...


class SettingsView:
    def __init__(
        self,
        screen_container: tk.Misc,
        actions: SettingsActions,
        create_scrollable_frame: Callable[..., tuple[Any, Any, Any, Any]],
        *,
        theme_var: tk.StringVar,
        font_size_var: tk.IntVar,
        font_size_display_var: tk.StringVar,
        settings_save_button_var: tk.StringVar,
        settings_summary_var: tk.StringVar,
    ) -> None:
        self.screen_container = screen_container
        self.actions = actions
        self._build_scrollable_frame = create_scrollable_frame
        self.theme_var = theme_var
        self.font_size_var = font_size_var
        self.font_size_display_var = font_size_display_var
        self.settings_save_button_var = settings_save_button_var
        self.settings_summary_var = settings_summary_var
        self._build_settings_screen()

    def update(self, theme: str, font_size: int, dirty: bool) -> None:
        theme_label = "ダーク" if theme == "dark" else "ライト"
        self.settings_summary_var.set(f"{theme_label} / 文字 {font_size}pt")
        self.font_size_display_var.set(f"{font_size} pt")
        self.theme_var.set(theme)
        self.font_size_var.set(font_size)
        self.settings_save_button_var.set("保存" if dirty else "保存済み")
        self.settings_save_button.state(["!disabled"] if dirty else ["disabled"])

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
        self.settings_canvas, self.settings_scrollbar, self.settings_inner, self.settings_window = self._build_scrollable_frame(
            self.settings_screen, "Card.TFrame", padding=24
        )

    def _build_settings_header(self) -> None:
        settings_header = ttk.Frame(self.settings_inner, style="CardInner.TFrame")
        settings_header.grid(row=0, column=0, sticky="ew")
        settings_header.columnconfigure(0, weight=1)
        ttk.Label(settings_header, text="表示設定", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        settings_actions = ttk.Frame(settings_header, style="CardInner.TFrame")
        settings_actions.grid(row=0, column=1, sticky="e")
        ttk.Button(
            settings_actions, text="規定値にリセット", command=self.actions._reset_ui_settings, style="Quiet.TButton"
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            settings_actions, text="閉じる", command=self.actions._toggle_settings_screen, style="Quiet.TButton"
        ).grid(row=0, column=2, padx=(8, 0))
        self.settings_save_button = ttk.Button(
            settings_actions,
            textvariable=self.settings_save_button_var,
            command=self.actions._save_ui_settings_from_screen,
            style="Accent.TButton",
        )
        self.settings_save_button.grid(row=0, column=1)
        ttk.Label(
            self.settings_inner,
            text="テーマと文字サイズをまとめて変更できます。選択内容はその場で反映され、保存すると次回起動時にも引き継がれます。",
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
            command=lambda: self.actions._apply_theme(self.theme_var.get()),
            style="Settings.TRadiobutton",
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Radiobutton(
            theme_group,
            text="ダーク",
            value="dark",
            variable=self.theme_var,
            command=lambda: self.actions._apply_theme(self.theme_var.get()),
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
        ttk.Button(font_quick_actions, text="小さく", command=self.actions._decrease_font_size, style="FontStep.TButton").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(font_quick_actions, textvariable=self.font_size_display_var, style="SettingsValue.TLabel").grid(
            row=0, column=1
        )
        ttk.Button(font_quick_actions, text="大きく", command=self.actions._increase_font_size, style="FontStep.TButton").grid(
            row=0, column=2, sticky="e"
        )

    def _build_font_preset_row(self, font_group: "ttk.LabelFrame") -> None:
        preset_row = ttk.Frame(font_group, style="CardInner.TFrame")
        preset_row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(preset_row, text="よく使うサイズ", style="CardMeta.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        for index, preset in enumerate((9, 11, 13, 15), start=1):
            ttk.Button(
                preset_row,
                text=f"{preset} pt",
                command=lambda value=preset: self.actions._apply_font_size_preset(value),
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
            command=self.actions._on_font_size_scale,
            style="Settings.Horizontal.TScale",
            takefocus=True,
        )
        self.font_size_scale.grid(row=0, column=1, sticky="ew")
        self.font_size_scale.bind("<Left>", self.actions._on_font_size_scale_left)
        self.font_size_scale.bind("<Right>", self.actions._on_font_size_scale_right)
        self.font_size_scale.bind("<Home>", self.actions._on_font_size_scale_home)
        self.font_size_scale.bind("<End>", self.actions._on_font_size_scale_end)
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

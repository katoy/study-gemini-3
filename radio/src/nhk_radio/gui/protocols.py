"""GUI Mixin が要求するプロトコル型（Protocol）の定義。"""

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Protocol

from ..types import Episode, Program


class GuiBrowserProtocol(Protocol):
    """EpisodeGuiBrowser が実装すべき型契約。

    Mixin が self に対して期待する全プロパティ・メソッドをここで定義。
    これにより mypy は型チェック時に Mixin コードが正しいことを検証できる。
    """

    # ========================
    # コンポーネント（Widget）
    # ========================
    root: tk.Tk
    program_tree: ttk.Treeview
    episode_tree: ttk.Treeview
    program_search_entry: tk.Entry
    episode_search_entry: tk.Entry
    program_genre_filter_combo: ttk.Combobox
    episode_saved_only_check: ttk.Checkbutton
    download_button: ttk.Button
    saved_button: ttk.Button
    copy_cell_button: ttk.Button
    fetch_button: ttk.Button

    # ========================
    # 状態（StringVar / BooleanVar）
    # ========================
    program_search_var: tk.StringVar
    program_genre_filter_var: tk.StringVar
    episode_search_var: tk.StringVar
    episode_saved_only_var: tk.BooleanVar
    status_var: tk.StringVar
    selected_cell_meta_var: tk.StringVar
    selected_cell_value_var: tk.StringVar
    program_list_summary_var: tk.StringVar
    episode_filter_summary_var: tk.StringVar
    episode_selection_summary_var: tk.StringVar
    selected_program_title_var: tk.StringVar
    selected_program_meta_var: tk.StringVar
    selected_program_stats_var: tk.StringVar
    episode_message_var: tk.StringVar
    episode_title_var: tk.StringVar

    # ========================
    # プログラムデータ
    # ========================
    programs: list[Program]
    filtered_programs: list[Program]
    program_order_map: dict[str | None, int]
    program_tree_programs: dict[str, Program]
    selected_program_key: str | None

    # ========================
    # エピソードデータ
    # ========================
    displayed_program: Program | None
    displayed_episodes: list[Episode]
    displayed_episode_map: dict[str, Episode]
    selected_episode_keys: tuple[str, ...]

    # ========================
    # ソート・フィルタ状態
    # ========================
    program_sort_state: tuple[str, bool]
    episode_sort_state: tuple[str, bool]

    # ========================
    # 設定・パス
    # ========================
    output_dir: Path
    current_theme: str
    current_font_size: str
    loading: bool

    # ========================
    # GuiProgramsMixin メソッド
    # ========================
    def _normalized_search_text(self, text: str) -> str: ...
    def _apply_program_filters(self) -> None: ...
    def _populate_programs(self, preserve_selection: bool = True) -> None: ...
    def _program_key(self, program: Program | None) -> str | None: ...
    def _selected_program(self) -> Program | None: ...
    def _sorted_programs(self, programs: list[Program]) -> list[Program]: ...
    def _update_program_tree_headings(self) -> None: ...
    def _on_program_select(self, _event: Any = None) -> None: ...
    def _update_program_overview(
        self, program: Program | None, episodes: list[Episode] | None = None, message: str = ""
    ) -> None: ...

    # ========================
    # GuiEpisodeMixin メソッド
    # ========================
    def _render_episode_rows(
        self, program: Program, episodes: list[Episode], clear_selection: bool = True
    ) -> None: ...
    def _sorted_episodes(self, episodes: list[Episode]) -> list[Episode]: ...
    def _downloaded_cell_text(self, downloaded: bool) -> str: ...
    def _is_saved_item(self, item_id: str) -> bool: ...
    def _refresh_downloaded_column(self, program: Program) -> None: ...
    def _selected_episode_keys(self) -> tuple[str, ...]: ...

    # ========================
    # GuiOperationsMixin メソッド
    # ========================
    def _tree_label(self, tree: ttk.Treeview) -> str: ...
    def _tree_cell_from_event(self, tree: ttk.Treeview, event: Any) -> tuple[str, str, str] | None: ...
    def _set_selected_tree_cell(self, tree: ttk.Treeview, column_id: str, value: str) -> None: ...
    def _is_episode_downloaded(self, item_id: str) -> bool: ...
    def _play_episode_file(self, item_id: str) -> None: ...
    def _show_episode_context_menu(self, event: Any, item_id: str) -> None: ...

    # ========================
    # その他の重要メソッド
    # ========================
    def _update_selected_cell_ui(self, meta: str, value: str) -> None: ...

"""Listing and selection helpers for EpisodeGuiBrowser."""

import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

from ..cache import load_episode_cache
from ..config import CACHE_TTL_SECONDS, SEARCH_HISTORY_LIMIT
from ..downloads import (
    _episode_key,
    _load_download_manifest,
    is_episode_downloaded,
    resolve_episode_downloaded_path,
)
from ..text import (
    _genre_label,
    _normalize_text,
    _sortable_day_value,
    _sortable_duration_value,
    _sortable_timestamp_value,
)
from ..types import Episode, Program
from .toolkit import tk, ttk

if TYPE_CHECKING:
    from .browser import EpisodeGuiBrowser


class GuiListingMixin:
    # Mixin properties to help type checker (cast self to EpisodeGuiBrowser)
    if TYPE_CHECKING:
        root: tk.Tk
        programs: list[Program]
        filtered_programs: list[Program]
        displayed_program: Program | None
        displayed_episodes: list[Episode]
        displayed_episode_map: dict[str, Episode]
        output_dir: Path
        _palette: dict[str, str]

    def _program_genre_filter_values(self) -> list[str]:
        labels = sorted({program.genre_label or _genre_label(program.genre) for program in self.programs})
        return ["すべて", *[label for label in labels if label]]

    def _on_program_filter_change(self, *_args):
        if not hasattr(self, "program_tree"):
            return
        self._apply_program_filters()

    def _apply_program_filters(self):
        needle = self._normalized_search_text(self.program_search_var.get())
        genre_filter = self.program_genre_filter_var.get()
        filtered = list(self.programs)
        if genre_filter and genre_filter != "すべて":
            filtered = [
                program
                for program in filtered
                if (program.genre_label or _genre_label(program.genre)) == genre_filter
            ]
        if needle:
            filtered = [program for program in filtered if needle in self._program_search_target(program)]
        self.filtered_programs = filtered
        self._update_program_search_history_values()
        self._populate_programs()

    def _populate_programs(self, preserve_selection: bool = True):
        p = self._palette
        self.program_tree.tag_configure("even", background=p["surface"])
        self.program_tree.tag_configure("odd", background=p["row_odd"])
        current_program = self._selected_program() or self.displayed_program if preserve_selection else None
        current_key = self._program_key(current_program) if current_program is not None else None
        programs = self._sorted_programs(self.filtered_programs)
        self.program_tree_programs.clear()
        for item_id in self.program_tree.get_children():
            self.program_tree.delete(item_id)
        selected_item_id = ""
        for index, program in enumerate(programs, 1):
            item_id = f"program-{index - 1}"
            tag = "odd" if index % 2 == 1 else "even"
            self.program_tree.insert(
                "",
                "end",
                iid=item_id,
                tags=(tag,),
                values=(
                    self.program_order_map.get(self._program_key(program), index),
                    program.display_date or "----",
                    program.display_title or program.title,
                ),
            )
            self.program_tree_programs[item_id] = program
            if current_key is not None and self._program_key(program) == current_key:
                selected_item_id = item_id
        if programs and selected_item_id:
            self._select_program_item(selected_item_id)
            self._on_program_select()
        elif programs and preserve_selection:
            self._select_program_item("program-0")
            self._on_program_select()
        else:
            self._clear_program_selection()
        self._update_fetch_button_state()

    def _selected_program(self) -> dict | None:
        selection = self.program_tree.selection()
        if not selection:
            return None
        return self.program_tree_programs.get(selection[0])

    def _select_program_item(self, item_id: str):
        if item_id not in self.program_tree_programs:
            return
        self.program_tree.selection_set(item_id)
        self.program_tree.focus(item_id)
        self.program_tree.see(item_id)

    def _program_key(self, program: Program | None) -> tuple[str, str] | None:
        if program is None:
            return None
        return program.site_id, program.corner_id

    def _heading_text(self, label: str, active_column: str | None, column: str, reverse: bool) -> str:
        if active_column != column:
            return label
        return f"{label}{'▼' if reverse else '▲'}"

    def _update_program_tree_headings(self):
        self.program_tree.heading(
            "no",
            text=self._heading_text("No.", self.program_sort_column, "no", self.program_sort_reverse),
            anchor="e",
            command=lambda: self._toggle_program_sort("no"),
        )
        self.program_tree.heading(
            "date",
            text=self._heading_text("更新日", self.program_sort_column, "date", self.program_sort_reverse),
            anchor="w",
            command=lambda: self._toggle_program_sort("date"),
        )
        self.program_tree.heading(
            "title",
            text=self._heading_text("番組", self.program_sort_column, "title", self.program_sort_reverse),
            anchor="w",
            command=lambda: self._toggle_program_sort("title"),
        )

    def _update_episode_tree_headings(self):
        self.episode_tree.heading(
            "saved",
            text=self._heading_text("DL", self.episode_sort_column, "saved", self.episode_sort_reverse),
            anchor="center",
            command=lambda: self._toggle_episode_sort("saved"),
        )
        self.episode_tree.heading(
            "date",
            text=self._heading_text("放送日時", self.episode_sort_column, "date", self.episode_sort_reverse),
            anchor="w",
            command=lambda: self._toggle_episode_sort("date"),
        )
        self.episode_tree.heading(
            "duration",
            text=self._heading_text("長さ", self.episode_sort_column, "duration", self.episode_sort_reverse),
            anchor="e",
            command=lambda: self._toggle_episode_sort("duration"),
        )
        self.episode_tree.heading(
            "title",
            text=self._heading_text("タイトル", self.episode_sort_column, "title", self.episode_sort_reverse),
            anchor="w",
            command=lambda: self._toggle_episode_sort("title"),
        )

    def _toggle_program_sort(self, column: str):
        if self.program_sort_column == column:
            self.program_sort_reverse = not self.program_sort_reverse
        else:
            self.program_sort_column = column
            self.program_sort_reverse = False
        self._update_program_tree_headings()
        self._populate_programs(preserve_selection=False)

    def _toggle_episode_sort(self, column: str):
        if self.episode_sort_column == column:
            self.episode_sort_reverse = not self.episode_sort_reverse
        else:
            self.episode_sort_column = column
            self.episode_sort_reverse = False
        self._update_episode_tree_headings()
        self._rerender_displayed_episodes()

    def _sorted_programs(self, programs: list[dict]) -> list[dict]:
        if self.program_sort_column is None:
            return list(programs)
        return sorted(programs, key=self._program_sort_key, reverse=self.program_sort_reverse)

    def _program_sort_key(self, program: Program):
        program_key = self._program_key(program)
        original_index = self.program_order_map.get(program_key, 10**9)
        display_title = self._normalized_search_text(program.display_title or program.title)
        if self.program_sort_column == "no":
            return (original_index, display_title)
        if self.program_sort_column == "date":
            started_at = _sortable_timestamp_value(program.started_at)
            day = _sortable_day_value(str(program.onair_date or program.display_date or ""))
            return (started_at, day, display_title, original_index)
        return (display_title, original_index)

    def _normalized_search_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", _normalize_text(text))
        return re.sub(r"\s+", " ", normalized).casefold()

    def _program_search_target(self, program: Program) -> str:
        return self._normalized_search_text(
            " ".join(
                part
                for part in (
                    program.display_title,
                    program.title,
                    program.corner_name,
                    program.genre_label,
                    program.genre,
                )
                if part
            )
        )

    def _program_list_summary_text(self) -> str:
        total = len(self.programs)
        visible = len(self.filtered_programs)
        filters: list[str] = []
        if self.program_genre_filter_var.get() and self.program_genre_filter_var.get() != "すべて":
            filters.append(self.program_genre_filter_var.get())
        if self._normalized_search_text(self.program_search_var.get()):
            filters.append("検索中")
        if filters:
            return f"{visible} / {total} 番組 ({' / '.join(filters)})"
        return f"{total} 番組"

    def _program_search_history_values(self) -> list[str]:
        needle = self._normalized_search_text(self.program_search_var.get())
        if not needle:
            return list(self.program_search_history)
        return [term for term in self.program_search_history if needle in self._normalized_search_text(term)]

    def _update_program_search_history_values(self):
        if hasattr(self, "program_search_entry"):
            self.program_search_entry.configure(values=self._program_search_history_values())

    def _remember_program_search(self, raw_term: str) -> bool:
        term = _normalize_text(raw_term)
        if not term:
            return False

        key = self._normalized_search_text(term)
        history = [item for item in self.program_search_history if self._normalized_search_text(item) != key]
        history.insert(0, term)
        self.program_search_history = history[:SEARCH_HISTORY_LIMIT]
        self._update_program_search_history_values()
        self._persist_ui_settings()
        return True

    def _clear_program_selection(self):
        self.program_tree.selection_remove(self.program_tree.selection())
        self.program_tree.focus("")
        self.displayed_program = None
        self.displayed_episodes = []
        self.displayed_episode_map.clear()
        for item_id in self.episode_tree.get_children():
            self.episode_tree.delete(item_id)
        self.episode_title_var.set("エピソード一覧")
        self.episode_message_var.set("一覧は未取得です。")
        self.download_button.state(["disabled"])
        self._update_fetch_button_state()
        self._schedule_saved_button_refresh()

        search_text = _normalize_text(self.program_search_var.get())
        self.program_list_summary_var.set(self._program_list_summary_text())
        if search_text:
            self.selected_program_title_var.set("一致する番組がありません")
            self.selected_program_meta_var.set(f"検索: {search_text}")
            self.selected_program_stats_var.set("検索条件を変更してください。")
        else:
            self.selected_program_title_var.set("番組を選択してください")
            self.selected_program_meta_var.set("左の番組一覧から選択すると、ここに番組の概要が表示されます。")
            self.selected_program_stats_var.set("エピソード一覧は未取得です。")

    def _on_program_search_change(self, *_args):
        # 入力のたびに実行せず、一定時間入力が止まってからフィルタを適用する（デバウンス）
        if hasattr(self, "_search_timer"):
            self.root.after_cancel(self._search_timer)
        self._search_timer = self.root.after(250, self._apply_program_filters)

    def _clear_program_search(self, _event=None):
        self.program_search_var.set("")
        self.program_search_entry.focus_set()
        return "break"

    def _commit_program_search(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        return self._focus_program_tree_from_search()

    def _on_program_search_history_selected(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        return None

    def _on_program_search_focus_in(self, _event=None):
        self._update_program_search_history_values()
        return None

    def _on_program_search_focus_out(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        return None

    def _focus_program_tree_from_search(self, _event=None):
        if self.filtered_programs:
            self._remember_program_search(self.program_search_var.get())
            self.program_tree.focus_set()
            if not self.program_tree.selection():
                self._select_program_item("program-0")
                self._on_program_select()
        return "break"

    def _cached_episodes_for(self, program: Program) -> list[Episode]:
        """メモリキャッシュのみを同期的にチェックする軽量版。"""
        key = (program.site_id, program.corner_id)
        cached = self.episodes_cache.get(key)
        if cached is not None:
            cached_at, episodes = cached
            if time.time() - cached_at <= CACHE_TTL_SECONDS:
                return episodes
        return []

    def _update_program_overview(
        self,
        program: Program | None,
        episodes: list[Episode] | None = None,
        message: str | None = None,
    ):
        if program is None:
            self.program_list_summary_var.set(self._program_list_summary_text())
            self.selected_program_title_var.set("番組を選択してください")
            self.selected_program_meta_var.set("左の番組一覧から選択すると、ここに番組の概要が表示されます。")
            self.selected_program_stats_var.set("エピソード一覧は未取得です。")
            return

        title = program.display_title or program.title
        genre_label = program.genre_label or _genre_label(program.genre)
        meta_parts = [
            genre_label,
            f"更新 {program.display_date or '----'}",
            f"ID {program.site_id}_{program.corner_id}",
        ]
        corner_name = _normalize_text(program.corner_name or "")
        if corner_name and corner_name != _normalize_text(program.title or ""):
            meta_parts.insert(1, corner_name)

        self.program_list_summary_var.set(f"{self._program_list_summary_text()} / 選択中: {genre_label}")
        self.selected_program_title_var.set(title)
        self.selected_program_meta_var.set(" / ".join(part for part in meta_parts if part))

        if episodes is None:
            stats = ""
        else:
            downloaded_count = sum(
                1 for episode in episodes if is_episode_downloaded(self.output_dir, program, episode)
            )
            stats = f"{len(episodes)} エピソード"
            if downloaded_count:
                stats += f" (保存済み {downloaded_count})"
        if message:
            stats = f"{stats} | {message}" if stats else message
        self.selected_program_stats_var.set(stats)

    def _on_program_select(self, _event=None):
        program = self._selected_program()
        if program is None:
            return None

        # メモリキャッシュをまずチェック（これは非常に速い）
        key = (program.site_id, program.corner_id)
        cached = self.episodes_cache.get(key)
        
        if cached is not None:
            cached_at, episodes = cached
            if time.time() - cached_at <= CACHE_TTL_SECONDS:
                self.status_var.set("")
                self._update_program_overview(program, episodes, "")
                self._show_episodes(program, episodes, message="")
                self._update_fetch_button_state()
                return None

        # メモリにない場合は、バックグラウンドでディスクキャッシュ・ネットワークをチェック
        self._update_program_overview(program, None, "準備中...")
        self._show_episodes(program, [], message="情報を確認しています...")
        
        # 非同期取得を開始 (GuiDownloadsMixin のメソッド)
        self.root.after_idle(lambda: self._start_fetch_selected(silent=True))
        return None

    def _on_program_double_click(self, event):
        if self.loading:
            return "break"

        item_id = self.program_tree.identify_row(event.y)
        if not item_id:
            return "break"

        self._select_program_item(item_id)
        self._on_program_select()
        self.root.after_idle(self._start_fetch_selected)
        return "break"

    def _tree_label(self, tree: ttk.Treeview) -> str:
        if tree is self.program_tree:
            return "番組一覧"
        if tree is self.episode_tree:
            return "エピソード一覧"
        return "一覧"

    def _bind_tooltip(self, widget, text: str):
        widget.bind("<Enter>", lambda event: self._show_tooltip(event, text), add="+")
        widget.bind("<Motion>", self._move_tooltip, add="+")
        widget.bind("<Leave>", lambda _event: self._hide_tooltip(), add="+")
        widget.bind("<ButtonPress>", lambda _event: self._hide_tooltip(), add="+")

    def _show_tooltip(self, event, text: str):
        self._hide_tooltip()
        tooltip = tk.Toplevel(self.root)
        tooltip.wm_overrideredirect(True)
        tooltip.attributes("-topmost", True)
        tooltip.configure(background=self._palette["border_strong"])

        label = tk.Label(
            tooltip,
            text=text,
            justify="left",
            padx=8,
            pady=5,
            background=self._palette["surface_alt"],
            foreground=self._palette["text"],
            font=self._ui_small,
            borderwidth=0,
        )
        label.pack(padx=1, pady=1)

        self.tooltip_window = tooltip
        self.tooltip_label = label
        self._move_tooltip(event)

    def _move_tooltip(self, event):
        if self.tooltip_window is None or not self.tooltip_window.winfo_exists():
            return
        x = event.x_root + 14
        y = event.y_root + 18
        self.tooltip_window.geometry(f"+{x}+{y}")

    def _hide_tooltip(self):
        if self.tooltip_window is not None and self.tooltip_window.winfo_exists():
            self.tooltip_window.destroy()
        self.tooltip_window = None
        self.tooltip_label = None

    def _tree_cell_from_event(self, tree: ttk.Treeview, event) -> tuple[str, str, str] | None:
        if tree.identify("region", event.x, event.y) != "cell":
            return None

        item_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not item_id or not column_id.startswith("#"):
            return None

        try:
            column_index = int(column_id[1:]) - 1
        except ValueError:
            return None

        values = tree.item(item_id, "values")
        if column_index < 0 or column_index >= len(values):
            return None
        return item_id, column_id, str(values[column_index])

    def _set_selected_tree_cell(self, tree: ttk.Treeview, column_id: str, value: str):
        try:
            column_index = int(column_id[1:]) - 1
        except ValueError:
            return

        columns = tree["columns"]
        if column_index < 0 or column_index >= len(columns):
            return

        heading = tree.heading(columns[column_index], "text") or columns[column_index]
        self.selected_cell_meta_var.set(f"{self._tree_label(tree)} / {heading}")
        self.selected_cell_value_var.set(value)
        if hasattr(self, "selected_cell_entry"):
            self.selected_cell_entry.xview_moveto(0)
        self._update_selected_cell_ui()

    def _on_program_tree_click(self, event):
        cell = self._tree_cell_from_event(self.program_tree, event)
        if cell is None:
            return None

        _item_id, column_id, value = cell
        self._set_selected_tree_cell(self.program_tree, column_id, value)
        return None

    def _show_episodes(self, program: Program, episodes: list[Episode], message: str):
        self.displayed_program = program
        self.displayed_episodes = list(episodes)
        self.episode_title_var.set(f"エピソード一覧: {program.display_title or program.title}")
        self.episode_message_var.set(message)
        self._render_episode_rows(program, episodes, clear_selection=False)

    def _episode_search_target(self, episode: Episode) -> str:
        return self._normalized_search_text(
            " ".join(
                part
                for part in (
                    episode.display_title,
                    episode.title,
                    episode.display_date,
                    episode.broadcast_time,
                    episode.duration_str,
                )
                if part
            )
        )

    def _filtered_episode_rows(self, program: Program, episodes: list[Episode]) -> list[Episode]:
        needle = self._normalized_search_text(self.episode_search_var.get())
        saved_only = self.episode_saved_only_var.get()
        filtered = list(episodes)
        if needle:
            filtered = [episode for episode in filtered if needle in self._episode_search_target(episode)]
        if saved_only:
            filtered = [episode for episode in filtered if is_episode_downloaded(self.output_dir, program, episode)]
        return filtered

    def _update_episode_filter_summary(self, visible_count: int, total_count: int):
        filters: list[str] = []
        if self._normalized_search_text(self.episode_search_var.get()):
            filters.append("検索中")
        if self.episode_saved_only_var.get():
            filters.append("保存済みのみ")
        suffix = f" ({' / '.join(filters)})" if filters else ""
        self.episode_filter_summary_var.set(f"表示 {visible_count} / 全 {total_count} 件{suffix}")

    def _update_episode_selection_summary(self):
        selection_count = len(self.episode_tree.selection()) if hasattr(self, "episode_tree") else 0
        self.episode_selection_summary_var.set(f"選択 {selection_count} 件")

    def _on_episode_selection_change(self, _event=None):
        self._update_episode_selection_summary()
        return None

    def _on_episode_filter_change(self, *_args):
        if self.displayed_program is None:
            self._update_episode_filter_summary(0, 0)
            self._update_episode_selection_summary()
            return
        self._rerender_displayed_episodes()

    def _clear_episode_search(self, _event=None):
        self.episode_search_var.set("")
        if hasattr(self, "episode_search_entry"):
            self.episode_search_entry.focus_set()
        return "break"

    def _sorted_episodes(self, episodes: list[Episode]) -> list[Episode]:
        if self.episode_sort_column is None:
            return list(episodes)

        order_map = {_episode_key(episode): index for index, episode in enumerate(episodes)}

        def sort_key(episode: Episode):
            original_index = order_map.get(_episode_key(episode), 10**9)
            title = self._normalized_search_text(episode.display_title or episode.title)
            if self.episode_sort_column == "saved":
                saved = (
                    is_episode_downloaded(self.output_dir, self.displayed_program, episode)
                    if self.displayed_program
                    else False
                )
                return (saved, title, original_index)
            if self.episode_sort_column == "date":
                timestamp = _sortable_timestamp_value(episode.date)
                day = _sortable_day_value(str(episode.date or episode.display_date or ""))
                time_text = _normalize_text(episode.broadcast_time)
                return (timestamp, day, time_text, title, original_index)
            if self.episode_sort_column == "duration":
                duration = _sortable_duration_value(str(episode.duration_str or ""))
                return (duration, title, original_index)
            return (title, original_index)

        return sorted(episodes, key=sort_key, reverse=self.episode_sort_reverse)

    def _render_episode_rows(self, program: Program, episodes: list[Episode], clear_selection: bool):
        self.displayed_episode_map.clear()
        for item in self.episode_tree.get_children():
            self.episode_tree.delete(item)

        p = self._palette
        self.episode_tree.tag_configure("even", background=p["surface"])
        self.episode_tree.tag_configure("odd", background=p["row_odd"])
        self.episode_tree.tag_configure("dl_even", background=p["dl_even"])
        self.episode_tree.tag_configure("dl_odd", background=p["dl_odd"])
        rendered = self._sorted_episodes(self._filtered_episode_rows(program, episodes))
        for index, episode in enumerate(rendered):
            iid = f"episode-{index}"
            self.displayed_episode_map[iid] = episode
            is_dl = is_episode_downloaded(self.output_dir, program, episode)
            saved = self._downloaded_cell_text(is_dl)
            date_time = episode.display_date or "----"
            btime = episode.broadcast_time
            if btime:
                date_time = f"{date_time} {btime}"
            dur = episode.duration_str or "----"
            tag = ("dl_odd" if index % 2 == 1 else "dl_even") if is_dl else "odd" if index % 2 == 1 else "even"
            self.episode_tree.insert(
                "",
                "end",
                iid=iid,
                tags=(tag,),
                values=(saved, date_time, dur, episode.display_title or episode.title),
            )

        if rendered:
            if clear_selection:
                self.episode_tree.selection_remove(self.episode_tree.selection())
                self.episode_tree.focus("")
            else:
                first = next(iter(self.displayed_episode_map))
                self.episode_tree.selection_set(first)
                self.episode_tree.focus(first)
                self.episode_tree.see(first)
            self.download_button.state(["!disabled"])
        else:
            self.episode_tree.selection_remove(self.episode_tree.selection())
            self.episode_tree.focus("")
            self.download_button.state(["disabled"])
        self._update_episode_filter_summary(len(rendered), len(episodes))
        self._update_episode_selection_summary()
        self._schedule_saved_button_refresh()

    def _rerender_displayed_episodes(self):
        if self.displayed_program is None:
            return
        self._render_episode_rows(self.displayed_program, self.displayed_episodes, clear_selection=True)

    def _refresh_downloaded_column(self, program: Program):
        if self.displayed_program is None:
            return
        if (
            self.displayed_program.site_id != program.site_id
            or self.displayed_program.corner_id != program.corner_id
        ):
            return

        for iid, episode in self.displayed_episode_map.items():
            values = list(self.episode_tree.item(iid, "values"))
            if len(values) < 3:
                continue
            values[0] = self._downloaded_cell_text(is_episode_downloaded(self.output_dir, program, episode))
            self.episode_tree.item(iid, values=tuple(values))
        self._schedule_saved_button_refresh()
        self._update_program_overview(self.displayed_program, self.displayed_episodes, "保存状態を更新")

    def _downloaded_cell_text(self, downloaded: bool) -> str:
        return "済" if downloaded else "-"

    def _is_saved_item(self, item_id: str) -> bool:
        values = self.episode_tree.item(item_id, "values")
        return bool(values and values[0] == self._downloaded_cell_text(True))

    def _schedule_saved_button_refresh(self):
        if self.saved_button_refresh_pending:
            return
        self.saved_button_refresh_pending = True
        self.root.after_idle(self._refresh_saved_episode_buttons)

    def _refresh_saved_episode_buttons(self):
        self.saved_button_refresh_pending = False
        if not hasattr(self, "episode_tree") or not self.episode_tree.winfo_exists():
            return

        visible_saved_items: set[str] = set()
        for item_id in self.episode_tree.get_children():
            if item_id not in self.displayed_episode_map or not self._is_saved_item(item_id):
                continue

            bbox = self.episode_tree.bbox(item_id, column="#1")
            if not bbox:
                continue

            x, y, width, height = bbox
            button = self.saved_episode_buttons.get(item_id)
            if button is None or not button.winfo_exists():
                button = ttk.Button(
                    self.episode_tree,
                    text="済",
                    style="SavedCell.TButton",
                    cursor="hand2",
                    takefocus=False,
                    command=lambda iid=item_id: self._open_saved_episode_from_item(iid),
                )
                self.saved_episode_buttons[item_id] = button

            button_width = max(min(width - 12, 46), 34)
            button_height = max(min(height - 8, 24), 18)
            button.place(
                x=x + max((width - button_width) // 2, 0),
                y=y + max((height - button_height) // 2, 0),
                width=button_width,
                height=button_height,
            )
            button.lift()
            visible_saved_items.add(item_id)

        for item_id, button in list(self.saved_episode_buttons.items()):
            if item_id not in self.displayed_episode_map or not self._is_saved_item(item_id):
                button.destroy()
                del self.saved_episode_buttons[item_id]
                continue
            if item_id not in visible_saved_items:
                button.place_forget()

    def _on_episode_tree_scroll(self, *args):
        self.episode_tree.yview(*args)
        self._schedule_saved_button_refresh()

    def _on_episode_tree_yscroll(self, first: str, last: str):
        self.episode_scroll.set(first, last)
        self._schedule_saved_button_refresh()

    def _on_episode_tree_configure(self, _event):
        self._schedule_saved_button_refresh()

    def _is_saved_cell_clickable(self, event) -> bool:
        if self.displayed_program is None:
            return False
        region = self.episode_tree.identify("region", event.x, event.y)
        if region != "cell":
            return False
        if self.episode_tree.identify_column(event.x) != "#1":
            return False

        item_id = self.episode_tree.identify_row(event.y)
        if not item_id or item_id not in self.displayed_episode_map:
            return False

        return self._is_saved_item(item_id)

    def _on_episode_tree_motion(self, event):
        self.episode_tree.configure(cursor="hand2" if self._is_saved_cell_clickable(event) else "")

    def _on_episode_tree_leave(self, _event):
        self.episode_tree.configure(cursor="")

    def _on_episode_tree_click(self, event):
        cell = self._tree_cell_from_event(self.episode_tree, event)
        if cell is not None:
            _item_id, column_id, value = cell
            self._set_selected_tree_cell(self.episode_tree, column_id, value)

        if self.displayed_program is None or not self._is_saved_cell_clickable(event):
            return None
        item_id = self.episode_tree.identify_row(event.y)
        return self._open_saved_episode_from_item(item_id)

    def _open_saved_episode_from_item(self, item_id: str):
        if self.displayed_program is None or item_id not in self.displayed_episode_map:
            return None
        self._set_selected_tree_cell(self.episode_tree, "#1", self._downloaded_cell_text(True))
        episode = self.displayed_episode_map[item_id]
        path = resolve_episode_downloaded_path(self.output_dir, self.displayed_program, episode)
        if path is None:
            # 理由を特定するためのヒントを表示
            _, saved_paths = _load_download_manifest(self.displayed_program, self.output_dir)
            recorded_path = saved_paths.get(_episode_key(episode), "(記録なし)")
            self.status_var.set(f"保存済みファイルが見つかりません。記録パス: {recorded_path}")
            return "break"

        self._open_saved_folder(path)
        return "break"

    def _show_saved_episode_popup(self, path: Path, episode: Episode):
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.destroy()

        popup = tk.Toplevel(self.root)
        popup.title("保存済みファイル")
        popup.geometry("760x260")
        popup.minsize(560, 220)
        popup.transient(self.root)
        popup.resizable(True, False)
        popup.configure(background=self._palette["surface"])

        self._build_saved_episode_popup_content(popup, path, episode)

        popup.bind("<Escape>", lambda _event: popup.destroy())
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
        self.saved_episode_popup = popup

    def _build_saved_episode_popup_content(self, popup: tk.Toplevel, path: Path, episode: Episode) -> None:
        main = ttk.Frame(popup, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="保存済みファイル", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=episode.display_title or episode.title or "エピソード",
            style="PopupTitle.TLabel",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        body = ttk.Frame(main, padding=(0, 14, 0, 0))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="ファイル名", style="PopupLabel.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 12))
        ttk.Label(body, text=path.name, style="PopupValue.TLabel", wraplength=560, justify="left").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(body, text="保存先PATH", style="PopupLabel.TLabel").grid(
            row=1, column=0, sticky="nw", padx=(0, 12), pady=(12, 0)
        )
        # ガベージコレクションを防ぐため popup に属性として保持させる
        popup._path_var = tk.StringVar(popup, value=str(path.absolute()))
        path_entry = ttk.Entry(body, textvariable=popup._path_var)
        path_entry.grid(row=1, column=1, sticky="ew", pady=(12, 0))
        path_entry.state(["readonly"])
        ttk.Label(body, text="保存先フォルダ", style="PopupLabel.TLabel").grid(
            row=2, column=0, sticky="nw", padx=(0, 12), pady=(12, 0)
        )
        ttk.Label(
            body, text=str(path.parent.absolute()), style="PopupValue.TLabel", wraplength=560, justify="left"
        ).grid(row=2, column=1, sticky="w", pady=(12, 0))

        ttk.Separator(main, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=(16, 12))
        buttons = ttk.Frame(main)
        buttons.grid(row=3, column=0, sticky="e")
        ttk.Button(buttons, text="PATHのコピー", command=lambda: self._copy_path_to_clipboard(path)).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(buttons, text="フォルダオープン", command=lambda: self._open_saved_folder(path)).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(buttons, text="閉じる", command=popup.destroy).grid(row=0, column=2)

    def _copy_path_to_clipboard(self, path: Path):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(path))
        self.root.update_idletasks()
        self.status_var.set("PATH をクリップボードにコピーしました。")

    def _copy_selected_cell_to_clipboard(self, _event=None):
        value = self.selected_cell_value_var.get()
        if not value:
            self.status_var.set("コピーするセルをクリックしてください。")
            return "break"

        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()
        self.status_var.set("セル値をクリップボードにコピーしました。")
        return "break"

    def _open_saved_folder(self, path: Path):
        target_dir = path.parent
        if not target_dir.exists():
            self.status_var.set("保存先フォルダが見つかりません。")
            return

        if sys.platform == "darwin":
            cmd = ["open", str(target_dir)]
        elif sys.platform.startswith("win"):
            cmd = ["cmd", "/c", "start", "", str(target_dir)]
        else:
            cmd = ["xdg-open", str(target_dir)]

        subprocess.Popen(cmd)
        self.status_var.set(f"フォルダを開きました: {target_dir}")


__all__ = ["GuiListingMixin"]

"""NHK Radio program and episode listing logic for the GUI."""

import logging
import queue
import re
import threading
import tkinter as tk
import unicodedata
import webbrowser
from collections import OrderedDict
from pathlib import Path
from tkinter import ttk, messagebox

from ..config import CACHE_TTL_SECONDS, SEARCH_HISTORY_LIMIT
from ..constants import _HEADERS, GENRE_LABELS, NHK_API_GENRE, NHK_GENRES
from ..core import (
    fetch_program_list,
    refresh_episode_list,
)
from ..downloads import is_episode_downloaded
from ..text import (
    _format_episode_date,
    _format_onair_date,
    _genre_label,
    _normalize_text,
    _sortable_day_value,
    _sortable_duration_value,
    _sortable_timestamp_value,
)
from ..types import Episode, Program

logger = logging.getLogger(__name__)


class GuiListingMixin:
    """Logic for program and episode listing, filtering, and selection."""

    # Mixin properties to help type checker
    if False:
        from .browser import EpisodeGuiBrowser
        self = EpisodeGuiBrowser()

    def _on_program_filter_change(self, *_args):
        if not hasattr(self, "program_tree"):
            return
        self._apply_program_filters()

    def _update_program_genre_filter_values(self):
        if hasattr(self, "program_genre_filter_combo"):
            self.program_genre_filter_combo.configure(values=self._program_genre_filter_values())

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
        self._update_program_genre_filter_values()
        self._populate_programs()

    def _populate_programs(self, preserve_selection: bool = True):
        self._update_program_genre_filter_values()
        # 描画バグ回避のため、背景色タグ（even/odd）の設定は行わない
        current_program = self._selected_program() or self.displayed_program if preserve_selection else None
        current_key = self._program_key(current_program) if current_program is not None else None
        programs = self._sorted_programs(self.filtered_programs)
        self.program_tree_programs.clear()
        for item_id in self.program_tree.get_children():
            self.program_tree.delete(item_id)
        selected_item_id = ""
        for index, program in enumerate(programs, 1):
            item_id = f"program-{index - 1}"
            self.program_tree.insert(
                "",
                "end",
                iid=item_id,
                # tag による背景色指定を行わない
                values=(
                    self.program_order_map.get(self._program_key(program), index),
                    program.display_date or "----",
                    program.display_title or program.title,
                ),
            )
            self.program_tree_programs[item_id] = program
            if current_key is not None and self._program_key(program) == current_key:
                selected_item_id = item_id

        if selected_item_id:
            self.program_tree.selection_set(selected_item_id)
            self.program_tree.see(selected_item_id)
        elif programs:
            self.program_tree.selection_set(f"program-0")
            self.program_tree.see(f"program-0")

        self.program_list_summary_var.set(
            f"{len(programs)} / {len(self.programs)} 番組"
            + (f" (検索中)" if len(programs) < len(self.programs) else "")
        )

    def _render_episode_rows(self, program: Program, episodes: list[Episode], clear_selection: bool = True):
        self.displayed_episode_map.clear()
        for item_id in self.episode_tree.get_children():
            self.episode_tree.delete(item_id)
        
        rendered = self._sorted_episodes(episodes)
        to_check = []
        for index, episode in enumerate(rendered):
            iid = f"episode-{index}"
            self.displayed_episode_map[iid] = episode
            
            # 初期状態は「未ダウンロード」として高速描画
            saved = self._downloaded_cell_text(False)
            date_time = episode.display_date or "----"
            btime = episode.broadcast_time
            if btime:
                date_time = f"{date_time} {btime}"
            dur = episode.duration_str or "----"
            
            # 描画バグ回避のため、背景色タグ（even/odd）の設定は行わない
            self.episode_tree.insert(
                "",
                "end",
                iid=iid,
                values=(saved, date_time, dur, episode.display_title or episode.title),
            )
            to_check.append((iid, episode))

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
            
            # 判定処理を開始
            import threading
            threading.Thread(target=self._async_download_check_worker, args=(program, to_check), daemon=True).start()
        else:
            self.episode_tree.selection_remove(self.episode_tree.selection())
            self.episode_tree.focus("")
            self.download_button.state(["disabled"])

        self._update_episode_filter_summary(len(rendered), len(episodes))
        self._update_episode_selection_summary()
        self._schedule_saved_button_refresh()

    def _async_download_check_worker(self, program: Program, to_check: list[tuple[str, Episode]]):
        """バックグラウンドで保存済み判定を行い、UIスレッドに通知する。"""
        results = []
        for iid, episode in to_check:
            if self.displayed_program != program:
                return
            is_dl = is_episode_downloaded(self.output_dir, program, episode)
            if is_dl:
                results.append((iid, True))
        
        if results and self.displayed_program == program:
            self.root.after(0, lambda: self._apply_download_check_results(program, results))

    def _apply_download_check_results(self, program: Program, results: list[tuple[str, bool]]):
        """判定結果を UI に反映する。"""
        if self.displayed_program != program:
            return

        for iid, is_dl in results:
            if not self.episode_tree.exists(iid):
                continue

            saved = self._downloaded_cell_text(is_dl)
            current_values = self.episode_tree.item(iid, "values")
            if not current_values:
                continue

            new_values = list(current_values)
            new_values[0] = saved
            # 背景色の変更（タグの付与）は行わず、値のみを更新する
            self.episode_tree.item(iid, values=tuple(new_values))

    def _rerender_displayed_episodes(self):
        if self.displayed_program is None:
            return
        self._render_episode_rows(self.displayed_program, self.displayed_episodes, clear_selection=True)

    def _refresh_downloaded_column(self, program: Program):
        if self.displayed_program is None:
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
        # 絵文字 (💾) は macOS で黒潰れの原因になるため、
        # より安定した記号 (☑: チェックボックス) をアイコンとして使用します。
        return "  ☑" if downloaded else ""

    def _is_saved_item(self, item_id: str) -> bool:
        values = self.episode_tree.item(item_id, "values")
        return bool(values and "☑" in str(values[0]))

    def _schedule_saved_button_refresh(self):
        if self.saved_button_refresh_pending:
            return
        self.saved_button_refresh_pending = True
        self.root.after(200, self._refresh_saved_only_button_state)

    def _refresh_saved_only_button_state(self):
        self.saved_button_refresh_pending = False
        if not hasattr(self, "episode_saved_only_check"):
            return
        
        # 実際に保存済みアイテムがあるか確認
        has_saved = False
        if self.displayed_program:
            for episode in self.displayed_episodes:
                if is_episode_downloaded(self.output_dir, self.displayed_program, episode):
                    has_saved = True
                    break
        
        if has_saved:
            self.episode_saved_only_check.state(["!disabled"])
        else:
            self.episode_saved_only_check.state(["disabled"])
            self.episode_saved_only_var.set(False)

    def _program_genre_filter_values(self) -> list[str]:
        labels = sorted({program.genre_label or _genre_label(program.genre) for program in self.programs})
        return ["すべて", *[label for label in labels if label]]

    def _normalized_search_text(self, text: str) -> str:
        if not text:
            return ""
        return unicodedata.normalize("NFKC", text).casefold().strip()

    def _program_search_target(self, program: Program) -> str:
        text = f"{program.title} {program.genre_label or ''}"
        return self._normalized_search_text(text)

    def _update_program_search_history_values(self):
        if hasattr(self, "program_search_entry"):
            history = list(self.program_search_history)
            self.program_search_entry.configure(values=history)

    def _remember_program_search(self, term: str):
        term = (term or "").strip()
        if not term:
            return
        
        history = list(self.program_search_history)
        normalized_term = self._normalized_search_text(term)
        
        # 重複除去 (大文字小文字無視)
        new_history = [term]
        seen = {normalized_term}
        for item in history:
            normalized = self._normalized_search_text(item)
            if normalized not in seen:
                new_history.append(item)
                seen.add(normalized)
        
        self.program_search_history = new_history[:SEARCH_HISTORY_LIMIT]
        self._update_program_search_history_values()
        self._persist_ui_settings()

    def _program_key(self, program: Program | None) -> str | None:
        if program is None:
            return None
        return f"{program.site_id}_{program.corner_id}"

    def _selected_program(self) -> Program | None:
        selection = self.program_tree.selection()
        if not selection:
            return None
        return self.program_tree_programs.get(selection[0])

    def _on_program_select(self, _event=None):
        program = self._selected_program()
        if program:
            # 概要を即座に更新
            self._update_program_overview(program, None, "詳細を読み込み中...")
            self.selected_program_title_var.set(program.display_title or program.title)
            self.selected_program_meta_var.set(f"{program.genre_label or _genre_label(program.genre)} / {program.display_date}")
            self.selected_program_stats_var.set("")

    def _update_program_overview(
        self,
        program: Program | None,
        episodes: list[Episode] | None = None,
        message: str = "",
    ):
        if program is None:
            self.selected_program_title_var.set("")
            self.selected_program_meta_var.set("左の番組一覧から選択すると、ここに番組の概要が表示されます。")
            self.selected_program_stats_var.set("")
            return

        self.selected_program_title_var.set(program.display_title or program.title)
        meta = f"{program.genre_label or _genre_label(program.genre)} / 更新 {program.display_date}"
        if program.corner_id:
            meta += f" / ID {program.site_id}{program.corner_id}"
        self.selected_program_meta_var.set(meta)

        if episodes is not None:
            saved_count = sum(1 for e in episodes if is_episode_downloaded(self.output_dir, program, e))
            stats = f"{len(episodes)} エピソード (保存済み {saved_count})"
            if message:
                stats += f" | {message}"
            self.selected_program_stats_var.set(stats)
        else:
            self.selected_program_stats_var.set(message)

    def _on_program_search_change(self, *_args):
        if getattr(self, "_search_timer", None):
            try:
                self.root.after_cancel(self._search_timer)
            except (tk.TclError, ValueError):
                pass
        self._search_timer = self.root.after(250, self._apply_program_filters)

    def _clear_program_search(self, _event=None):
        self.program_search_var.set("")
        self.program_search_entry.focus_set()

    def _focus_program_tree_from_search(self, _event=None):
        self.program_tree.focus_set()
        selection = self.program_tree.selection()
        if not selection:
            children = self.program_tree.get_children()
            if children:
                self.program_tree.selection_set(children[0])

    def _commit_program_search(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        self._apply_program_filters()

    def _on_program_search_history_selected(self, _event=None):
        self._remember_program_search(self.program_search_var.get())
        self._apply_program_filters()

    def _on_program_search_focus_in(self, _event=None):
        self._update_program_search_history_values()

    def _on_program_search_focus_out(self, _event=None):
        # 入力が空でない場合は履歴に追加を試みる
        val = self.program_search_var.get()
        if val:
            self._remember_program_search(val)

    def _on_episode_filter_change(self, *_args):
        if self.displayed_program:
            self._render_episode_rows(self.displayed_program, self.displayed_episodes, clear_selection=False)

    def _clear_episode_search(self, _event=None):
        self.episode_search_var.set("")
        if hasattr(self, "episode_search_entry"):
            self.episode_search_entry.focus_set()
        return "break"

    def _clear_episode_filter(self, _event=None):
        return self._clear_episode_search(_event)

    def _sorted_programs(self, programs: list[Program]) -> list[Program]:
        col, reverse = self.program_sort_state
        if col == "no":
            return sorted(programs, key=lambda p: self.program_order_map.get(self._program_key(p), 0), reverse=reverse)
        if col == "date":
            return sorted(programs, key=lambda p: p.display_date or "", reverse=reverse)
        if col == "title":
            return sorted(programs, key=lambda p: p.display_title or p.title, reverse=reverse)
        return programs

    def _toggle_program_sort(self, col: str):
        current_col, current_reverse = self.program_sort_state
        if current_col == col:
            self.program_sort_state = (col, not current_reverse)
        else:
            self.program_sort_state = (col, False)
        self._update_program_tree_headings()
        self._populate_programs()

    def _update_program_tree_headings(self):
        for c in ["no", "date", "title"]:
            label = {"no": "No.", "date": "更新日", "title": "番組"}[c]
            if self.program_sort_state[0] == c:
                label += " ▲" if self.program_sort_state[1] else " ▼"
            self.program_tree.heading(c, text=label)

    def _sorted_episodes(self, episodes: list[Episode]) -> list[Episode]:
        # フィルタリング
        needle = self._normalized_search_text(self.episode_search_var.get())
        saved_only = self.episode_saved_only_var.get()
        
        filtered = episodes
        if needle:
            filtered = [e for e in filtered if needle in self._normalized_search_text(f"{e.title} {e.display_title}")]
        if saved_only and self.displayed_program:
            filtered = [e for e in filtered if is_episode_downloaded(self.output_dir, self.displayed_program, e)]

        # ソート
        col, reverse = self.episode_sort_state
        if col == "saved":
            # 保存済みを優先
            key_func = lambda e: is_episode_downloaded(self.output_dir, self.displayed_program, e) if self.displayed_program else False
        elif col == "date":
            key_func = lambda e: _sortable_timestamp_value(e.date)
        elif col == "duration":
            key_func = lambda e: _sortable_duration_value(e.duration_str)
        elif col == "title":
            key_func = lambda e: e.display_title or e.title
        else:
            return filtered
            
        return sorted(filtered, key=key_func, reverse=reverse)

    def _toggle_episode_sort(self, col: str):
        current_col, current_reverse = self.episode_sort_state
        if current_col == col:
            self.episode_sort_state = (col, not current_reverse)
        else:
            self.episode_sort_state = (col, False)
        self._update_episode_tree_headings()
        if self.displayed_program:
            self._render_episode_rows(self.displayed_program, self.displayed_episodes, clear_selection=False)

    def _update_episode_tree_headings(self):
        headers = {"saved": "DL", "date": "放送日時", "duration": "長さ", "title": "タイトル"}
        for c, base_label in headers.items():
            label = base_label
            if self.episode_sort_state[0] == c:
                label += " ▲" if self.episode_sort_state[1] else " ▼"
            self.episode_tree.heading(c, text=label)

    def _update_episode_filter_summary(self, count: int, total: int):
        self.episode_filter_summary_var.set(f"表示 {count} / 全 {total} 件")

    def _update_episode_selection_summary(self):
        count = len(self.episode_tree.selection())
        self.episode_selection_summary_var.set(f"選択 {count} 件")

    def _on_episode_selection_change(self, _event=None):
        self._update_episode_selection_summary()

    def _tree_label(self, tree: ttk.Treeview) -> str:
        if tree is self.program_tree:
            return "番組一覧"
        if tree is self.episode_tree:
            return "エピソード一覧"
        return "一覧"

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
        meta = f"{self._tree_label(tree)} / {heading}"
        self._update_selected_cell_ui(meta, value)
        if hasattr(self, "selected_cell_entry"):
            self.selected_cell_entry.xview_moveto(0)

    def _on_program_tree_click(self, event):
        cell = self._tree_cell_from_event(self.program_tree, event)
        if cell is None:
            return None
        _item_id, column_id, value = cell
        self._set_selected_tree_cell(self.program_tree, column_id, value)
        return None

    def _on_episode_tree_click(self, event):
        cell = self._tree_cell_from_event(self.episode_tree, event)
        if cell is None:
            return None
        _item_id, column_id, value = cell
        self._set_selected_tree_cell(self.episode_tree, column_id, value)
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

    def _select_program_item(self, item_id: str):
        self.program_tree.selection_set(item_id)
        self.program_tree.see(item_id)

    def _show_episodes(self, program: Program, episodes: list[Episode], message: str):
        self.displayed_program = program
        self.displayed_episodes = list(episodes)
        self.episode_title_var.set(f"エピソード一覧: {program.display_title or program.title}")
        self.episode_message_var.set(message)
        self._render_episode_rows(program, episodes, clear_selection=False)

    def _on_episode_tree_motion(self, event):
        pass

    def _on_episode_tree_leave(self, _event):
        pass

    def _on_episode_tree_configure(self, _event):
        pass

    def _on_episode_tree_scroll(self, *args):
        self.episode_tree.yview(*args)

    def _bind_tooltip(self, widget, text: str):
        widget.bind("<Enter>", lambda event: self._show_tooltip(event, text), add="+")
        widget.bind("<Motion>", self._move_tooltip, add="+")
        widget.bind("<Leave>", lambda _event: self._hide_tooltip(), add="+")
        widget.bind("<ButtonPress>", lambda _event: self._hide_tooltip(), add="+")

    def _show_tooltip(self, event, text: str):
        self._hide_tooltip()
        tooltip = tk.Toplevel(self.root)
        tooltip.wm_overrideredirect(True)
        
        # 背景色をパレットから取得
        p = self._palette
        label = tk.Label(
            tooltip,
            text=text,
            background=p.get("accent_soft", "#FFF4E6"),
            foreground=p.get("text", "#000000"),
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            font=getattr(self, "_ui_small", ("sans-serif", 10))
        )
        label.pack()
        self.tooltip_window = tooltip
        self.tooltip_label = label
        self._move_tooltip(event)

    def _move_tooltip(self, event):
        if not hasattr(self, "tooltip_window") or self.tooltip_window is None or not self.tooltip_window.winfo_exists():
            return
        x = event.x_root + 14
        y = event.y_root + 18
        self.tooltip_window.geometry(f"+{x}+{y}")

    def _hide_tooltip(self):
        if hasattr(self, "tooltip_window") and self.tooltip_window is not None and self.tooltip_window.winfo_exists():
            self.tooltip_window.destroy()
        self.tooltip_window = None
        self.tooltip_label = None


    def _on_episode_tree_yscroll(self, *args):
        # Treeview からスクロールバーへの通知
        self.episode_scroll.set(*args)

    def _focus_program_search(self, _event=None):
        if hasattr(self, "program_search_entry"):
            self.program_search_entry.focus_set()
        return "break"

    def _focus_episode_search(self, _event=None):
        if hasattr(self, "episode_search_entry"):
            self.episode_search_entry.focus_set()
        return "break"

    def _copy_selected_cell_to_clipboard(self, _event=None):
        val = self.selected_cell_value_var.get()
        if val:
            self.root.clipboard_clear()
            self.root.clipboard_append(val)
            self.status_var.set(f"コピーしました: {val[:20]}...")

    def _update_selected_cell_ui(self, meta: str, value: str):
        self.selected_cell_meta_var.set(meta)
        self.selected_cell_value_var.set(value)
        if hasattr(self, "copy_cell_button"):
            self.copy_cell_button.state(["!disabled"])


    def _cached_episodes_for(self, program: Program) -> list[Episode] | None:
        """指定した番組のキャッシュされたエピソードを返す。"""
        return self.data_manager.load_cached_episodes(program)


__all__ = ["GuiListingMixin"]

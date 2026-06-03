"""GUI programs Mixin — 番組ツリーの検索・フィルタ・ソート。"""

# mypy: disable-error-code="attr-defined,has-type,arg-type,assignment,misc,empty-body,return-value"

import logging
import tkinter as tk
import unicodedata
import webbrowser  # noqa: F401
from contextlib import suppress

from ...config import SEARCH_HISTORY_LIMIT
from ...constants import GENRE_LABELS, NHK_GENRES
from ...text import (
    _program_genre_labels,
    _program_genre_text,
)
from ...types import Program

logger = logging.getLogger(__name__)

_PROGRAM_INSERT_CHUNK = 50


class GuiProgramsMixin:
    """Logic for program listing, filtering, and selection."""

    # Mixin properties to help type checker
    if False:
        from ..browser import EpisodeGuiBrowser
        self = EpisodeGuiBrowser()

    def _on_program_filter_change(self, *_args):
        if not hasattr(self, "program_tree"):
            return
        self._apply_program_filters()

    def _update_program_genre_filter_values(self):
        if hasattr(self, "program_genre_filter_combo"):
            values = tuple(self._program_genre_filter_values())
            if tuple(self.program_genre_filter_combo.cget("values")) != values:
                self.program_genre_filter_combo.configure(values=values)

    def _apply_program_filters(self):
        needle = self._normalized_search_text(self.program_search_var.get())
        genre_filter = self.program_genre_filter_var.get()
        filtered = list(self.programs)
        if genre_filter and genre_filter != "すべて":
            filtered = [
                program
                for program in filtered
                if genre_filter in _program_genre_labels(program)
            ]
        if needle:
            filtered = [program for program in filtered if needle in self._program_search_target(program)]
        self.filtered_programs = filtered
        self._update_program_search_history_values()
        self._update_program_genre_filter_values()
        self._populate_programs()

    def _populate_programs(self, preserve_selection: bool = True):
        self._update_program_genre_filter_values()
        current_key = None
        if preserve_selection:
            current_program = self._selected_program()
            current_key = (
                self._program_key(current_program)
                if current_program is not None
                else self.selected_program_key
            )
        programs = self._sorted_programs(self.filtered_programs)
        self.program_tree_programs.clear()
        for item_id in self.program_tree.get_children():
            self.program_tree.delete(item_id)

        self._populate_generation = getattr(self, "_populate_generation", 0) + 1
        generation = self._populate_generation

        def _insert_chunk(start: int, selected_so_far: str) -> None:
            if self._populate_generation != generation:
                return
            chunk = programs[start : start + _PROGRAM_INSERT_CHUNK]
            sel = selected_so_far
            for i, program in enumerate(chunk):
                idx = start + i
                item_id = f"program-{idx}"
                self.program_tree.insert(
                    "",
                    "end",
                    iid=item_id,
                    values=(
                        self.program_order_map.get(self._program_key(program), idx + 1),
                        program.display_date or "----",
                        program.display_title or program.title,
                    ),
                )
                self.program_tree_programs[item_id] = program
                if current_key is not None and self._program_key(program) == current_key:
                    sel = item_id
            next_start = start + _PROGRAM_INSERT_CHUNK
            if next_start < len(programs):
                self.root.after(0, lambda s=sel: _insert_chunk(next_start, s))
            else:
                _finalize(sel)

        def _finalize(selected_item_id: str) -> None:
            if self._populate_generation != generation:
                return
            if selected_item_id:
                self.program_tree.selection_set(selected_item_id)
                self.program_tree.see(selected_item_id)
                self.selected_program_key = self._program_key(
                    self.program_tree_programs.get(selected_item_id)
                )
            elif programs:
                self.program_tree.selection_set("program-0")
                self.program_tree.see("program-0")
                self.selected_program_key = self._program_key(
                    self.program_tree_programs.get("program-0")
                )
            else:
                self.selected_program_key = None
            self.program_list_summary_var.set(
                f"{len(programs)} / {len(self.programs)} 番組"
                + (" (検索中)" if len(programs) < len(self.programs) else "")
            )

        if programs:
            _insert_chunk(0, "")
        else:
            _finalize("")

    def _program_genre_filter_values(self) -> list[str]:
        seen_labels = list(
            dict.fromkeys(
                label
                for program in self.programs
                for label in _program_genre_labels(program)
                if label != "未分類"
            )
        )
        ordered = [GENRE_LABELS[g] for g in NHK_GENRES if GENRE_LABELS[g] in seen_labels]
        remaining = [label for label in seen_labels if label not in ordered]
        return ["すべて", *ordered, *remaining, "未分類"]

    def _normalized_search_text(self, text: str) -> str:
        if not text:
            return ""
        return unicodedata.normalize("NFKC", text).casefold().strip()

    def _program_search_target(self, program: Program) -> str:
        text = (
            f"{program.title} {program.display_title} {program.corner_name or ''} "
            f"{' '.join(_program_genre_labels(program))}"
        )
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
            self.selected_program_key = self._program_key(program)
            # 概要を即座に更新
            self._update_program_overview(program, None, "詳細を読み込み中...")
            self.selected_program_title_var.set(program.display_title or program.title)
            self.selected_program_meta_var.set(f"{_program_genre_text(program)} / {program.display_date}")
            self.selected_program_stats_var.set("")

    def _update_program_overview(
        self,
        program: Program | None,
        episodes = None,
        message: str = "",
    ):
        if program is None:
            self.selected_program_title_var.set("")
            self.selected_program_meta_var.set("左の番組一覧から選択すると、ここに番組の概要が表示されます。")
            self.selected_program_stats_var.set("")
            return

        self.selected_program_title_var.set(program.display_title or program.title)
        meta = f"{_program_genre_text(program)} / 更新 {program.display_date}"
        if program.corner_id:
            meta += f" / ID {program.site_id}{program.corner_id}"
        self.selected_program_meta_var.set(meta)

        if episodes is not None:
            # バッチ判定で全エピソードの保存状態を効率的に取得
            from ...downloads import get_downloaded_episode_keys
            downloaded_keys = get_downloaded_episode_keys(self.output_dir, program, episodes)
            saved_count = len(downloaded_keys)
            stats = f"{len(episodes)} エピソード (保存済み {saved_count})"
            if message:
                stats += f" | {message}"
            self.selected_program_stats_var.set(stats)
        else:
            self.selected_program_stats_var.set(message)

    def _on_program_search_change(self, *_args):
        if getattr(self, "_search_timer", None):
            with suppress(tk.TclError, ValueError):
                self.root.after_cancel(self._search_timer)
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

    def _on_program_tree_click(self, event):
        cell = self._tree_cell_from_event(self.program_tree, event)
        if cell:
            item_id, col, _value = cell
            if col == "title":
                self._set_selected_tree_cell(self.program_tree, col, _value)

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
        self.selected_program_key = self._program_key(self.program_tree_programs.get(item_id))

    def _focus_program_search(self, _event=None):
        if hasattr(self, "program_search_entry"):
            self.program_search_entry.focus_set()
        return "break"

    def _open_nhk_program_page(self):
        """NHK 番組ページをブラウザで開く。"""
        if self.displayed_program is None:
            self.status_var.set("番組が選択されていません。")
            return

        from ...constants import NHK_DETAIL_TMPL

        program = self.displayed_program
        url = program.url or NHK_DETAIL_TMPL.format(
            site_id=program.site_id, corner_id=program.corner_id
        )

        try:
            webbrowser.open(url)
            self.status_var.set(f"番組ページを開きました: {program.display_title or program.title}")
        except Exception as e:
            self.status_var.set(f"ブラウザを開く際にエラーが発生しました: {e}")

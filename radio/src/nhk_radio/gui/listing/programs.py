"""GUI programs Mixin — 番組ツリーの検索・フィルタ・ソート。"""

import logging
import tkinter as tk
import webbrowser  # noqa: F401
from contextlib import suppress
from typing import TYPE_CHECKING

from ...config import SEARCH_HISTORY_LIMIT
from ...constants import GENRE_LABELS, NHK_GENRES
from ...text import (
    _program_genre_labels,
    _program_genre_text,
)
from ...types import Program

if TYPE_CHECKING:
    from ..protocols import GuiBrowserProtocol

logger = logging.getLogger(__name__)

class GuiProgramsMixin:
    """Logic for program listing, filtering, and selection."""

    if TYPE_CHECKING:
        # 型チェック時に self の型をアノテート
        self: "GuiBrowserProtocol"

    def _on_program_filter_change(self, *_args):
        if not hasattr(self, "program_tree"):
            return
        self._apply_program_filters()

    def _update_program_genre_filter_values(self):
        if hasattr(self, "program_view"):
            self.program_view.set_genres(self._program_genre_filter_values())

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
            current_key = self._program_key(current_program) if current_program is not None else self.selected_program_key
        programs = self._sorted_programs(self.filtered_programs)
        self.program_view.render(
            programs,
            len(self.programs),
            current_key,
            self.program_order_map,
            self._program_key,
            lambda key: setattr(self, "selected_program_key", key),
        )
        self._populate_generation = self.program_view.generation

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

    def _program_search_target(self, program: Program) -> str:
        text = (
            f"{program.title} {program.display_title} {program.corner_name or ''} "
            f"{' '.join(_program_genre_labels(program))}"
        )
        return self._normalized_search_text(text)

    def _update_program_search_history_values(self):
        if hasattr(self, "program_view"):
            self.program_view.set_search_history(self.program_search_history)

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
        self._persist_search_history()

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
            self._refresh_fetch_button_label()
            # 表示中のエピソード一覧と同じ番組なら何もしない (再描画時の選択イベント対策)
            if self._program_key(self.displayed_program) == self.selected_program_key:
                return
            # 一覧を選択中の番組に揃え、別番組のエピソードを誤って DL しないようにする (H1)
            cached = self._cached_episodes_for(program)
            if cached:
                self._update_program_overview(program, cached, "キャッシュ表示")
                self._show_episodes(program, cached, message=f"キャッシュから {len(cached)} 件を表示中")
            else:
                self._update_program_overview(program, None, "一覧は未取得です")
                self._show_episodes(program, [], message="「一覧を取得」(F) でエピソードを取得してください")

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
            downloaded_keys = get_downloaded_episode_keys(
                self.output_dir, program, episodes, audio_only=self.audio_only
            )
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
        self.program_view.update_headings(self.program_sort_state)

    def _on_program_tree_click(self, event):
        cell = self._tree_cell_from_event(self.program_tree, event)
        if cell:
            item_id, col, _value = cell
            # col は "#3" 形式の列 ID で返る (F1)
            if col == "#3":
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

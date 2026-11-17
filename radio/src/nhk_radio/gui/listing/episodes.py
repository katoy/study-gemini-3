"""GUI episodes Mixin — エピソードツリーの表示・検索・フィルタ。"""

import contextlib
import logging
import queue
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ...constants import CACHE_TTL_INFINITE
from ...downloads import _episode_key, get_downloaded_episode_keys
from ...text import _sortable_day_value, _sortable_duration_value, _sortable_timestamp_value
from ...types import Episode, Program

if TYPE_CHECKING:
    from ..protocols import GuiBrowserProtocol

logger = logging.getLogger(__name__)


class GuiEpisodeMixin:
    """Logic for episode listing, filtering, and selection."""

    if TYPE_CHECKING:
        self: GuiBrowserProtocol

    def _render_episode_rows(self, program: Program, episodes: list[Episode], clear_selection: bool = True):
        preserved_keys = ()
        if not clear_selection:
            preserved_keys = self._selected_episode_keys() or self.selected_episode_keys
        rendered = self._sorted_episodes(episodes)
        to_check, self.selected_episode_keys = self.episode_view.render_rows(
            rendered,
            total_count=len(episodes),
            clear_selection=clear_selection,
            preserved_keys=preserved_keys,
        )
        # 保存状態はメモリ上のキャッシュから付ける。UI スレッドではファイル I/O をしない (G13)
        saved_keys = self.displayed_saved_keys
        for iid, episode in to_check:
            self.episode_view.set_saved(iid, _episode_key(episode) in saved_keys)
        self._schedule_saved_button_refresh()

    def _reset_saved_keys(self) -> None:
        """表示中の番組の保存状態のキャッシュを空にする (番組が変わったときなど)。"""
        self.displayed_saved_keys = set[str]()
        self.saved_keys_program_key = None

    def _start_saved_keys_refresh(self) -> None:
        """表示中の番組の全エピソードの保存状態を、バックグラウンドで判定し直す (G13)。

        結果はキュー経由で UI スレッドの _poll_saved_keys が受け取り、_apply_saved_keys で反映する。
        世代番号で、古い番組や古い判定の結果を捨てる。
        """
        program = self.displayed_program
        if program is None:
            return
        self.saved_keys_generation += 1
        generation = self.saved_keys_generation
        episodes = list(self.displayed_episodes)

        import threading

        threading.Thread(
            target=self._saved_keys_worker, args=(program, episodes, generation), daemon=True
        ).start()
        if self.saved_keys_poll_id is None:
            self.saved_keys_poll_id = self.root.after(50, self._poll_saved_keys)

    def _saved_keys_worker(self, program: Program, episodes: list[Episode], generation: int) -> None:
        """バックグラウンドで保存状態を判定し、結果をキューに入れる。"""
        try:
            keys: set[str] | None = get_downloaded_episode_keys(
                self.output_dir, program, episodes, audio_only=self.audio_only
            )
        except Exception as e:
            logger.warning(f"保存状態の判定に失敗しました: {e}")
            keys = None
        self.saved_keys_queue.put((program, generation, keys))

    def _poll_saved_keys(self) -> None:
        """保存状態の判定結果を受け取り、最新の判定の結果だけを反映する。"""
        self.saved_keys_poll_id = None
        latest_received = False
        while True:
            try:
                program, generation, keys = self.saved_keys_queue.get_nowait()
            except queue.Empty:
                break
            if generation != self.saved_keys_generation:
                continue
            latest_received = True
            if keys is not None and self._program_key(program) == self._program_key(self.displayed_program):
                self._apply_saved_keys(program, keys)
        if not latest_received:
            self.saved_keys_poll_id = self.root.after(50, self._poll_saved_keys)

    def _apply_saved_keys(self, program: Program, keys: set[str]) -> None:
        """判定した保存状態をキャッシュに入れ、DL 列・ボタン・概要・一覧に反映する。"""
        self.displayed_saved_keys = set(keys)
        self.saved_keys_program_key = self._program_key(program)
        for iid, episode in self.displayed_episode_map.items():
            self.episode_view.set_saved(iid, _episode_key(episode) in self.displayed_saved_keys)
        was_saved_only = self.episode_saved_only_var.get()
        self._refresh_saved_only_button_state()
        self._refresh_program_overview_stats()
        # 保存状態で絞り込み・並べ替えをしているときは、一覧を描き直す
        if was_saved_only or self.episode_saved_only_var.get() or self.episode_sort_state[0] == "saved":
            self._render_episode_rows(program, self.displayed_episodes, clear_selection=False)

    def _rerender_displayed_episodes(self):
        if self.displayed_program is None:
            return
        self._render_episode_rows(self.displayed_program, self.displayed_episodes, clear_selection=True)

    def _refresh_downloaded_column(self, program: Program):
        """ダウンロード完了や削除の後に、保存状態をバックグラウンドで判定し直す (G13)。"""
        if self.displayed_program is None:
            return
        self._start_saved_keys_refresh()

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

        # 保存状態はメモリ上のキャッシュから判断する (G13)
        has_saved = bool(self.displayed_program and self.displayed_episodes and self.displayed_saved_keys)

        if has_saved:
            self.episode_saved_only_check.state(["!disabled"])
        else:
            self.episode_saved_only_check.state(["disabled"])
            if self.episode_saved_only_var.get():
                self.episode_saved_only_var.set(False)

    def _on_episode_filter_change(self, *_args):
        if getattr(self, "_episode_search_timer", None):
            with contextlib.suppress(tk.TclError, ValueError):
                self.root.after_cancel(self._episode_search_timer)
        self._episode_search_timer = self.root.after(150, self._apply_episode_filter)

    def _apply_episode_filter(self):
        if self.displayed_program:
            self._render_episode_rows(self.displayed_program, self.displayed_episodes, clear_selection=False)

    def _clear_episode_search(self, _event=None):
        self.episode_search_var.set("")
        # set("") の trace でスケジュールされたタイマーを確実にキャンセルして二重描画を防止 (2-3)
        if getattr(self, "_episode_search_timer", None):
            with contextlib.suppress(tk.TclError, ValueError):
                self.root.after_cancel(self._episode_search_timer)
            self._episode_search_timer = None
        self._apply_episode_filter()
        if hasattr(self, "episode_search_entry"):
            self.episode_search_entry.focus_set()
        return "break"

    def _clear_episode_filter(self, _event=None):
        return self._clear_episode_search(_event)

    def _sorted_episodes(self, episodes: list[Episode]) -> list[Episode]:
        # フィルタリング
        needle = self._normalized_search_text(self.episode_search_var.get())
        saved_only = self.episode_saved_only_var.get()

        # 保存状態はメモリ上のキャッシュを使う。入力のたびにファイル I/O をしない (G13)
        downloaded_keys = self.displayed_saved_keys

        filtered = episodes
        if needle:
            filtered = [e for e in filtered if needle in self._normalized_search_text(f"{e.title} {e.display_title}")]
        if saved_only and self.displayed_program:
            filtered = [e for e in filtered if _episode_key(e) in downloaded_keys]

        # ソート
        col, reverse = self.episode_sort_state
        if col == "saved":
            # 保存済みを優先
            def key_func(episode: Episode) -> bool:
                return _episode_key(episode) in downloaded_keys
        elif col == "date":
            def key_func(episode: Episode):
                day_key = _sortable_day_value(episode.display_date or episode.date)
                if day_key[0] == 0:
                    ts_key = _sortable_timestamp_value(episode.date)
                    return (ts_key[0], ts_key[1], episode.broadcast_time or "")
                return (day_key[0], float(day_key[1]), episode.broadcast_time or "")
        elif col == "duration":
            def key_func(episode: Episode):
                return _sortable_duration_value(episode.duration_str)
        elif col == "title":
            def key_func(episode: Episode) -> str:
                return episode.display_title or episode.title
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
        self.episode_view.update_headings(self.episode_sort_state)

    def _update_episode_filter_summary(self, count: int, total: int):
        self.episode_view.update_filter_summary(count, total)

    def _update_episode_selection_summary(self):
        self.episode_view.update_selection_summary()

    def _on_episode_selection_change(self, _event=None):
        self.selected_episode_keys = self._selected_episode_keys()
        self._update_episode_selection_summary()

    def _selected_episode_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        for item_id in self.episode_tree.selection():
            episode = self.displayed_episode_map.get(item_id)
            if episode is not None:
                keys.append(_episode_key(episode))
        return tuple(keys)

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

    def _on_episode_tree_click(self, event):
        cell = self._tree_cell_from_event(self.episode_tree, event)
        if cell is None:
            return None
        item_id, column_id, value = cell

        # ☑ マーク（保存済みインジケータ）クリックでデフォルトプレイヤーで再生
        # column_id は "#1"（saved カラムのインデックス）
        if column_id == "#1" and "☑" in str(value):
            self._play_episode_file(item_id)
            return "break"

        self._set_selected_tree_cell(self.episode_tree, column_id, value)
        return None

    def _show_episodes(self, program: Program, episodes: list[Episode], message: str):
        if self._program_key(self.displayed_program) != self._program_key(program):
            self.selected_episode_keys = ()
            # 前の番組の保存状態を使わない
            self._reset_saved_keys()
        self.displayed_program = program
        self.displayed_episodes = list(episodes)
        self.episode_title_var.set(f"エピソード一覧: {program.display_title or program.title}")
        self.episode_message_var.set(message)
        self._render_episode_rows(program, episodes, clear_selection=False)
        if episodes:
            self._start_saved_keys_refresh()

    def _on_episode_tree_motion(self, event):
        """マウスホバーで saved カラムの ☑ マークに hand cursor と tooltip を表示。"""
        cell = self._tree_cell_from_event(self.episode_tree, event)
        # column_id は "#1"（saved カラムのインデックス）
        if cell and cell[1] == "#1" and "☑" in str(cell[2]):
            self.episode_tree.config(cursor="hand2")
            self._show_tooltip(event, "クリック: 再生 | 右クリック: メニュー")
        else:
            self.episode_tree.config(cursor="")
            self._hide_tooltip()

    def _on_episode_tree_leave(self, _event):
        """マウスが tree を離れたら cursor と tooltip をリセット。"""
        self.episode_tree.config(cursor="")
        self._hide_tooltip()

    def _bind_tooltip(self, widget, text: str):
        widget.bind("<Enter>", lambda event: self._show_tooltip(event, text), add="+")
        widget.bind("<Motion>", self._move_tooltip, add="+")
        widget.bind("<Leave>", lambda _event: self._hide_tooltip(), add="+")
        widget.bind("<ButtonPress>", lambda _event: self._hide_tooltip(), add="+")

    def _show_tooltip(self, event, text: str):
        # マウスが動くたびに作り直さないよう、同じ文言なら位置だけ動かす (G12)
        if (
            self.tooltip_window is not None
            and self.tooltip_window.winfo_exists()
            and self.tooltip_label is not None
            and self.tooltip_label.cget("text") == text
        ):
            self._move_tooltip(event)
            return
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
        if hasattr(self, "selected_cell_area"):
            # セルをクリックしたときだけ選択セル欄を表示する (L2)
            self.selected_cell_area.grid()

    def _hide_selected_cell_area(self):
        """選択セル欄を空にして隠す (L2)。"""
        self.selected_cell_meta_var.set("")
        self.selected_cell_value_var.set("")
        self.copy_cell_button.state(["disabled"])
        self.selected_cell_area.grid_remove()

    def _cached_episodes_for(self, program: Program) -> list[Episode] | None:
        """指定した番組のキャッシュされたエピソードを返す。"""
        return self.data_manager.get_cached_episodes(program, ttl_seconds=CACHE_TTL_INFINITE)

"""Fetch and download helpers for EpisodeGuiBrowser, delegating logic to DownloadManager."""

import queue
import threading
import time
import webbrowser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols import GuiBrowserProtocol

from ..cache import clear_all_cache
from ..constants import NHK_ONDEMAND_URL
from ..downloads import _episode_key, program_output_dir
from ..types import Episode, Program


class GuiDownloadsMixin:
    """Delegates download logic to DownloadManager and handles UI updates."""

    if TYPE_CHECKING:
        self: "GuiBrowserProtocol"

    def _update_download_row_progress(
        self,
        episode_key: str,
        *,
        percent: float | None = None,
        eta: str | None = None,
        status_text: str | None = None,
    ):
        self.activity_view.update_progress(episode_key, percent=percent, eta=eta, status_text=status_text)

    def _update_fetch_button_state(self):
        if not hasattr(self, "fetch_button"):
            return
        if self.loading or self._selected_program() is None:
            self.fetch_button.state(["disabled"])
        else:
            self.fetch_button.state(["!disabled"])

    def _set_loading(self, loading: bool):
        self.loading = loading
        self._update_fetch_button_state()
        if loading:
            self.fetch_button_var.set("取得中...")
        else:
            self._refresh_fetch_button_label()

    def _refresh_fetch_button_label(self):
        """選択中の番組を取得済みなら「再取得」、未取得なら「一覧を取得」と表示する (L5)。"""
        if self.loading:
            return
        program = self._selected_program()
        fetched = program is not None and (program.site_id, program.corner_id) in self.episodes_cache
        self.fetch_button_var.set("再取得" if fetched else "一覧を取得")

    def _start_download_selected(self, _event=None):
        """UI event handler for Download button."""
        import tkinter.messagebox as mb

        # マウスのダブルクリックが ☑ 列 (saved: #1) で発生した場合はダウンロード処理を行わず終了 (G9)
        # キー操作 (<Return> 等) の場合はマウス座標に影響されないようスキップする
        is_mouse_click = _event is not None and (getattr(_event, "num", None) == 1 or not getattr(_event, "keysym", None))
        if is_mouse_click and hasattr(self, "episode_tree") and hasattr(self, "_tree_cell_from_event"):
            cell = self._tree_cell_from_event(self.episode_tree, _event)
            if cell and cell[1] == "#1":
                return "break"

        from ..downloads import find_episode_downloaded_path

        if self.displayed_program is None:
            return "break"

        selected_items = self.episode_tree.selection()
        if not selected_items:
            self.status_var.set("ダウンロードするエピソードを選択してください。")
            return "break"

        selected = [self.displayed_episode_map[iid] for iid in selected_items if iid in self.displayed_episode_map]
        if not selected:
            return "break"

        program = self.displayed_program

        # 既に保存済みのエピソードをチェック
        existing_episodes = []
        for episode in selected:
            path = find_episode_downloaded_path(
                self.output_dir, program, episode, audio_only=self.audio_only
            )
            if path is not None:
                existing_episodes.append((episode, path))

        # 上書き確認
        if existing_episodes:
            episode_names = "\n".join(f"  • {ep.display_title or ep.title}" for ep, _ in existing_episodes)
            if not mb.askyesno(
                "ファイルが既に存在します",
                f"以下のエピソードは既に保存済みです。\n上書きしてダウンロードしますか？\n\n{episode_names}",
                parent=self.root,
            ):
                return "break"
            # 注意: 事前の unlink は行わない。yt-dlp の --force-overwrites により安全に上書きされるため、
            # ダウンロード失敗時に元ファイルを失うことを防止する (G4)
        elif _event is not None and not mb.askyesno(
            "ダウンロードの確認",
            f"選択した {len(selected)} 件のエピソードをダウンロードしますか？",
            parent=self.root,
        ):
            # ダブルクリック / Enter による誤操作での即 DL を防ぐ (H3)
            return "break"

        new_jobs_count = 0
        for episode in selected:
            episode_key = _episode_key(episode)
            # すでに実行中でないか確認
            row = self.active_download_rows.get(episode_key)
            if row and row["state"] == "running":
                continue

            self._reset_download_row(episode_key)
            self._add_download_row(program, episode)
            self.download_manager.start_download(program, episode)
            new_jobs_count += 1

        if new_jobs_count > 0:
            self.status_var.set(f"「{program.display_title or program.title}」のダウンロードを開始しました ({new_jobs_count} 件)。")
            if not self.download_polling:
                self.download_polling = True
                self.root.after(100, self._poll_download_result)
        else:
            self.status_var.set("選択したエピソードはすでにダウンロード中です。")

        return "break"

    def _on_cancel_all(self):
        self.download_manager.cancel_all()
        self.status_var.set("すべてのダウンロードを中断しています...")

    def _on_cancel_one(self, episode_key: str):
        self.download_manager.cancel_download(episode_key)
        self.status_var.set("ダウンロードを中断しています...")

    def _poll_download_result(self):
        if not self.download_polling:
            return

        while True:
            try:
                event = self.download_result_queue.get_nowait()
            except queue.Empty:
                break

            kind, episode_key, program, episode, data = event

            if kind == "progress":
                percent, eta, status_text = data
                self._update_download_row_progress(episode_key, percent=percent, eta=eta, status_text=status_text)
                continue

            if kind == "done_one":
                self._finish_download_row(episode_key, "完了")
                self.status_var.set(f"ダウンロード完了: {episode.display_title or episode.title}")
                self.episode_message_var.set(f"保存先: {program_output_dir(self.output_dir, program)}")
                if (
                    self.displayed_program is not None
                    and self.displayed_program.site_id == program.site_id
                    and self.displayed_program.corner_id == program.corner_id
                ):
                    self._refresh_downloaded_column(program)
            elif kind == "failed_one":
                # data には失敗理由 (str) が入る。理由が取れない場合は None (F4)
                reason = data if isinstance(data, str) and data else None
                self._finish_download_row(episode_key, "失敗", program, episode, reason)
                title = episode.display_title or episode.title
                self.status_var.set(f"ダウンロード失敗: {title}" + (f" ({reason})" if reason else ""))
            elif kind == "cancelled_one":
                self._finish_download_row(episode_key, "中断", program, episode)
                self.status_var.set(f"ダウンロードを中断しました: {episode.display_title or episode.title}")

        if self.download_manager.is_active() or not self.download_result_queue.empty():
            # アクティブなダウンロード数に基づいて動的にポーリング間隔を調整
            # 3 個以上なら 50ms、1-2 個なら 100ms（複数ジョブでの応答性 vs CPU 使用率）
            active_count = len(self.download_manager.processes)
            poll_interval = 50 if active_count >= 3 else 100
            self.root.after(poll_interval, self._poll_download_result)
        else:
            self.download_polling = False

    def _start_fetch_selected(self, _event=None, silent: bool = False):
        if self.loading:
            return "break"

        program = self._selected_program()
        if program is None:
            return "break"

        if not silent:
            title = program.display_title or program.title
            self.status_var.set(f"「{title}」のエピソード一覧を取得中...")
            self.episode_message_var.set("取得中...")
            self._update_program_overview(program, None, "取得中")
            self._set_progress(0, 1, "")

        self._set_loading(True)
        self.data_manager.start_fetch_episodes(program)
        self.root.after(50, self._poll_fetch_result)
        return "break"

    def _poll_fetch_result(self):
        if self.fetch_result_queue is None:
            return

        try:
            program, episodes, source, error = self.fetch_result_queue.get_nowait()
        except queue.Empty:
            if self.loading:
                self.root.after(50, self._poll_fetch_result)
            return

        self._finish_fetch(program, episodes, source, error)

    def _finish_fetch(self, program: Program, episodes: list[Episode], source: str, error: str | None):
        self._set_loading(False)
        self._set_progress(0, 1, "")
        key = (program.site_id, program.corner_id)
        title = program.display_title or program.title
        if self.selected_program_key != self._program_key(program):
            # 取得中に別番組へ切り替えた場合は、選択中の番組の表示を上書きしない (H1)
            if error is None:
                self.episodes_cache[key] = (time.time(), episodes)
                self.episodes_cache.move_to_end(key)
                self.status_var.set(f"「{title}」の一覧取得が完了しました (表示は選択中の番組のまま)。")
            else:
                self.status_var.set(f"「{title}」の取得失敗: {error}")
        elif error is not None:
            # エラー時はキャッシュに空リストを書き込まない
            # （期限切れキャッシュが再利用できるようにするため）
            self.status_var.set(f"取得失敗: {error}")
            self._show_error_banner(f"取得に失敗しました: {error}")
            fallback = self._cached_episodes_for(program)
            if fallback:
                self._update_program_overview(program, fallback, "キャッシュ表示")
                self._show_episodes(
                    program, fallback, message=f"最新取得に失敗したためキャッシュを表示中 ({len(fallback)} 件)"
                )
            else:
                self._update_program_overview(program, None, "取得失敗")
                self._show_episodes(program, [], message="一覧は未取得です。取得に失敗しました。")
        else:
            self.episodes_cache[key] = (time.time(), episodes)
            self.episodes_cache.move_to_end(key)
            source_label = {"stale-cache": "期限切れキャッシュ"}.get(source, "最新取得")
            # 直前の操作結果を空文字で消さず、取得結果を表示する (M7)
            self.status_var.set(f"「{title}」のエピソード一覧を表示しました ({len(episodes)} 件)。")
            self._hide_error_banner()
            self._update_program_overview(program, episodes, source_label)
            self._show_episodes(program, episodes, message=f"{source_label}で {len(episodes)} 件を表示中")
            if episodes:
                self.episode_tree.focus_set()

        if len(self.episodes_cache) > 100:
            self.episodes_cache.popitem(last=False)
        self._refresh_fetch_button_label()

    def _clear_cache(self):
        import tkinter.messagebox as mb

        if self.loading:
            return
        if not mb.askyesno(
            "キャッシュを全削除",
            "番組一覧とエピソード一覧のキャッシュをすべて削除しますか？\n(保存済みの音声ファイルは削除されません)",
            parent=self.root,
        ):
            return
        self.status_var.set("キャッシュを削除中...")
        self._set_loading(True)

        def _worker():
            try:
                clear_all_cache()
                self.data_manager.clear_all_data()
                self.root.after(0, self._on_cache_cleared_success)
            except Exception as e:
                message = str(e)
                self.root.after(0, lambda: self._on_cache_cleared_error(message))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_cache_cleared_success(self):
        self._set_loading(False)
        self.status_var.set("キャッシュを削除しました。")
        self.episodes_cache.clear()
        self._reset_ui_state_after_cache_clear()

    def _on_cache_cleared_error(self, error: str):
        self._set_loading(False)
        self.status_var.set(f"キャッシュ削除失敗: {error}")

    def _open_ondemand_site(self, _event=None):
        webbrowser.open(NHK_ONDEMAND_URL)
        return "break"

    def _add_download_row(self, program: Program, episode: Episode):
        self.activity_view.add(episode)

    def _finish_download_row(
        self,
        episode_key: str,
        status: str,
        program: Program | None = None,
        episode: Episode | None = None,
        reason: str | None = None,
    ):
        on_retry = None
        if program is not None and episode is not None:
            on_retry = lambda: self._retry_download(program, episode)  # noqa: E731
        self.activity_view.finish(episode_key, status, on_retry, reason)

    def _retry_download(self, program: Program, episode: Episode):
        """失敗・中断したダウンロードを同じ番組・エピソードでやり直す (F4)。"""
        episode_key = _episode_key(episode)
        row = self.active_download_rows.get(episode_key)
        if row and row["state"] == "running":
            return
        self._reset_download_row(episode_key)
        self._add_download_row(program, episode)
        self.download_manager.start_download(program, episode)
        self.status_var.set(f"再試行しています: {episode.display_title or episode.title}")
        if not self.download_polling:
            self.download_polling = True
            self.root.after(100, self._poll_download_result)

    def _remove_download_row(self, episode_key: str):
        self.activity_view.remove(episode_key)

    def _reset_download_row(self, episode_key: str):
        self.activity_view.reset(episode_key)

    def _update_download_summary(self):
        self.activity_view._update_summary()

    def _reflow_download_rows(self, *, auto_scroll: bool = False):
        self.activity_view._reflow(auto_scroll=auto_scroll)

    def _show_error_banner(self, message: str) -> None:
        self.episode_view.show_error(message)

    def _hide_error_banner(self) -> None:
        self.episode_view.hide_error()


__all__ = ["GuiDownloadsMixin"]

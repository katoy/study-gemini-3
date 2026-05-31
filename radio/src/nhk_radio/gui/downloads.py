"""Fetch and download helpers for EpisodeGuiBrowser, delegating logic to DownloadManager."""

# mypy: disable-error-code="attr-defined,assignment,call-arg,empty-body"

import queue
import threading
import time
import webbrowser

from ..cache import clear_all_cache
from ..constants import NHK_ONDEMAND_URL
from ..downloads import (
    _episode_key,
    _format_download_eta,
    _format_download_percent,
    _program_output_dir,
)
from ..types import Episode, Program
from .toolkit import tk, ttk


class GuiDownloadsMixin:
    """Delegates download logic to DownloadManager and handles UI updates."""

    # Mixin properties to help type checker
    if False:
        from .browser import EpisodeGuiBrowser
        self = EpisodeGuiBrowser()

    def _update_download_row_progress(
        self,
        episode_key: str,
        *,
        percent: float | None = None,
        eta: str | None = None,
        status_text: str | None = None,
    ):
        def _update():
            row = self.active_download_rows.get(episode_key)
            if row is None or row["state"] != "running":
                return

            if percent is not None:
                row["percent_var"].set(_format_download_percent(percent))
                row["progress"].stop()
                row["progress"].configure(mode="determinate", maximum=100, value=min(max(percent, 0.0), 100.0))
                row["progress_meta_var"].set(f"{row['percent_var'].get()} / {_format_download_eta(eta)}")
            elif eta is not None:
                row["progress_meta_var"].set(f"{row['percent_var'].get()} / {_format_download_eta(eta)}")

            if status_text is not None:
                row["status_var"].set(status_text)

        self.root.after(0, _update)

    def _update_fetch_button_state(self):
        if not hasattr(self, "fetch_button"):
            return
        if self.loading or self._selected_program() is None:
            self.fetch_button.state(["disabled"])
        else:
            self.fetch_button.state(["!disabled"])

    def _set_loading(self, loading: bool, allow_cancel: bool = False):
        self.loading = loading
        self._update_fetch_button_state()
        if loading:
            self.fetch_button_var.set("取得を中止" if allow_cancel else "取得中...")
        else:
            self.fetch_button_var.set("一覧を取得")

    def _start_download_selected(self, _event=None):
        """UI event handler for Download button."""
        import tkinter.messagebox as mb

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
            path = find_episode_downloaded_path(self.output_dir, program, episode)
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

            # 既存ファイルを削除
            from ..downloads import remove_episode_from_manifest

            for episode, path in existing_episodes:
                try:
                    path.unlink()
                    remove_episode_from_manifest(self.output_dir, program, episode)
                except OSError as e:
                    self.status_var.set(f"既存ファイルの削除に失敗しました: {e}")
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
                self.episode_message_var.set(f"保存先: {_program_output_dir(self.output_dir, program)}")
                if (
                    self.displayed_program is not None
                    and self.displayed_program.site_id == program.site_id
                    and self.displayed_program.corner_id == program.corner_id
                ):
                    self._refresh_downloaded_column(program)
            elif kind == "failed_one":
                self._finish_download_row(episode_key, "失敗")
                self.status_var.set(f"ダウンロード失敗: {episode.display_title or episode.title}")
            elif kind == "cancelled_one":
                self._finish_download_row(episode_key, "中断")
                self.status_var.set(f"ダウンロードを中断しました: {episode.display_title or episode.title}")

        if self.download_manager.is_active():
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

        self._set_loading(True, allow_cancel=False)
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
        if error is not None:
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
            self.status_var.set("")
            self._hide_error_banner()
            self._update_program_overview(program, episodes, source_label)
            self._show_episodes(program, episodes, message=f"{source_label}で {len(episodes)} 件を表示中")
            if episodes:
                self.episode_tree.focus_set()

        if len(self.episodes_cache) > 100:
            self.episodes_cache.popitem(last=False)

    def _clear_cache(self):
        if self.loading:
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
        episode_key = _episode_key(episode)
        if episode_key in self.active_download_rows:
            return

        index = len(self.active_download_rows)
        widgets = self._create_download_job_widgets(index, episode, episode_key)
        self.active_download_rows[episode_key] = {
            "state": "running",
            **widgets,
        }
        self._reflow_download_rows(auto_scroll=True)

    def _finish_download_row(self, episode_key: str, status: str):
        row = self.active_download_rows.get(episode_key)
        if row is None:
            return

        row["state"] = "done"
        row["status_var"].set(status)
        row["progress"].stop()
        if status == "完了":
            row["progress"].configure(value=100)
            row["percent_var"].set("100%")

        # ボタンを「削除」に変更
        row["action_button"].configure(text="削除", command=lambda: self._remove_download_row(episode_key))
        self._update_download_summary()

    def _remove_download_row(self, episode_key: str):
        row = self.active_download_rows.pop(episode_key, None)
        if row:
            row["frame"].destroy()
            self._reflow_download_rows()
            self._update_download_summary()

    def _reset_download_row(self, episode_key: str):
        if episode_key in self.active_download_rows:
            self._remove_download_row(episode_key)

    def _update_download_summary(self):
        active = sum(1 for r in self.active_download_rows.values() if r["state"] == "running")
        total = len(self.active_download_rows)
        if total == 0:
            self.progress_text_var.set("ダウンロードジョブはありません")
        else:
            self.progress_text_var.set(f"実行中: {active} / 全体: {total}")

    def _reflow_download_rows(self, *, auto_scroll: bool = False):
        # Canvas 内のアイテムを上から順に再配置
        for i, row in enumerate(self.active_download_rows.values()):
            row["frame"].grid(row=i, column=0, sticky="ew", padx=5, pady=2)

        self.root.update_idletasks()
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))
        if auto_scroll:
            self.download_jobs_canvas.yview_moveto(1.0)

    def _create_download_job_widgets(self, index: int, episode: Episode, episode_key: str) -> dict:
        frame = ttk.Frame(self.download_jobs_inner, style="Card.TFrame")
        # column 1 (プログレスバー) が伸縮するように設定
        frame.columnconfigure(1, weight=1)

        title_label = ttk.Label(
            frame,
            text=episode.display_title or episode.title,
            style="Bold.TLabel"
        )
        title_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        status_var = tk.StringVar(value="準備中...")
        # 状態ラベルにもある程度の幅を持たせて安定させる
        status_label = ttk.Label(frame, textvariable=status_var, font=("", 9), width=10, anchor="e")
        status_label.grid(row=0, column=2, sticky="e", padx=10, pady=(10, 5))

        progress = ttk.Progressbar(frame, mode="indeterminate", length=200)
        progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        progress.start(10)

        percent_var = tk.StringVar(value="--%")
        progress_meta_var = tk.StringVar(value="--% / 残り --:--")
        # 進捗テキストラベルに固定幅 (width=22) を設定して、伸縮を防ぐ
        meta_label = ttk.Label(frame, textvariable=progress_meta_var, font=("", 9), width=22, anchor="e")
        meta_label.grid(row=1, column=2, sticky="e", padx=10, pady=5)

        action_button = ttk.Button(
            frame,
            text="中止",
            command=lambda: self._on_cancel_one(episode_key),
            width=8
        )
        action_button.grid(row=0, column=3, rowspan=2, padx=10, pady=10)

        return {
            "frame": frame,
            "status_var": status_var,
            "progress": progress,
            "percent_var": percent_var,
            "progress_meta_var": progress_meta_var,
            "action_button": action_button,
        }

    def _show_error_banner(self, message: str) -> None:
        """Display error banner with the given message."""
        self.error_banner_label.config(text=message)
        self.error_banner_frame.grid()

    def _hide_error_banner(self) -> None:
        """Hide error banner."""
        self.error_banner_frame.grid_remove()


__all__ = ["GuiDownloadsMixin"]

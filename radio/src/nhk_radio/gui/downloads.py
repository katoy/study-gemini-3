"""Fetch and download helpers for EpisodeGuiBrowser."""

import contextlib
import queue
import subprocess
import threading
import time
import webbrowser

from ..cache import clear_all_cache
from ..constants import NHK_ONDEMAND_URL
from ..core import fetch_program_list, refresh_episode_list
from ..downloads import (
    _download_episode_command,
    _episode_key,
    _format_download_eta,
    _format_download_percent,
    _parse_yt_dlp_progress,
    _program_filename_template,
    _program_output_dir,
    cleanup_partial_episode_files,
    mark_episode_downloaded,
    resolve_episode_downloaded_path,
)
from .toolkit import tk, ttk


class GuiDownloadsMixin:
    def _start_fetch_programs(self, genre: str | None = None):
        if self.loading:
            return

        self.status_var.set("番組一覧を取得中...")
        self._set_loading(True)
        self.program_fetch_queue = queue.Queue()
        worker = threading.Thread(target=self._fetch_programs_worker, args=(genre, self.program_fetch_queue), daemon=True)
        worker.start()
        self.root.after(50, self._poll_program_fetch_result)

    def _fetch_programs_worker(self, genre: str | None, result_queue: queue.Queue):
        try:
            programs = fetch_program_list(genre)
            error = None
        except Exception as e:
            programs = []
            error = str(e)
        result_queue.put((programs, error))

    def _poll_program_fetch_result(self):
        if self.program_fetch_queue is None:
            return

        try:
            programs, error = self.program_fetch_queue.get_nowait()
        except queue.Empty:
            if self.loading:
                self.root.after(50, self._poll_program_fetch_result)
            return

        self.program_fetch_queue = None
        self._finish_fetch_programs(programs, error)

    def _finish_fetch_programs(self, programs: list[Program], error: str | None):
        self._set_loading(False)
        if error is not None:
            self.status_var.set(f"番組一覧の取得に失敗しました: {error}")
            return

        self.programs = programs
        self.filtered_programs = list(programs)
        # ジャンル選択リストを更新
        if hasattr(self, "program_genre_filter_combo"):
            self.program_genre_filter_combo["values"] = self._program_genre_filter_values()
        # Treeview を再構築
        self._populate_programs(preserve_selection=False)
        self.program_list_summary_var.set(self._program_list_summary_text())
        self.status_var.set(f"{len(programs)} 件の番組を取得しました。")
        if programs:
            self.program_tree.focus_set()

    def _update_download_row_progress(
        self,
        episode_key: str,
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
        def _update():
            self.loading = loading
            if loading:
                self.clear_button.state(["disabled"])
                self.program_search_entry.state(["disabled"])
            else:
                self.clear_button.state(["!disabled"])
                self.program_search_entry.state(["!disabled"])
                self._update_fetch_button_state()
            if not self.displayed_episode_map or loading:
                self.download_button.state(["disabled"])
            else:
                self.download_button.state(["!disabled"])
            self.root.configure(cursor="watch" if loading else "")
            self.root.update_idletasks()

        self.root.after(0, _update)

    def _open_ondemand_site(self):
        try:
            webbrowser.open_new_tab(NHK_ONDEMAND_URL)
        except webbrowser.Error:
            self.status_var.set(f"ブラウザで開けませんでした: {NHK_ONDEMAND_URL}")
            return
        self.status_var.set("NHK ラジオ らじる★らじる 聞き逃しをブラウザで開きました。")

    def _set_progress(self, current: int, total: int, text: str = ""):
        def _update():
            nonlocal total
            total = max(total, 1)
            if text:
                self.progress_text_var.set(text)
            elif total <= 1 and current <= 0:
                self.progress_text_var.set("")
            else:
                self.progress_text_var.set(f"処理済: {current} 件 / 開始 {total} 件")

        self.root.after(0, _update)

    def _show_progress_window(self):
        self.download_jobs_canvas.focus_set()
        self.status_var.set("下部のダウンロード状況を確認してください。")

    def _hide_progress_window(self):
        return

    def _on_download_jobs_inner_configure(self, _event=None):
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))

    def _on_download_jobs_canvas_configure(self, event):
        self.download_jobs_canvas.itemconfigure(self.download_jobs_window, width=event.width)
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))
        self._update_download_job_title_wrap(event.width)

    def _on_download_jobs_mousewheel(self, event):
        if not self.active_download_rows:
            return "break"

        if hasattr(event, "delta") and event.delta:
            step = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            return None

        self.download_jobs_canvas.yview_scroll(step, "units")
        return "break"

    def _on_settings_inner_configure(self, _event=None):
        self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all"))

    def _on_settings_canvas_configure(self, event):
        self.settings_canvas.itemconfigure(self.settings_window, width=event.width)
        self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all"))

    def _on_settings_mousewheel(self, event):
        bbox = self.settings_canvas.bbox("all")
        if not bbox:
            return None
        if bbox[3] - bbox[1] <= self.settings_canvas.winfo_height():
            return None

        if hasattr(event, "delta") and event.delta:
            step = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            return None

        self.settings_canvas.yview_scroll(step, "units")
        return "break"

    def _reflow_download_rows(self):
        for row_index, row in enumerate(self.active_download_rows.values()):
            row["frame"].grid_configure(row=row_index)
        if self.active_download_rows:
            self.download_jobs_empty.grid_remove()
        else:
            self.download_jobs_empty.grid(row=0, column=0, sticky="w")
        self.download_jobs_canvas.configure(scrollregion=self.download_jobs_canvas.bbox("all"))

    def _update_download_job_title_wrap(self, width: int | None = None):
        if width is None:
            width = self.download_jobs_canvas.winfo_width()
        if width <= 1:
            return

        wraplength = max(width - 220, 260)
        for row in self.active_download_rows.values():
            title_label = row.get("title_label")
            if title_label is not None:
                title_label.configure(wraplength=wraplength)

    def _remove_download_row(self, episode_key: str):
        row = self.active_download_rows.get(episode_key)
        if row is None or row["state"] == "running":
            return
        row["frame"].destroy()
        self.active_download_rows.pop(episode_key, None)
        self.active_download_meta.pop(episode_key, None)
        self.download_cancel_events.pop(episode_key, None)
        self._reflow_download_rows()
        self._update_download_summary()

    def _update_download_summary(self):
        active = 0
        for row in self.active_download_rows.values():
            if row["state"] == "running":
                active += 1

        if active:
            total = max(self.download_started_count, 1)
            self._set_progress(
                self.download_finished_count,
                total,
                f"実行中 {active} 件 / 処理済 {self.download_finished_count} 件 / 開始 {self.download_started_count} 件",
            )
        elif self.download_started_count:
            self._set_progress(
                self.download_finished_count,
                max(self.download_started_count, 1),
                f"処理済: {self.download_finished_count} 件 / 開始 {self.download_started_count} 件",
            )
        else:
            self._set_progress(0, 1, "")

        if not self.active_download_rows and not self.loading:
            if self.displayed_episode_map:
                self.download_button.state(["!disabled"])
            else:
                self.download_button.state(["disabled"])

    def _add_download_row(self, program: Program, episode: Episode):
        episode_key = _episode_key(episode)
        if episode_key in self.active_download_rows:
            return episode_key

        self._show_progress_window()
        self.download_jobs_empty.grid_remove()
        row_index = len(self.active_download_rows)
        row_widgets = self._create_download_job_widgets(row_index, episode, episode_key)

        self.active_download_rows[episode_key] = {**row_widgets, "state": "running"}
        self.active_download_meta[episode_key] = (program, episode)
        self.download_started_count += 1
        self._update_download_summary()
        self._update_download_job_title_wrap()
        self.download_jobs_canvas.update_idletasks()
        self.download_jobs_canvas.yview_moveto(1.0)
        return episode_key

    def _reset_download_row(self, episode_key: str):
        row = self.active_download_rows.get(episode_key)
        if row is None:
            return
        if row["state"] == "running":
            return
        row["frame"].destroy()
        self.active_download_rows.pop(episode_key, None)
        self.active_download_meta.pop(episode_key, None)
        self.download_cancel_events.pop(episode_key, None)
        self._reflow_download_rows()
        self._update_download_summary()

    def _create_download_job_widgets(self, row_index: int, episode: Episode, episode_key: str) -> dict:
        """ダウンロードジョブ行のウィジェットを生成して辞書で返す。"""
        frame = ttk.Frame(self.download_jobs_inner, style="DownloadJob.TFrame", padding=(12, 10))
        frame.grid(row=row_index, column=0, sticky="ew", pady=2)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=0)
        frame.rowconfigure(1, weight=0)
        frame.rowconfigure(2, weight=0)

        title = ttk.Label(
            frame,
            text=episode.display_title or episode.title,
            anchor="w",
            justify="left",
            style="DownloadJobTitle.TLabel",
        )
        title.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        status_var = tk.StringVar(value="ダウンロード中...")
        action_button = ttk.Button(
            frame,
            text="中断",
            style="DownloadJobAction.TButton",
            command=lambda key=episode_key: self._cancel_download_job(key),
            width=6,
        )
        action_button.grid(row=0, column=1, rowspan=3, sticky="ns")
        progress = ttk.Progressbar(frame, orient="horizontal", mode="indeterminate")
        progress.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(8, 0))
        percent_var = tk.StringVar(value="--%")
        progress_meta_var = tk.StringVar(value=f"--%  /  {_format_download_eta(None)}")
        meta_row = ttk.Frame(frame, style="DownloadJob.TFrame")
        meta_row.grid(row=2, column=0, sticky="ew", padx=(0, 12), pady=(6, 0))
        meta_row.columnconfigure(1, weight=1)
        ttk.Label(meta_row, textvariable=status_var, anchor="w", style="DownloadJobStatus.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        ttk.Label(meta_row, textvariable=progress_meta_var, anchor="e", style="DownloadJobMeta.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        progress.start(12)
        return {
            "frame": frame,
            "progress": progress,
            "percent_var": percent_var,
            "progress_meta_var": progress_meta_var,
            "status_var": status_var,
            "action_button": action_button,
            "title_label": title,
        }

    def _finish_download_row(self, episode_key: str, status_text: str):
        row = self.active_download_rows.get(episode_key)
        if row is None:
            return
        if row["state"] != "running":
            return

        row["state"] = "done"
        row["progress"].stop()
        row["progress"].configure(mode="determinate", maximum=1, value=1)
        if status_text == "完了":
            row["percent_var"].set("100%")
            row["progress_meta_var"].set("100% / 残り 00:00")
        else:
            row["progress_meta_var"].set(f"{row['percent_var'].get()} / {_format_download_eta(None)}")
        row["status_var"].set(status_text)
        row["action_button"].configure(text="削除", command=lambda key=episode_key: self._remove_download_row(key))
        self.download_finished_count += 1
        self._update_download_summary()

    def _cancel_download_job(self, episode_key: str):
        cancel_event = self.download_cancel_events.get(episode_key)
        if cancel_event is None:
            return

        row = self.active_download_rows.get(episode_key)
        if row is not None and row["state"] == "running":
            row["status_var"].set("中断中...")

        cancel_event.set()
        with self.download_process_lock:
            process = self.download_processes.get(episode_key)
        if process is not None:
            with contextlib.suppress(Exception):
                process.terminate()

    def _start_fetch_selected(self, _event=None):
        if self.loading:
            return "break"

        program = self._selected_program()
        if program is None:
            return "break"

        title = program.display_title or program.title
        self.status_var.set(f"「{title}」のエピソード一覧を取得中...")
        self.episode_message_var.set("取得中...")
        self._update_program_overview(program, None, "取得中")
        self._set_progress(0, 1, "")
        self._set_loading(True, allow_cancel=False)
        self.fetch_result_queue = queue.Queue()
        worker = threading.Thread(target=self._fetch_worker, args=(program, self.fetch_result_queue), daemon=True)
        worker.start()
        self.root.after(50, self._poll_fetch_result)
        return "break"

    def _fetch_worker(self, program: Program, result_queue: queue.Queue):
        try:
            episodes, source = refresh_episode_list(program)
            error = None
        except Exception as e:
            episodes = []
            source = ""
            error = str(e)
        result_queue.put((program, episodes, source, error))

    def _poll_fetch_result(self):
        if self.fetch_result_queue is None:
            return

        try:
            program, episodes, source, error = self.fetch_result_queue.get_nowait()
        except queue.Empty:
            if self.loading:
                self.root.after(50, self._poll_fetch_result)
            return

        self.fetch_result_queue = None
        self._finish_fetch(program, episodes, source, error)

    def _finish_fetch(self, program: Program, episodes: list[Episode], source: str, error: str | None):
        self._set_loading(False)
        self._set_progress(0, 1, "")
        key = (program.site_id, program.corner_id)
        if error is not None:
            self.episodes_cache[key] = (time.time(), [])
            self.status_var.set(f"取得失敗: {error}")
            fallback = self._cached_episodes_for(program)
            if fallback:
                self._update_program_overview(program, fallback, "キャッシュ表示")
                self._show_episodes(
                    program, fallback, message=f"最新取得に失敗したためキャッシュを表示中 ({len(fallback)} 件)"
                )
            else:
                self._update_program_overview(program, None, "取得失敗")
                self._show_episodes(program, [], message="一覧は未取得です。取得に失敗しました。")
            return

        self.episodes_cache[key] = (time.time(), episodes)
        source_label = {"stale-cache": "期限切れキャッシュ"}.get(source, "最新取得")
        self.status_var.set("")
        self._update_program_overview(program, episodes, source_label)
        self._show_episodes(program, episodes, message=f"{source_label}で {len(episodes)} 件を表示中")
        if episodes:
            self.episode_tree.focus_set()

    def _clear_cache(self):
        if self.loading:
            return
        removed = clear_all_cache()
        self.episodes_cache.clear()
        self._reset_ui_state_after_cache_clear()
        self.status_var.set(f"キャッシュを削除しました ({removed} 件)")
        self._on_program_select()

    def _start_download_selected(self, _event=None):
        if self.loading:
            return "break"
        if self.displayed_program is None:
            self.status_var.set("番組を選択してください。")
            return "break"

        selected = [
            self.displayed_episode_map[iid]
            for iid in self.episode_tree.selection()
            if iid in self.displayed_episode_map
        ]
        if not selected:
            self.status_var.set("下段でダウンロード対象を選択してください。")
            return "break"

        program = self.displayed_program
        new_jobs = []
        duplicate_count = 0
        for episode in selected:
            episode_key = _episode_key(episode)
            if (
                episode_key in self.active_download_rows
                and self.active_download_rows[episode_key]["state"] == "running"
            ):
                duplicate_count += 1
                continue
            self._reset_download_row(episode_key)
            self.download_cancel_events[episode_key] = threading.Event()
            self._add_download_row(program, episode)
            new_jobs.append((episode_key, episode))

        if not new_jobs:
            self.status_var.set("選択したエピソードはすでにダウンロード中です。")
            return "break"

        started = len(new_jobs)
        self.status_var.set(f"「{program.display_title or program.title}」のダウンロードを開始しました。")
        self.episode_message_var.set(
            f"開始 {started} 件" + (f" / 既に実行中 {duplicate_count} 件" if duplicate_count else "")
        )
        for episode_key, episode in new_jobs:
            worker = threading.Thread(
                target=self._download_one_worker,
                args=(program, episode, episode_key, self.download_cancel_events[episode_key]),
                daemon=True,
            )
            worker.start()

        if not self.download_polling:
            self.download_polling = True
            self.root.after(100, self._poll_download_result)
        return "break"

    def _download_one_worker(
        self,
        program: Program,
        episode: Episode,
        episode_key: str,
        cancel_event: threading.Event,
    ):
        output_dir = _program_output_dir(self.output_dir, program)
        filename_template = _program_filename_template(program)
        if cancel_event.is_set():
            self.download_result_queue.put(("canceled_one", episode_key, program, episode))
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            _download_episode_command(episode.url, output_dir, filename_template, audio_only=self.audio_only),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with self.download_process_lock:
            self.download_processes[episode_key] = process

        success, canceled = self._monitor_download_process(process, episode_key, cancel_event, program, episode)

        if canceled:
            self.download_result_queue.put(("canceled_one", episode_key, program, episode))
            return
        if success:
            # OS のファイル書き込み完了を少し待つ
            downloaded_path = None
            for _ in range(3):
                downloaded_path = resolve_episode_downloaded_path(self.output_dir, program, episode)
                if downloaded_path:
                    break
                time.sleep(0.2)

            mark_episode_downloaded(self.output_dir, program, episode, downloaded_path)
            self.download_result_queue.put(("done_one", episode_key, program, episode))
        else:
            cleanup_partial_episode_files(self.output_dir, program, episode)
            self.download_result_queue.put(("failed_one", episode_key, program, episode))

    def _monitor_download_process(
        self,
        process: subprocess.Popen,
        episode_key: str,
        cancel_event: threading.Event,
        program: Program,
        episode: Episode,
    ) -> tuple[bool, bool]:
        """プロセスの出力を監視し、進捗をキューに送る。(success, canceled) を返す。"""
        process_output_queue: queue.Queue[str | None] = queue.Queue()

        def _read_output():
            if process.stdout is None:
                process_output_queue.put(None)
                return
            try:
                for line in process.stdout:
                    process_output_queue.put(line)
            finally:
                process.stdout.close()
                process_output_queue.put(None)

        threading.Thread(target=_read_output, daemon=True).start()

        success = False
        canceled = False
        output_closed = False
        last_progress: tuple[str, str, str] | None = None
        try:
            while True:
                if cancel_event.is_set():
                    canceled = True
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    cleanup_partial_episode_files(self.output_dir, program, episode)
                    break

                try:
                    line = process_output_queue.get(timeout=0.1)
                except queue.Empty:
                    line = None
                else:
                    if line is None:
                        output_closed = True
                    else:
                        percent, eta, status_text = _parse_yt_dlp_progress(line)
                        if percent is not None or eta is not None or status_text is not None:
                            progress_event = (
                                _format_download_percent(percent),
                                _format_download_eta(eta),
                                status_text or "",
                            )
                            if progress_event != last_progress:
                                self.download_result_queue.put(("progress_one", episode_key, percent, eta, status_text))
                                last_progress = progress_event

                returncode = process.poll()
                if returncode is not None and output_closed:
                    success = returncode == 0
                    break
        finally:
            with self.download_process_lock:
                self.download_processes.pop(episode_key, None)

        return success, canceled

    def _poll_download_result(self):
        if not self.download_polling:
            return

        while True:
            try:
                event = self.download_result_queue.get_nowait()
            except queue.Empty:
                break

            kind = event[0]
            if kind == "progress_one":
                _, episode_key, percent, eta, status_text = event
                self._update_download_row_progress(episode_key, percent=percent, eta=eta, status_text=status_text)
                continue
            if kind == "done_one":
                _, episode_key, program, episode = event
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
                _, episode_key, program, episode = event
                self._finish_download_row(episode_key, "失敗")
                self.status_var.set(f"ダウンロード失敗: {episode.display_title or episode.title}")
                self.episode_message_var.set(f"保存先: {_program_output_dir(self.output_dir, program)}")
            elif kind == "canceled_one":
                _, episode_key, program, episode = event
                self._finish_download_row(episode_key, "中断")
                self.status_var.set(f"ダウンロードを中断しました: {episode.display_title or episode.title}")
                self.episode_message_var.set("中断したエピソードの途中ファイルは削除しました。")

            self.download_cancel_events.pop(event[1], None)
            self.active_download_meta.pop(event[1], None)

        active_running = any(row["state"] == "running" for row in self.active_download_rows.values())
        if active_running:
            self.root.after(100, self._poll_download_result)
        else:
            self.download_polling = False


__all__ = ["GuiDownloadsMixin"]

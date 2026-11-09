"""Download activity panel and its local presentation state."""

from collections.abc import Callable
from typing import Any

from ..downloads import _episode_key, _format_download_eta, _format_download_percent
from ..types import Episode
from .toolkit import tk, ttk


class ActivityView:
    """Own the download rows; callers supply only download cancellation."""

    def __init__(
        self,
        root: tk.Tk,
        parent: ttk.Panedwindow,
        progress_text_var: tk.StringVar,
        create_scrollable_frame: Callable[..., tuple[Any, Any, Any, Any]],
        on_cancel_one: Callable[[str], None],
    ) -> None:
        self.root = root
        self.progress_text_var = progress_text_var
        self.on_cancel_one = on_cancel_one
        self.rows: dict[str, dict[str, Any]] = {}

        activity = ttk.Frame(parent, style="Card.TFrame", padding=6, height=140)
        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(1, weight=1)
        self.progress_label = ttk.Label(
            activity, textvariable=progress_text_var, anchor="w", style="CardMeta.TLabel"
        )
        self.progress_label.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        # 完了・失敗・中断した行をまとめて消す (F4)
        self.clear_finished_button = ttk.Button(
            activity, text="完了分をクリア", command=self.clear_finished, style="Quiet.TButton"
        )
        self.clear_finished_button.grid(row=0, column=1, sticky="e", pady=(0, 4))
        self.clear_finished_button.state(["disabled"])
        self.jobs_frame = ttk.Frame(activity, padding=2)
        self.jobs_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.jobs_frame.columnconfigure(0, weight=1)
        self.jobs_frame.rowconfigure(0, weight=1)
        self.canvas, self.scrollbar, self.inner, self.window = create_scrollable_frame(
            self.jobs_frame, "CardInner.TFrame"
        )
        self.empty_label = ttk.Label(
            self.inner, text="実行中のダウンロードはありません。", style="CardMeta.TLabel"
        )
        self.empty_label.grid(row=0, column=0, sticky="w")
        parent.add(activity, weight=1)
        self.frame = activity

    def update_progress(
        self,
        episode_key: str,
        *,
        percent: float | None = None,
        eta: str | None = None,
        status_text: str | None = None,
    ) -> None:
        def update() -> None:
            row = self.rows.get(episode_key)
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

        self.root.after(0, update)

    def add(self, episode: Episode) -> None:
        episode_key = _episode_key(episode)
        if episode_key in self.rows:
            return
        widgets = self._create_job_widgets(episode, episode_key)
        self.rows[episode_key] = {"state": "running", **widgets}
        self._reflow(auto_scroll=True)

    def finish(self, episode_key: str, status: str, on_retry: Callable[[], None] | None = None) -> None:
        """行を終了状態にする。on_retry を渡すと「再試行」ボタンを出す (F4)。"""
        row = self.rows.get(episode_key)
        if row is None:
            return
        row["state"] = "done"
        row["status_var"].set(status)
        row["progress"].stop()
        if status == "完了":
            row["progress"].configure(value=100)
            row["percent_var"].set("100%")
        if on_retry is not None:
            # 失敗・中断した行はその場でやり直せるようにする (行の削除は「完了分をクリア」で行う)
            row["action_button"].configure(text="再試行", command=on_retry)
        else:
            row["action_button"].configure(text="削除", command=lambda: self.remove(episode_key))
        self._update_summary()

    def remove(self, episode_key: str) -> None:
        row = self.rows.pop(episode_key, None)
        if row:
            row["frame"].destroy()
            self._reflow()
            self._update_summary()

    def clear_finished(self) -> None:
        """実行中以外の行をすべて削除する。"""
        for episode_key in [key for key, row in self.rows.items() if row["state"] != "running"]:
            self.rows.pop(episode_key)["frame"].destroy()
        self._reflow()
        self._update_summary()

    def reset(self, episode_key: str) -> None:
        if episode_key in self.rows:
            self.remove(episode_key)

    def _update_summary(self) -> None:
        active = sum(row["state"] == "running" for row in self.rows.values())
        total = len(self.rows)
        self.progress_text_var.set("ダウンロードジョブはありません" if not total else f"実行中: {active} / 全体: {total}")
        self.clear_finished_button.state(["!disabled"] if total > active else ["disabled"])

    def _reflow(self, *, auto_scroll: bool = False) -> None:
        for index, row in enumerate(self.rows.values()):
            row["frame"].grid(row=index, column=0, sticky="ew", padx=5, pady=2)
        self.root.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if auto_scroll:
            self.canvas.yview_moveto(1.0)

    def _create_job_widgets(self, episode: Episode, episode_key: str) -> dict[str, Any]:
        frame = ttk.Frame(self.inner, style="Card.TFrame")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=episode.display_title or episode.title, style="Bold.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5)
        )
        status_var = tk.StringVar(value="準備中...")
        ttk.Label(frame, textvariable=status_var, font=("", 9), width=10, anchor="e").grid(
            row=0, column=2, sticky="e", padx=10, pady=(10, 5)
        )
        progress = ttk.Progressbar(frame, mode="indeterminate", length=200)
        progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        progress.start(10)
        percent_var = tk.StringVar(value="--%")
        progress_meta_var = tk.StringVar(value="--% / 残り --:--")
        ttk.Label(frame, textvariable=progress_meta_var, font=("", 9), width=22, anchor="e").grid(
            row=1, column=2, sticky="e", padx=10, pady=5
        )
        action_button = ttk.Button(frame, text="中止", command=lambda: self.on_cancel_one(episode_key), width=8)
        action_button.grid(row=0, column=3, rowspan=2, padx=10, pady=10)
        return {
            "frame": frame,
            "status_var": status_var,
            "progress": progress,
            "percent_var": percent_var,
            "progress_meta_var": progress_meta_var,
            "action_button": action_button,
        }

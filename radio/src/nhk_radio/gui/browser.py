"""Tkinter GUI browser for NHK radio programs."""

import contextlib
import logging
import queue
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import (  # noqa: F401
    DEFAULT_UI_FONT_SIZE_PT,
    DEFAULT_UI_THEME,
    HELP_CONTENT_VERSION,
    _load_ui_settings,
    _save_help_seen_version,
)
from ..types import Episode, Program
from .build import AppShell, UiVars
from .data_manager import DataManager
from .download_manager import DownloadManager
from .download_panel import GuiDownloadsMixin
from .help_markdown import build_help_markdown, render_help_markdown
from .listing import GuiListingMixin
from .protocols import GuiBrowserProtocol
from .styling import GuiStylingMixin
from .toolkit import messagebox, tk, ttk

if TYPE_CHECKING:
    # Protocol を実装していることをコンパイラに確認させる
    _: GuiBrowserProtocol

logger = logging.getLogger(__name__)

# 終了時に中止した DL の後始末を待つ上限秒数とポーリング間隔
_QUIT_WAIT_SECONDS = 5.0
_QUIT_POLL_INTERVAL_MS = 100


class EpisodeGuiBrowser(GuiStylingMixin, GuiListingMixin, GuiDownloadsMixin):
    def __init__(self, programs: list[Program] | None, output_dir: Path, *, audio_only: bool = True, genre: str | None = None, root: tk.Tk | None = None):
        if tk is None or ttk is None:
            raise RuntimeError("tkinter が利用できません")

        self.programs = programs or []
        self.output_dir = output_dir
        self.audio_only = audio_only
        self.genre = genre

        self._initialize_runtime_state(self.programs)
        if root is not None:
            self.root = root
        else:
            self._initialize_root_window()
        # ThemeManager の初期化 (Mixin経由)
        self._initialize_theme()

        self._initialize_ui_state(self.programs)

        self._build_widgets()
        self._populate_programs()

        seen_ver = int(self.theme_manager.settings.get("help_seen_version", 0))
        if seen_ver < HELP_CONTENT_VERSION:
            _save_help_seen_version(HELP_CONTENT_VERSION)
            self.root.after(600, self._show_help_dialog)

        if programs is None:
            # 起動後に非同期取得を開始
            self.root.after(100, lambda: self._start_fetch_programs(genre))

    def _build_widgets(self) -> None:
        self.shell = AppShell(
            self.root,
            self,
            self._palette,
            UiVars(
                status=self.status_var,
                selected_cell_meta=self.selected_cell_meta_var,
                selected_cell_value=self.selected_cell_value_var,
                settings_button=self.settings_button_var,
                program_search=self.program_search_var,
                program_genre=self.program_genre_filter_var,
                program_summary=self.program_list_summary_var,
                program_title=self.selected_program_title_var,
                program_meta=self.selected_program_meta_var,
                program_stats=self.selected_program_stats_var,
                fetch_button=self.fetch_button_var,
                episode_message=self.episode_message_var,
                episode_search=self.episode_search_var,
                episode_saved_only=self.episode_saved_only_var,
                episode_filter_summary=self.episode_filter_summary_var,
                episode_selection_summary=self.episode_selection_summary_var,
                progress=self.progress_text_var,
                theme=self.theme_var,
                font_size=self.font_size_var,
                font_size_display=self.font_size_display_var,
                settings_save_button=self.settings_save_button_var,
                settings_summary=self.settings_summary_var,
            ),
            self.program_search_history,
            self._program_genre_filter_values,
        )
        shell = self.shell
        self.program_view = shell.program_view
        self.episode_view = shell.episode_view
        self.activity_view = shell.activity_view
        self.settings_view = shell.settings_view
        self.program_tree = shell.program_view.tree
        self.program_tree_programs = shell.program_view.programs_by_item
        self.program_genre_filter_combo = shell.program_view.genre_combo
        self.program_search_entry = shell.program_view.search_entry
        self.episode_tree = shell.episode_view.tree
        self.displayed_episode_map = shell.episode_view.episodes_by_item
        self.episode_scroll = shell.episode_view.scrollbar
        self.episode_title_var = shell.episode_view.episode_title_var
        self.episode_search_entry = shell.episode_view.search_entry
        self.episode_saved_only_check = shell.episode_view.saved_only_check
        self.fetch_button = shell.episode_view.fetch_button
        self.download_button = shell.episode_view.download_button
        self.active_download_rows = shell.activity_view.rows
        self.selected_cell_entry = shell.selected_cell_entry
        self.selected_cell_area = shell.selected_cell_area
        self.copy_cell_button = shell.copy_cell_button

        self._update_program_tree_headings()
        self._update_episode_tree_headings()
        self.download_button.state(["disabled"])
        self._refresh_treeview_theme()
        self._update_settings_ui()
        self._show_screen("browser", announce=False)

    def _initialize_runtime_state(self, programs: list[Program]) -> None:
        self.result: tuple[Program, list[Episode]] | tuple[None, None] = (None, None)
        self.loading = False
        self._search_timer = None

        # UI 状態 (ThemeManager 初期化前にプレースホルダを設定)
        self.current_theme = DEFAULT_UI_THEME
        self.current_font_size = int(DEFAULT_UI_FONT_SIZE_PT)
        self.current_screen = "browser"
        self.settings_dirty = False
        self.program_search_history: list[str] = []

        # データ管理 (Composition)
        self.data_manager = DataManager(
            on_program_result=self._on_data_manager_programs,
            on_episode_result=self._on_data_manager_episodes,
        )
        self.data_manager.update_programs(programs)

        # UI同期用キュー
        self.fetch_result_queue: queue.Queue | None = queue.Queue()
        self.program_fetch_queue: queue.Queue = queue.Queue()
        self.download_result_queue: queue.Queue = queue.Queue()

        # ダウンロード管理 (Composition)
        self.download_manager = DownloadManager(
            output_dir=self.output_dir,
            audio_only=self.audio_only,
            on_result=self._on_download_manager_result,
        )

        # 起動時に前回のクラッシュ等で残ったバックアップファイルを非同期に復元・整理 (G4, 2-2, 2-3)
        self._start_residual_backup_cleanup()

        self.download_polling = False
        self.active_download_rows = {}

        # Mixin がアクセスするプロパティ。programs は初期値、filtered_programs は動的更新、
        # episodes_cache は DataManager と同期。
        self.programs = self.data_manager.programs
        self.filtered_programs = self.data_manager.programs
        self.episodes_cache = self.data_manager.episodes_cache

        self.program_tree_programs = {}
        self.selected_program_key: str | None = None
        self.displayed_program: Program | None = None
        self.displayed_episodes: list[Episode] = []
        self.displayed_episode_map = {}
        self.selected_episode_keys: tuple[str, ...] = ()
        self.program_sort_state = ("no", False)
        self.episode_sort_state = ("date", True)
        self.saved_episode_buttons: dict[str, ttk.Button] = {}
        self.saved_button_refresh_pending = False
        self.saved_episode_popup: tk.Toplevel | None = None
        self.help_popup: tk.Toplevel | None = None
        self.help_text: tk.Text | None = None
        self.help_markdown_content: str | None = None
        self.tooltip_window: tk.Toplevel | None = None
        self.tooltip_label: tk.Label | None = None
        self.program_order_map = {self._program_key(program): index for index, program in enumerate(programs, 1)}

    def _on_download_manager_result(self, res_type, key, program, episode, data):
        """Bridge result from DownloadManager to UI queue."""
        self.download_result_queue.put((res_type, key, program, episode, data))

    def _on_data_manager_programs(self, programs, error):
        """Bridge programs result from DataManager to UI queue."""
        self.program_fetch_queue.put((programs, error))

    def _on_data_manager_episodes(self, program, episodes, source, error):
        """Bridge episodes result from DataManager to UI queue."""
        if self.fetch_result_queue:
            self.fetch_result_queue.put((program, episodes, source, error))

    def _toggle_settings_screen(self):
        """表示設定ダイアログを開く。開いていれば (未保存の確認をして) 閉じる。"""
        if self.current_screen == "browser":
            self._show_screen("settings")
        else:
            self._show_screen("browser")

    def _show_screen(self, screen_name: str, announce: bool = True):
        """指定したスクリーンを表示する。"""
        if screen_name != "settings" and self.current_screen == "settings" and not self._confirm_leave_settings():
            return
        if screen_name == "settings":
            self.shell.show_screen("settings")
            self.current_screen = "settings"
            if announce:
                self.status_var.set("表示設定を開きました")
        else:
            self.shell.show_screen("browser")
            self.current_screen = "browser"
            if announce:
                self.status_var.set("表示設定を閉じました")
        self._update_settings_ui()

    def _reset_ui_settings(self):
        """UI設定をデフォルトに戻す。"""
        if messagebox.askyesno("設定リセット", "表示設定を初期値に戻しますか？"):
            from ..config import DEFAULT_UI_FONT_SIZE_PT, DEFAULT_UI_THEME
            self._apply_theme(DEFAULT_UI_THEME)
            self._apply_font_size_preset(int(DEFAULT_UI_FONT_SIZE_PT))
            self.status_var.set("設定をリセットしました")

    def _discard_unsaved_settings(self):
        """保存されていない設定を破棄して現在の状態に戻す。"""
        self.current_theme = self.saved_theme
        self.current_font_size = self.saved_font_size
        self._apply_current_theme()
        self.settings_dirty = False

    def _initialize_root_window(self) -> None:
        self.root = tk.Tk()
        self.root.title("NHK ラジオ 聞き逃しブラウザ")

        # macOS でのイベントループ初期化エラーを抑制するためのヒント
        with contextlib.suppress(tk.TclError):
            self.root.update_idletasks()

        # デモモード時は録画しやすいように位置を固定
        import os

        if os.environ.get("NHK_RADIO_DEMO_MODE"):
            self.root.geometry("1360x840+0+0")
        else:
            self.root.geometry("1360x840")
        self.root.minsize(1040, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

    def _initialize_ui_state(self, programs: list[Program]) -> None:
        # ThemeManager が読み込んだ実際の値と同期 (StylingMixin で既に行われているが念のため一貫性を維持)
        tm = self.theme_manager
        self.program_search_history = list(tm.settings.get("program_search_history", []))

        self.saved_theme = self.current_theme
        self.saved_font_size = self.current_font_size

        self.font_family = tm.mono_family
        self.ui_font_family = tm.font_family

        self.status_var = tk.StringVar(value="番組を選択してください。")
        self.selected_cell_meta_var = tk.StringVar(value="")
        self.selected_cell_value_var = tk.StringVar(value="")
        self.program_list_summary_var = tk.StringVar(value=f"{len(programs)} 番組")
        self.program_search_var = tk.StringVar()
        self.program_genre_filter_var = tk.StringVar(value="すべて")
        self.selected_program_title_var = tk.StringVar(value="")
        self.selected_program_meta_var = tk.StringVar(value="")
        self.selected_program_stats_var = tk.StringVar(value="")
        self.episode_message_var = tk.StringVar(value="")
        self.episode_filter_summary_var = tk.StringVar(value="表示中 0 件")
        self.episode_selection_summary_var = tk.StringVar(value="選択 0 件")
        self.episode_search_var = tk.StringVar()
        self.episode_saved_only_var = tk.BooleanVar(value=False)
        self.fetch_button_var = tk.StringVar(value="一覧を取得")
        self.progress_text_var = tk.StringVar(value="")

        self.settings_button_var = tk.StringVar()
        self.settings_summary_var = tk.StringVar()
        self.font_size_display_var = tk.StringVar()
        self.settings_save_button_var = tk.StringVar()
        self.theme_var = tk.StringVar(value=self.current_theme)
        self.font_size_var = tk.IntVar(value=self.current_font_size)
        self.program_search_var.trace_add("write", self._on_program_search_change)
        self.episode_search_var.trace_add("write", self._on_episode_filter_change)
        self.episode_saved_only_var.trace_add("write", self._on_episode_filter_change)

    def _persist_ui_settings(self):
        """UI設定を永続化する。ThemeManager を通じて保存。"""
        self.theme_manager.save_settings(
            theme=self.current_theme,
            font_size=self.current_font_size,
            search_history=self.program_search_history,
        )

    def _persist_search_history(self):
        """検索履歴のみを永続化する (G8)。"""
        self.theme_manager.save_search_history(self.program_search_history)

    def _set_progress(self, current: int, total: int, text: str = ""):
        """進捗状況を更新する。"""
        if total > 0:
            # 簡易的な進捗文字列を生成
            self.progress_text_var.set(f"{text} {current}/{total}")
        else:
            self.progress_text_var.set(text)

    def _reset_ui_state_after_cache_clear(self):
        """キャッシュクリア後にUI表示を初期化する。"""
        self.episodes_cache.clear()
        # 削除済みキャッシュの内容を表示し続けないよう、エピソード一覧と概要もリセットする (M6)
        self.displayed_program = None
        self.displayed_episodes = []
        self.selected_episode_keys = ()
        self.episode_view.clear()
        self.episode_message_var.set("")
        self._update_program_overview(None)
        self._populate_programs()
        self._refresh_fetch_button_label()
        self.status_var.set("キャッシュをクリアしました")
        # clear_all_data で番組一覧も空になるため、取り直して一覧が空のまま残らないようにする
        self._start_fetch_programs()

    def _start_residual_backup_cleanup(self) -> None:
        """起動時にバックグラウンドスレッドで残存バックアップファイルを復元・整理する (2-2, 2-3)。"""

        def _worker() -> None:
            try:
                from ..downloads.cleanup import BACKUP_MIN_AGE_SECONDS, cleanup_residual_backup_files

                active_dirs = self.download_manager.get_active_program_dirs()
                cleanup_residual_backup_files(
                    self.output_dir,
                    active_program_dirs=active_dirs,
                    min_age_seconds=BACKUP_MIN_AGE_SECONDS,
                )
            except Exception as e:
                logger.debug(f"残存バックアップの非同期整理で例外: {e}")

        threading.Thread(target=_worker, daemon=True, name="ResidualBackupCleanup").start()

    def _start_fetch_programs(self, genre: str | None = None):
        """Initial background fetch of all programs."""
        if self.loading:
            return

        self.program_fetch_queue = queue.Queue()
        self.status_var.set("番組一覧を読み込み中...")
        self._set_loading(True)
        self.data_manager.start_fetch_programs(genre)
        self.root.after(100, self._poll_fetch_programs)

    def _poll_fetch_programs(self):
        try:
            res = self.program_fetch_queue.get_nowait()
            self._finish_fetch_programs(*res)
        except queue.Empty:
            if self.loading:
                self.root.after(100, self._poll_fetch_programs)

    def _finish_fetch_programs(self, programs: list[Program], error: str | None):
        self._set_loading(False)
        if error:
            self.status_var.set(f"取得失敗: {error}")
        else:
            self.programs = programs
            self.filtered_programs = list(programs)
            # program_order_map は後で GuiListingMixin 等で使われる可能性があるため更新
            self.program_order_map = {self._program_key(p): i for i, p in enumerate(programs, 1)}
            self._apply_program_filters()
            self.status_var.set("読み込み完了")

    def run(self) -> tuple[Program, list[Episode]] | tuple[None, None]:
        self.root.mainloop()
        return self.result

    def _cancel(self):
        # 補助ウィンドウが開いていても 1 回の操作で終了できるようにする (M3)
        for popup in (self.help_popup, self.saved_episode_popup):
            if popup is not None and popup.winfo_exists():
                popup.destroy()
        # 未保存の表示設定は表示中の画面に関係なく確認する (M1)
        if self.settings_dirty:
            if messagebox is None or not messagebox.askyesno(
                "未保存の表示設定", "未保存の表示設定を破棄して終了しますか？", parent=self.root
            ):
                return
            self._discard_unsaved_settings()
        has_running_download = any(row["state"] == "running" for row in self.active_download_rows.values())
        if has_running_download:
            # DL 中でも「すべて中止して終了」を選べるようにする (M4)
            if messagebox is None or not messagebox.askyesno(
                "ダウンロード処理中です",
                "ダウンロード処理が実行中です。すべて中止して終了しますか？",
                parent=self.root,
            ):
                return
            self.download_manager.cancel_all()
            self.status_var.set("ダウンロードを中止して終了します...")
            self._destroy_after_downloads_stop(time.monotonic() + _QUIT_WAIT_SECONDS)
            return
        if self.loading and messagebox is not None and not messagebox.askyesno(
            "一覧取得中",
            "一覧を取得中ですが、終了しますか？",
            parent=self.root,
        ):
            return
        self._destroy_root()

    def _destroy_after_downloads_stop(self, deadline: float) -> None:
        """中止した DL ワーカーが退避ファイルの復元を終えるまで待ってから終了する (M4)。"""
        if self.download_manager.is_active() and time.monotonic() < deadline:
            self.root.after(_QUIT_POLL_INTERVAL_MS, lambda: self._destroy_after_downloads_stop(deadline))
            return
        self._destroy_root()

    def _destroy_root(self) -> None:
        self.result = (None, None)
        self.root.destroy()

    def _confirm_leave_settings(self) -> bool:
        """未保存の表示設定があれば保存 / 破棄 / キャンセルを確認する。離脱してよければ True (M1)。"""
        if not self.settings_dirty or messagebox is None:
            return True
        answer = messagebox.askyesnocancel(
            "未保存の表示設定", "表示設定が保存されていません。保存しますか？", parent=self.root
        )
        if answer is None:
            return False
        if answer:
            self._save_ui_settings_from_screen()
        else:
            self._discard_unsaved_settings()
        return True

    def _is_text_input_focus(self) -> bool:
        widget = self.root.focus_get()
        if widget is None:
            return False
        return widget in {
            getattr(self, "program_search_entry", None),
            getattr(self, "episode_search_entry", None),
            getattr(self, "selected_cell_entry", None),
            # ジャンル選択中の文字入力で F / D が発火しないようにする (F5)
            getattr(self, "program_genre_filter_combo", None),
        }

    def _show_help_dialog(self, _event=None):
        if self.help_popup is not None and self.help_popup.winfo_exists():
            self.help_popup.lift()
            self.help_popup.focus_force()
            return "break"

        popup = tk.Toplevel(self.root)
        popup.title("ヘルプ / ショートカット")
        popup.geometry("840x640")
        popup.minsize(700, 500)
        popup.transient(self.root)
        popup.configure(background=self._palette["surface"])
        popup.bind("<Escape>", lambda _event: popup.destroy())
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)

        main = ttk.Frame(popup, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)

        body = ttk.Frame(main)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.help_text = tk.Text(
            body,
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=1,
            cursor="arrow",
        )
        self.help_text.grid(row=0, column=0, sticky="nsew")
        help_scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.help_text.yview)
        help_scrollbar.grid(row=0, column=1, sticky="ns")
        self.help_text.configure(yscrollcommand=help_scrollbar.set)
        self.help_markdown_content = build_help_markdown(self.programs)
        render_help_markdown(self.help_text, self.help_markdown_content, self._palette, self._help_markdown_fonts())

        actions = ttk.Frame(main)
        actions.grid(row=1, column=0, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="閉じる", command=popup.destroy, style="Accent.TButton").grid(row=0, column=0)

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
        self.help_popup = popup
        popup.bind(
            "<Destroy>",
            lambda _event: (
                setattr(self, "help_popup", None),
                setattr(self, "help_text", None),
                setattr(self, "help_markdown_content", None),
            ),
            add="+",
        )
        return "break"

    def _help_markdown_fonts(self) -> dict[str, tuple]:
        return {
            "h1": self._app_title_font,
            "h2": self._heading_font,
            "h3": self._card_title_font,
            "body": self._ui_base,
            "strong": self._ui_bold,
            "mono": self._mono,
        }

    def _handle_escape(self, _event=None):
        if self.help_popup is not None and self.help_popup.winfo_exists():
            self.help_popup.destroy()
            return "break"
        if self.saved_episode_popup is not None and self.saved_episode_popup.winfo_exists():
            self.saved_episode_popup.destroy()
            return "break"
        if self.current_screen == "settings":
            self._show_screen("browser")
            return "break"
        if self._is_text_input_focus():
            widget = self.root.focus_get()
            if widget is self.program_search_entry:
                return self._clear_program_search()
            if widget is self.episode_search_entry:
                return self._clear_episode_search()
        return None

    def _handle_browser_shortcut(self, event):
        if self.current_screen != "browser" or self.loading or self._is_text_input_focus():
            return None
        # ヘルプダイアログや別ポップアップなどの別ウィンドウが開いている時はショートカットを無効化 (G10)
        if getattr(self, "help_popup", None) and self.help_popup.winfo_exists():
            return None
        if getattr(self, "saved_episode_popup", None) and self.saved_episode_popup.winfo_exists():
            return None
        widget = getattr(event, "widget", None)
        if widget and hasattr(widget, "winfo_toplevel"):
            try:
                if widget.winfo_toplevel() != self.root:
                    return None
            except Exception:
                pass
        # 修飾キー (Control, Alt/Option, Command など) が押されている場合は無視 (G10)
        # 0x4: Control, 0x8: Mod1/Alt, 0x100000: Command (macOS)
        if getattr(event, "state", 0) & (0x4 | 0x8 | 0x100000):
            return None
        key = (event.keysym or "").lower()
        if key == "f":
            return self._start_fetch_selected()
        if key == "d":
            return self._start_download_selected()
        if key in {"question", "slash"} and bool(event.state & 0x1):
            return self._show_help_dialog()
        return None


def browse_programs(
    programs: list[Program] | None, output_dir: Path, *, audio_only: bool = True, genre: str | None = None
) -> tuple[Program, list[Episode]] | tuple[None, None]:

    try:
        return EpisodeGuiBrowser(programs, output_dir, audio_only=audio_only, genre=genre).run()
    except tk.TclError as e:
        raise RuntimeError(str(e)) from e



# ──────────────────────────────────────────────────────
# 対話型選択 UI
# ──────────────────────────────────────────────────────

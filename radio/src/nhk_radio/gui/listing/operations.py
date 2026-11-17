"""GUI operations Mixin — ファイル操作・ダウンロード状態。"""

import logging
import tkinter as tk
import tkinter.messagebox as mb
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocols import GuiBrowserProtocol

logger = logging.getLogger(__name__)


class GuiOperationsMixin:
    """Logic for file operations and download status."""

    if TYPE_CHECKING:
        self: GuiBrowserProtocol

    def _normalized_search_text(self, text: str) -> str:
        """検索テキストの正規化（NFKC 正規化・小文字化・前後スペース削除）。"""
        import unicodedata
        if not text:
            return ""
        return unicodedata.normalize("NFKC", text).casefold().strip()

    def _tree_label(self, tree: ttk.Treeview) -> str:
        """ツリービューのラベルを返す。"""
        if tree is self.program_tree:
            return "番組一覧"
        if tree is self.episode_tree:
            return "エピソード一覧"
        return "一覧"

    def _tree_cell_from_event(self, tree: ttk.Treeview, event) -> tuple[str, str, str] | None:
        """イベント座標からツリーセルを抽出して返す（item_id, column_id, value）。"""
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

    def _on_episode_tree_right_click(self, event):
        """右クリックで行を選択してコンテキストメニューを表示。"""
        item_id = self.episode_tree.identify_row(event.y)
        if not item_id:
            return
        self.episode_tree.selection_set(item_id)
        self._show_episode_context_menu(event, item_id)

    def _show_episode_context_menu(self, event, item_id: str):
        """エピソード右クリックコンテキストメニューを表示。"""
        is_saved = self._is_saved_item(item_id)

        # 右クリックのたびに Menu を作ると破棄されずに溜まるため、1 つを使い回す (G12)
        menu = self.episode_context_menu
        if menu is None:
            menu = tk.Menu(self.root, tearoff=0)
            self.episode_context_menu = menu
        else:
            menu.delete(0, "end")

        state_saved = "normal" if is_saved else "disabled"

        menu.add_command(
            label="デフォルトプレイヤーで再生",
            command=lambda: self._play_episode_file(item_id),
            state=state_saved,
        )
        menu.add_command(
            label="フォルダを開く",
            command=lambda: self._open_downloaded_episode_folder(item_id),
            state=state_saved,
        )
        menu.add_command(
            label="パスをコピー",
            command=lambda: self._copy_episode_path(item_id),
            state=state_saved,
        )
        menu.add_command(
            label="ファイル名をコピー",
            command=lambda: self._copy_episode_filename(item_id),
            state=state_saved,
        )
        menu.add_separator()
        menu.add_command(
            label="ファイルを削除",
            command=lambda: self._delete_episode_file(item_id),
            state=state_saved,
        )
        menu.add_command(
            # 未保存の行では通常の DL なので、ラベルを動作に合わせる (F2)
            label="再度ダウンロード" if is_saved else "ダウンロード",
            command=lambda: self._redownload_episode(item_id),
        )
        menu.add_separator()
        menu.add_command(
            label="番組ページを開く",
            command=lambda: self._open_nhk_program_page(),
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _play_episode_file(self, item_id: str):
        """デフォルトプレイヤーでエピソードファイルを再生。"""
        import os
        import subprocess
        import sys

        from ...downloads import find_episode_downloaded_path, is_within_output_dir
        from ...downloads.cleanup import MEDIA_EXTENSIONS

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        path = find_episode_downloaded_path(
            self.output_dir, self.displayed_program, episode, audio_only=self.audio_only
        )
        if path is None:
            self.status_var.set("ファイルが見つかりません。")
            return

        try:
            within_output = is_within_output_dir(path, self.output_dir) and path.resolve().is_relative_to(
                self.output_dir.resolve()
            )
        except OSError:
            within_output = False
        if not within_output:
            self.status_var.set(f"保存先の外を指すため再生しません: {path}")
            return

        if path.suffix.lower() not in MEDIA_EXTENSIONS:
            self.status_var.set(f"再生できないファイル形式です: {path.name}")
            return

        target = os.path.abspath(path)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", target])
            elif sys.platform == "win32":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
            self.status_var.set(f"再生中: {path.name}")
        except Exception as e:
            self.status_var.set(f"再生に失敗しました: {e}")

    def _open_selected_program_folder(self, _event=None):
        """選択中/表示中番組の保存先フォルダを開く（未作成なら保存先ルートを開く）。"""
        from ...downloads import _program_search_dirs, is_within_output_dir, open_downloaded_folder

        program = self.displayed_program or self._selected_program()
        target_dir = self.output_dir
        if program is not None:
            for candidate in _program_search_dirs(self.output_dir, program):
                if candidate.exists():
                    target_dir = candidate
                    break

        if target_dir == self.output_dir:
            target_dir.mkdir(parents=True, exist_ok=True)
        elif not is_within_output_dir(target_dir / "_", self.output_dir):
            self.status_var.set(f"保存先の外を指すためフォルダを開きません: {target_dir}")
            return "break"

        if open_downloaded_folder(target_dir):
            self.status_var.set(f"フォルダを開きました: {target_dir.name}")
        else:
            self.status_var.set("フォルダを開く際にエラーが発生しました。")
        return "break"

    def _open_downloaded_episode_folder(self, item_id: str):
        """保存済みエピソードの保存先フォルダを開く。"""
        if self.displayed_program is None:
            return

        # item_id に対応するエピソードを取得
        episode = self.displayed_episode_map.get(item_id)
        if episode is None:
            self.status_var.set("エピソード情報が見つかりません。")
            return

        # 保存先を確認（旧ディレクトリ構造に保存されているファイルも対象にする: B4）
        from ...downloads import (
            find_episode_downloaded_path,
            is_within_output_dir,
            open_downloaded_folder,
            program_output_dir,
        )

        downloaded_path = find_episode_downloaded_path(
            self.output_dir, self.displayed_program, episode, audio_only=self.audio_only
        )
        target_dir = (
            downloaded_path.parent
            if downloaded_path is not None
            else program_output_dir(self.output_dir, self.displayed_program)
        )
        if not target_dir.exists():
            self.status_var.set("保存先フォルダが見つかりません。")
            return
        if not is_within_output_dir(target_dir / "_", self.output_dir):
            self.status_var.set(f"保存先の外を指すためフォルダを開きません: {target_dir}")
            return

        # フォルダを開く
        if open_downloaded_folder(target_dir):
            self.status_var.set(f"フォルダを開きました: {target_dir.name}")
        else:
            self.status_var.set("フォルダを開く際にエラーが発生しました。")

    def _copy_episode_path(self, item_id: str):
        """フルパスをクリップボードにコピー。"""
        from ...downloads import find_episode_downloaded_path

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        path = find_episode_downloaded_path(
            self.output_dir, self.displayed_program, episode, audio_only=self.audio_only
        )
        if path is None:
            self.status_var.set("ファイルが見つかりません。")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(str(path))
        self.status_var.set(f"パスをコピーしました: {path.name}")

    def _copy_episode_filename(self, item_id: str):
        """ファイル名のみクリップボードにコピー。"""
        from ...downloads import find_episode_downloaded_path

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        path = find_episode_downloaded_path(
            self.output_dir, self.displayed_program, episode, audio_only=self.audio_only
        )
        if path is None:
            self.status_var.set("ファイルが見つかりません。")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(path.name)
        self.status_var.set(f"ファイル名をコピーしました: {path.name}")

    def _delete_episode_file(self, item_id: str):
        """ファイルを削除（確認ダイアログ付き）。"""
        from ...downloads import (
            _episode_key,
            find_episode_downloaded_path,
            is_within_output_dir,
            remove_episode_from_manifest,
        )

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        path = find_episode_downloaded_path(
            self.output_dir, self.displayed_program, episode, audio_only=self.audio_only
        )
        if path is None:
            self.status_var.set("ファイルが見つかりません。")
            return
        if not is_within_output_dir(path, self.output_dir):
            # リンクをたどると保存先の外を指すファイルは削除しない
            self.status_var.set(f"保存先の外を指すため削除しません: {path}")
            return

        if not mb.askyesno(
            "ファイルの削除",
            f"以下のファイルを削除しますか？\n\n{path.name}",
            parent=self.root,
        ):
            return

        try:
            path.unlink()
            remove_episode_from_manifest(self.output_dir, self.displayed_program, episode)
            self.status_var.set(f"削除しました: {path.name}")
            was_saved_only = self.episode_saved_only_var.get()
            self.displayed_saved_keys.discard(_episode_key(episode))
            self.episode_view.set_saved(item_id, False)
            self._refresh_saved_only_button_state()
            self._refresh_program_overview_stats()
            if was_saved_only:
                # 「保存済みのみ」表示中は削除した行を即座に一覧から外す (F3, B1)
                self._apply_episode_filter()
            self._refresh_downloaded_column(self.displayed_program)
        except OSError as e:
            self.status_var.set(f"削除に失敗しました: {e}")

    def _redownload_episode(self, item_id: str):
        """エピソードを再ダウンロード（上書き確認付き）。"""
        from ...downloads import find_episode_downloaded_path

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        program = self.displayed_program
        path = find_episode_downloaded_path(
            self.output_dir, program, episode, audio_only=self.audio_only
        )

        # 注意: 事前の unlink は行わない。ダウンロードワーカー側で安全に退避・復元されるため、
        # ダウンロード失敗時に元ファイルを失うことを防止する (G4)
        if path is not None and not mb.askyesno(
            "ファイルの上書き",
            f"ファイルが既に存在します。上書きしてダウンロードしますか？\n\n{path.name}",
            parent=self.root,
        ):
            return

        from ...downloads import _episode_key

        episode_key = _episode_key(episode)
        if episode_key in self.active_download_rows:
            row = self.active_download_rows[episode_key]
            if row.get("state") == "running":
                self.status_var.set("既にダウンロード中です。")
                return

        self._reset_download_row(episode_key)
        self._add_download_row(program, episode)
        self.download_manager.start_download(program, episode)

        if not self.download_polling:
            self.download_polling = True
            self.root.after(100, self._poll_download_result)

        self.status_var.set(f"「{program.display_title or program.title}」の再ダウンロードを開始しました。")

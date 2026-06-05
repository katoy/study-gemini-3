"""GUI operations Mixin — ファイル操作・ダウンロード状態。"""

# mypy: disable-error-code="attr-defined,has-type,arg-type,assignment,misc,empty-body,return-value"

import logging
import tkinter as tk
import tkinter.messagebox as mb

logger = logging.getLogger(__name__)


class GuiOperationsMixin:
    """Logic for file operations and download status."""

    # Mixin properties to help type checker
    if False:
        from ..browser import EpisodeGuiBrowser
        self = EpisodeGuiBrowser()

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

        menu = tk.Menu(self.root, tearoff=0)

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
            label="再度ダウンロード",
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

        from ...downloads import find_episode_downloaded_path

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        path = find_episode_downloaded_path(self.output_dir, self.displayed_program, episode)
        if path is None:
            self.status_var.set("ファイルが見つかりません。")
            return

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif sys.platform == "win32":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.status_var.set(f"再生中: {path.name}")
        except Exception as e:
            self.status_var.set(f"再生に失敗しました: {e}")

    def _open_downloaded_episode_folder(self, item_id: str):
        """保存済みエピソードの保存先フォルダを開く。"""
        if self.displayed_program is None:
            return

        # item_id に対応するエピソードを取得
        episode = self.displayed_episode_map.get(item_id)
        if episode is None:
            self.status_var.set("エピソード情報が見つかりません。")
            return

        # 保存先を確認
        from ...downloads import program_output_dir, open_downloaded_folder

        program_dir = program_output_dir(self.output_dir, self.displayed_program)
        if not program_dir.exists():
            self.status_var.set("保存先フォルダが見つかりません。")
            return

        # フォルダを開く
        if open_downloaded_folder(program_dir):
            self.status_var.set(f"フォルダを開きました: {program_dir.name}")
        else:
            self.status_var.set("フォルダを開く際にエラーが発生しました。")

    def _copy_episode_path(self, item_id: str):
        """フルパスをクリップボードにコピー。"""
        from ...downloads import find_episode_downloaded_path

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        path = find_episode_downloaded_path(self.output_dir, self.displayed_program, episode)
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

        path = find_episode_downloaded_path(self.output_dir, self.displayed_program, episode)
        if path is None:
            self.status_var.set("ファイルが見つかりません。")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(path.name)
        self.status_var.set(f"ファイル名をコピーしました: {path.name}")

    def _delete_episode_file(self, item_id: str):
        """ファイルを削除（確認ダイアログ付き）。"""
        from ...downloads import find_episode_downloaded_path, remove_episode_from_manifest

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        path = find_episode_downloaded_path(self.output_dir, self.displayed_program, episode)
        if path is None:
            self.status_var.set("ファイルが見つかりません。")
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
            self._refresh_downloaded_column(self.displayed_program)
        except OSError as e:
            self.status_var.set(f"削除に失敗しました: {e}")

    def _redownload_episode(self, item_id: str):
        """エピソードを再ダウンロード（上書き確認付き）。"""
        from ...downloads import find_episode_downloaded_path, remove_episode_from_manifest

        episode = self.displayed_episode_map.get(item_id)
        if not episode or not self.displayed_program:
            return

        program = self.displayed_program
        path = find_episode_downloaded_path(self.output_dir, program, episode)

        if path is not None:
            if not mb.askyesno(
                "ファイルの上書き",
                f"ファイルが既に存在します。上書きしてダウンロードしますか？\n\n{path.name}",
                parent=self.root,
            ):
                return

            try:
                path.unlink()
                remove_episode_from_manifest(self.output_dir, program, episode)
            except OSError as e:
                self.status_var.set(f"既存ファイルの削除に失敗しました: {e}")
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

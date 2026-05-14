import re
import tkinter as tk
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

from nhk_radio.gui.browser import EpisodeGuiBrowser


class GuiConsistencyTest(unittest.TestCase):
    """GUIクラスとそのMixin間の属性・メソッドの整合性を検証するテスト。"""

    def setUp(self):
        # 1) 本物の root window を作る (表示はしない)
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except tk.TclError:
            self.root = MagicMock(spec=tk.Tk)

        # 2) 依存マネージャーをモックし、必要な属性値を設定
        self.dm_mock = MagicMock()
        self.tm_mock = MagicMock()
        self.tm_mock.current_theme = "light"
        self.tm_mock.current_font_size = 11
        self.tm_mock.settings = {"program_search_history": []}
        self.tm_mock.font_family = "sans-serif"
        self.tm_mock.mono_family = "monospace"
        # 実行時に期待される全パレットキー
        self.tm_mock.palette = {
            "bg": "white", "text": "black", "row_odd": "gray",
            "accent": "blue", "accent_soft": "lightblue", "accent_dark": "darkblue",
            "primary": "blue", "border": "gray", "border_strong": "darkgray",
            "surface": "white", "surface_alt": "gray", "text_sub": "gray",
            "selected_bg": "blue", "selected_fg": "white", "on_accent": "white",
            "dl_even": "green", "dl_odd": "green", "input_bg": "white", "head_bg": "gray"
        }

        self.patchers = [
            patch("nhk_radio.gui.browser.tk.Tk", return_value=self.root),
            patch("nhk_radio.gui.data_manager.DataManager", return_value=self.dm_mock),
            patch("nhk_radio.gui.styling.ThemeManager", return_value=self.tm_mock),
            patch("nhk_radio.gui.download_manager.DownloadManager"),
            patch("nhk_radio.gui.toolkit.ttk.Style"),
        ]
        for p in self.patchers:
            p.start()

        # 3) EpisodeGuiBrowser を作成 (初期化時のクラッシュをこの時点で検知)
        try:
            self.browser = EpisodeGuiBrowser([], Path("/tmp"))
        except Exception as e:
            # setUpでの失敗を分かりやすく表示
            self.browser = None
            self._setup_error = e

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        with suppress(Exception):
            self.root.destroy()

    def test_all_self_references_exist(self):
        """
        src/nhk_radio/gui/ 配下の全ファイルを走査し、
        self.xxx() や self.xxx で参照されている属性が
        EpisodeGuiBrowser インスタンスに実在するかを検証する。
        """
        if self.browser is None:
            self.fail(f"Browser failed to initialize in setUp: {self._setup_error}")

        gui_dir = Path(__file__).parent.parent / "src" / "nhk_radio" / "gui"
        files = ["browser.py", "build.py", "listing.py", "styling.py", "downloads.py"]

        # 除外リスト (外部/標準/動的属性)
        ignored = {
            "root", "master", "data_manager", "theme_manager", "download_manager",
            "programs", "output_dir", "audio_only", "genre", "loading",
            "after", "bind", "unbind", "focus_get", "destroy", "winfo_exists",
            "update_idletasks", "protocol", "mainloop", "geometry", "minsize",
            "nametowidget", "tk", "children", "selection", "item", "delete", "insert",
            "set", "get", "tag_configure", "column", "heading", "yview", "xview",
            "trace_add", "trace_remove", "focus_set", "grab_set", "wait_window",
            "winfo_toplevel", "winfo_children", "winfo_parent", "winfo_class",
            "current_theme", "current_font_size", "winfo_width", "winfo_height",
            "winfo_id", "winfo_name", "winfo_pathname", "winfo_vrootwidth", "winfo_vrootheight",
            "focus_lastfor", "focus_displayof", "keysym", "state", "event_generate"
        }

        errors = []
        pattern = re.compile(r"self\.([_a-zA-Z0-9]+)")

        for filename in files:
            file_path = gui_dir / filename
            if not file_path.exists():
                continue

            content = file_path.read_text(encoding="utf-8")
            lines = [line for line in content.splitlines() if not line.strip().startswith("#")]

            for line_no, line in enumerate(lines, 1):
                for match in pattern.finditer(line):
                    attr_name = match.group(1)
                    if attr_name in ignored:
                        continue

                    if not hasattr(self.browser, attr_name):
                        errors.append(f"{filename}:{line_no} - 'self.{attr_name}' is missing")

        if errors:
            self.fail("Consistency check failed (Potential AttributeErrors):\n" + "\n".join(errors))

    def test_required_methods_execution_smoke(self):
        """過去にエラーが発生した主要なメソッドをモック環境で実行する。"""
        if self.browser is None:
            self.fail(f"Browser failed to initialize: {self._setup_error}")

        b = self.browser
        # 1. 状態変更
        b._set_loading(True)
        b._set_loading(False)
        # 2. 進捗更新
        b._set_progress(1, 10, "Testing")
        # 3. 設定の保存
        b._persist_ui_settings()

    def test_method_argument_arity(self):
        """
        ast 解析を使用して、self.method() 呼び出しの引数の数（Arity）が
        定義と一致しているかチェックする。
        """
        import ast
        import inspect

        if self.browser is None:
            self.fail(f"Browser failed to initialize: {self._setup_error}")

        # 1) 実装されているメソッドの引数情報を収集
        signatures = {}
        for name in dir(self.browser):
            attr = getattr(self.browser, name)
            if callable(attr) and not name.startswith("__"):
                try:
                    signatures[name] = inspect.signature(attr)
                except (ValueError, TypeError):
                    continue

        gui_dir = Path(__file__).parent.parent / "src" / "nhk_radio" / "gui"
        files = ["browser.py", "build.py", "listing.py", "styling.py", "downloads.py"]

        errors = []
        for filename in files:
            path = gui_dir / filename
            if not path.exists():
                continue

            tree = ast.parse(path.read_text(encoding="utf-8"))

            for node in ast.walk(tree):
                # self.method(...) 呼び出し
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self"
                ):
                    method_name = node.func.attr

                    if method_name in signatures:
                        sig = signatures[method_name]
                        params = list(sig.parameters.values())

                        # スター付き引数 (*args, **kwargs) がある呼び出しは静的判定が難しいため除外
                        if any(isinstance(a, ast.Starred) for a in node.args):
                            continue

                        # 呼び出し側の引数カウント
                        call_arg_count = len(node.args) + len(node.keywords)

                        # 定義側の期待範囲
                        min_args = sum(
                            1 for p in params if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                        )
                        has_varargs = any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params)
                        max_args = len(params) if not has_varargs else float("inf")

                        if call_arg_count < min_args or (call_arg_count > max_args and not has_varargs):
                            errors.append(
                                f"{filename}:{node.lineno} - {method_name} expected {min_args}-{max_args} args, but got {call_arg_count}"
                            )

        if errors:
            self.fail("Method arity mismatch found:\n" + "\n".join(errors))

if __name__ == "__main__":
    unittest.main()

import ast
import inspect
from pathlib import Path

from nhk_radio.gui.browser import EpisodeGuiBrowser


def analyze_calls():
    # 実際のインスタンスからメソッド情報を取得
    browser = EpisodeGuiBrowser([], Path("/tmp"), audio_only=True)
    signatures = {}
    for name in dir(browser):
        attr = getattr(browser, name)
        if callable(attr) and not name.startswith("__"):
            try:
                signatures[name] = inspect.signature(attr)
            except ValueError:
                continue

    gui_dir = Path("src/nhk_radio/gui")
    files = ["browser.py", "build.py", "listing.py", "styling.py", "downloads.py"]

    errors = []

    for filename in files:
        path = gui_dir / filename
        if not path.exists():
            continue

        tree = ast.parse(path.read_text())

        for node in ast.walk(tree):
            # self.method(...) の呼び出しを探す
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            ):
                method_name = node.func.attr

                if method_name in signatures:
                    sig = signatures[method_name]
                    # 引数の数を計算 (selfは除外されている)
                    # Callノードの args と keywords をカウント
                    call_arg_count = len(node.args) + len(node.keywords)

                    # 期待される引数の範囲を計算
                    params = list(sig.parameters.values())
                    min_args = sum(
                        1 for p in params if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                    )
                    has_varargs = any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params)
                    max_args = len(params) if not has_varargs else float("inf")

                    if call_arg_count < min_args or (call_arg_count > max_args and not has_varargs):
                        errors.append(
                            f"{filename}:{node.lineno} - {method_name} expected {min_args}-{max_args} args, but got {call_arg_count}"
                        )

    for err in errors:
        print(err)

if __name__ == "__main__":
    analyze_calls()

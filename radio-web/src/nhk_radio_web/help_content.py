"""ヘルプコンテンツの管理と Markdown→HTML 変換。"""

from pathlib import Path

from markdown_it import MarkdownIt


def _get_help_md_path() -> Path:
    """help.md ファイルへのパスを取得。"""
    return Path(__file__).parent.parent.parent / "help.md"


def render_help_html() -> str:
    """help.md を HTML に変換して返す。

    Returns:
        HTML 文字列
    """
    help_path = _get_help_md_path()
    if not help_path.exists():
        return "<p>ヘルプが見つかりません</p>"

    content = help_path.read_text(encoding="utf-8")
    md = MarkdownIt()
    html = md.render(content)
    return html

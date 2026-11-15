"""キーボードショートカットの一覧。

ステータスバーのヒントとヘルプ本文の両方をここから作り、二重管理を避ける。
キーの割り当て (bind) は build.py と browser.py にある。ここを変えたらそちらも合わせる。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    """1 つのショートカット。

    Attributes:
        keys: キーの表記。複数あれば `/` でつないで表示する。
        description: ヘルプ本文に載せる説明。
        hint: ステータスバーに載せる短い説明。None なら載せない。
    """

    keys: tuple[str, ...]
    description: str
    hint: str | None = None


SHORTCUTS: tuple[Shortcut, ...] = (
    Shortcut(("Ctrl/Cmd + F",), "番組検索欄へフォーカス", "番組検索"),
    Shortcut(("Ctrl/Cmd + L",), "エピソード検索欄へフォーカス", "エピソード検索"),
    Shortcut(("F",), "選択番組のエピソード一覧を取得", "一覧取得"),
    Shortcut(("D",), "選択エピソードをダウンロード", "DL"),
    Shortcut(("F1", "?"), "このヘルプを開く", "ヘルプ"),
    Shortcut(("Esc",), "ヘルプダイアログを閉じる / 表示設定ダイアログを閉じる / 検索欄をクリア"),
    Shortcut(("Ctrl/Cmd + C",), "選択セルの値をクリップボードにコピー"),
)

# ステータスバーのヒントで項目の間に入れる区切り
_HINT_SEPARATOR = "  "


def render_help_line(shortcut: Shortcut) -> str:
    """ヘルプ本文 (Markdown) の 1 行を作る。

    Args:
        shortcut: 対象のショートカット。

    Returns:
        `- `F1` / `?`: 説明` の形の行。
    """
    keys = " / ".join(f"`{key}`" for key in shortcut.keys)
    return f"- {keys}: {shortcut.description}"


def render_help_list() -> str:
    """ヘルプ本文に入れるショートカットの一覧 (Markdown) を作る。"""
    return "\n".join(render_help_line(shortcut) for shortcut in SHORTCUTS)


def render_status_hint() -> str:
    """ステータスバーのヒントを作る。キーの表記からは空白を除いて短くする。"""
    items = [
        " / ".join(key.replace(" ", "") for key in shortcut.keys) + f": {shortcut.hint}"
        for shortcut in SHORTCUTS
        if shortcut.hint is not None
    ]
    return _HINT_SEPARATOR.join(items)

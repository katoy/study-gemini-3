"""ショートカットの一覧を 1 か所で定義し、ステータスバーのヒントとヘルプ本文の両方を作ることの回帰テスト。

GUI レビュー (docs/review-2026-11-08-ui.md) の L6 で残っていた「ヒントとヘルプ本文の二重管理」への対応。
"""

from nhk_radio.gui import shortcuts
from nhk_radio.gui.help_markdown import build_help_markdown


def test_status_hint_keeps_previous_text() -> None:
    """ステータスバーのヒントは、従来の表示と同じ文言になる。"""
    assert shortcuts.render_status_hint() == (
        "Ctrl/Cmd+F: 番組検索  Ctrl/Cmd+L: エピソード検索  F: 一覧取得  D: DL  F1 / ?: ヘルプ"
    )


def test_help_markdown_lists_every_shortcut() -> None:
    """ヘルプ本文には、定義したショートカットがすべて載り、置き換え前の目印は残らない。"""
    markdown = build_help_markdown([])

    assert "{{SHORTCUT_LIST}}" not in markdown
    for shortcut in shortcuts.SHORTCUTS:
        assert shortcuts.render_help_line(shortcut) in markdown


def test_render_help_line_formats_keys_as_code() -> None:
    """ヘルプ本文では、キーをそれぞれコード表記にして `/` でつなぐ。"""
    shortcut = shortcuts.Shortcut(keys=("F1", "?"), description="このヘルプを開く", hint="ヘルプ")
    assert shortcuts.render_help_line(shortcut) == "- `F1` / `?`: このヘルプを開く"


def test_status_hint_skips_shortcuts_without_hint() -> None:
    """ヒントの無いショートカット (Esc など) は、ステータスバーには載せない。"""
    hint = shortcuts.render_status_hint()
    assert "Esc" not in hint
    assert any(s.hint is None for s in shortcuts.SHORTCUTS)

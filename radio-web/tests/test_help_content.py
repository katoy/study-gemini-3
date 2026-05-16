"""ヘルプコンテンツのテスト。"""

from unittest.mock import patch

from nhk_radio_web.help_content import render_help_html


def test_render_help_html_returns_string():
    """render_help_html が HTML 文字列を返す。"""
    result = render_help_html()
    assert isinstance(result, str)
    assert len(result) > 0


def test_render_help_html_contains_expected_sections():
    """render_help_html が期待されるセクションを含む。"""
    result = render_help_html()
    # help.md に含まれるタイトルやセクションが HTML に変換されているか確認
    assert "<h1>" in result or "<h2>" in result  # ヘッダーが存在する
    assert "ヘルプ" in result  # title が含まれる


def test_render_help_html_file_not_found():
    """help.md が見つからない場合、フォールバック HTML を返す。"""
    with patch("nhk_radio_web.help_content._get_help_md_path") as mock_path:
        mock_path.return_value.exists.return_value = False
        result = render_help_html()
        assert result == "<p>ヘルプが見つかりません</p>"

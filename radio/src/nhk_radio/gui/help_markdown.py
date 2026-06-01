"""Markdown-backed help loading and Tk rendering helpers."""

import re
from importlib import resources

from ..constants import GENRE_LABELS, NHK_GENRES
from ..text import _normalize_text
from ..types import Program


def build_help_markdown(programs: list[Program]) -> str:
    template = resources.files("nhk_radio").joinpath("help.md").read_text(encoding="utf-8")
    return template.replace("{{GENRE_LIST}}", _render_genre_list_markdown()).replace(
        "{{CORNER_LIST}}", _render_corner_list_markdown(programs)
    )


def _render_genre_list_markdown() -> str:
    return "\n".join(f"- `{genre}`: {GENRE_LABELS.get(genre, genre)}" for genre in NHK_GENRES)


def _render_corner_list_markdown(programs: list[Program]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for program in sorted(
        programs,
        key=lambda item: (
            _normalize_text(item.corner_name or ""),
            item.site_id or "",
            item.corner_id or "",
        ),
    ):
        site_id = (program.site_id or "").strip()
        corner_id = (program.corner_id or "").strip()
        corner_name = _normalize_text(program.corner_name or "")
        if not site_id or not corner_id or not corner_name:
            continue
        key = f"{site_id}_{corner_id}"
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- `{key}`: {corner_name}")
    if not lines:
        return "- `(no loaded corner_name data)`: 読み込み済みデータに corner_name はありません"
    return "\n".join(lines)


def render_help_markdown(text_widget, markdown: str, palette: dict[str, str], fonts: dict[str, tuple]) -> None:
    text_widget.configure(state="normal")
    text_widget.delete("1.0", "end")
    _configure_help_tags(text_widget, palette, fonts)

    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()

        if not stripped:
            text_widget.insert("end", "\n")
            index += 1
            continue

        if stripped.startswith("```"):
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):  # pragma: no cover
                index += 1
            text_widget.insert("end", "\n".join(code_lines).rstrip() + "\n\n", ("codeblock",))
            continue

        if stripped.startswith("# "):
            _insert_inline_segments(text_widget, stripped[2:], "h1", "h1_strong", "h1_code")
            text_widget.insert("end", "\n\n")
            index += 1
            continue
        if stripped.startswith("## "):
            _insert_inline_segments(text_widget, stripped[3:], "h2", "h2_strong", "h2_code")
            text_widget.insert("end", "\n\n")
            index += 1
            continue
        if stripped.startswith("### "):
            _insert_inline_segments(text_widget, stripped[4:], "h3", "h3_strong", "h3_code")
            text_widget.insert("end", "\n")
            index += 1
            continue

        bullet_match = re.match(r"^([-*])\s+(.*)$", stripped)
        if bullet_match:
            text_widget.insert("end", "• ", ("bullet_marker",))
            _insert_inline_segments(text_widget, bullet_match.group(2), "bullet", "bullet_strong", "bullet_code")
            text_widget.insert("end", "\n")
            index += 1
            continue

        numbered_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if numbered_match:
            text_widget.insert("end", f"{numbered_match.group(1)}. ", ("bullet_marker",))
            _insert_inline_segments(text_widget, numbered_match.group(2), "bullet", "bullet_strong", "bullet_code")
            text_widget.insert("end", "\n")
            index += 1
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if not next_line or next_line.startswith(("#", "```")) or re.match(r"^([-*]|\d+\.)\s+", next_line):
                break
            paragraph_lines.append(next_line)
            index += 1
        _insert_inline_segments(text_widget, " ".join(paragraph_lines), "body", "strong", "inline_code")
        text_widget.insert("end", "\n\n")

    text_widget.configure(state="disabled")


def _configure_help_tags(text_widget, palette: dict[str, str], fonts: dict[str, tuple]) -> None:
    text_widget.configure(
        wrap="word",
        relief="flat",
        bd=0,
        highlightthickness=1,
        background=palette["surface"],
        foreground=palette["text"],
        insertbackground=palette["text"],
        selectbackground=palette["selected_bg"],
        selectforeground=palette["selected_fg"],
        padx=18,
        pady=18,
        spacing1=0,
        spacing3=0,
        cursor="arrow",
    )
    text_widget.tag_configure(
        "body", font=fonts["body"], foreground=palette["text"], lmargin1=0, lmargin2=0, spacing3=6
    )
    text_widget.tag_configure("strong", font=fonts["strong"], foreground=palette["text"])
    text_widget.tag_configure(
        "inline_code", font=fonts["mono"], foreground=palette["accent_dark"], background=palette["accent_soft"]
    )
    text_widget.tag_configure("h1", font=fonts["h1"], foreground=palette["text"], spacing1=6, spacing3=8)
    text_widget.tag_configure("h2", font=fonts["h2"], foreground=palette["accent"], spacing1=6, spacing3=6)
    text_widget.tag_configure("h3", font=fonts["h3"], foreground=palette["text"], spacing1=4, spacing3=4)
    text_widget.tag_configure("h1_strong", font=fonts["h1"], foreground=palette["text"])
    text_widget.tag_configure("h2_strong", font=fonts["h2"], foreground=palette["accent"])
    text_widget.tag_configure("h3_strong", font=fonts["h3"], foreground=palette["text"])
    text_widget.tag_configure(
        "h1_code", font=fonts["mono"], foreground=palette["accent_dark"], background=palette["accent_soft"]
    )
    text_widget.tag_configure(
        "h2_code", font=fonts["mono"], foreground=palette["accent_dark"], background=palette["accent_soft"]
    )
    text_widget.tag_configure(
        "h3_code", font=fonts["mono"], foreground=palette["accent_dark"], background=palette["accent_soft"]
    )
    text_widget.tag_configure(
        "bullet", font=fonts["body"], foreground=palette["text"], lmargin1=24, lmargin2=24, spacing1=2, spacing3=2
    )
    text_widget.tag_configure(
        "bullet_strong", font=fonts["strong"], foreground=palette["text"], lmargin1=24, lmargin2=24
    )
    text_widget.tag_configure(
        "bullet_code",
        font=fonts["mono"],
        foreground=palette["accent_dark"],
        background=palette["accent_soft"],
        lmargin1=24,
        lmargin2=24,
    )
    text_widget.tag_configure(
        "bullet_marker", font=fonts["strong"], foreground=palette["accent"], lmargin1=8, lmargin2=24
    )
    text_widget.tag_configure(
        "codeblock",
        font=fonts["mono"],
        foreground=palette["text"],
        background=palette["surface_alt"],
        lmargin1=18,
        lmargin2=18,
        rmargin=18,
        spacing1=4,
        spacing3=8,
    )


def _insert_inline_segments(text_widget, text: str, base_tag: str, strong_tag: str, code_tag: str) -> None:
    for kind, value in _split_inline_markdown(text):
        if kind == "strong":
            text_widget.insert("end", value, (strong_tag,))
        elif kind == "code":
            text_widget.insert("end", value, (code_tag,))
        else:
            text_widget.insert("end", value, (base_tag,))


def _split_inline_markdown(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(\*\*.+?\*\*|`.+?`)")
    segments: list[tuple[str, str]] = []
    cursor = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > cursor:
            segments.append(("text", text[cursor:start]))
        token = match.group(0)
        if token.startswith("**") and token.endswith("**"):
            segments.append(("strong", token[2:-2]))
        elif token.startswith("`") and token.endswith("`"):
            segments.append(("code", token[1:-1]))
        else:
            segments.append(("text", token))
        cursor = end
    if cursor < len(text):
        segments.append(("text", text[cursor:]))
    return segments

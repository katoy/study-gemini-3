"""Brand logo widget for the NHK radio downloader."""

from .toolkit import tk


def create_brand_logo(parent, palette: dict[str, str], size: int = 60):
    canvas = tk.Canvas(
        parent,
        width=size,
        height=size,
        highlightthickness=0,
        bd=0,
        relief="flat",
        background=palette["surface"],
    )
    _draw_brand_logo(canvas, palette, size)
    return canvas


def update_brand_logo(canvas, palette: dict[str, str]):
    size = int(canvas.cget("width"))
    canvas.configure(background=palette["surface"])
    _draw_brand_logo(canvas, palette, size)


def _draw_brand_logo(canvas, palette: dict[str, str], size: int):
    canvas.delete("all")

    pad = max(size * 0.12, 7)
    center = size / 2
    orb_size = size - pad * 2
    orb_left = pad
    orb_top = pad
    orb_right = size - pad
    orb_bottom = size - pad

    # 青系の配色を動的に決定
    # palette に "primary_soft" がない場合は primary から生成することを想定するか、
    # 既存の palette 構造に合わせます。
    # 暫定的に primary を使用しつつ、透明度や明るさを調整します。
    primary_color = palette["primary"]
    
    # 円の背景 (薄い青系)
    bg_circle = "#E7F5FF" if palette["bg"].startswith("#F") else "#1A2533"

    canvas.create_oval(
        orb_left,
        orb_top,
        orb_right,
        orb_bottom,
        fill=bg_circle,
        outline=primary_color,
        width=max(size * 0.04, 2),
    )

    wave_width = max(size * 0.045, 2)
    wave_color = primary_color
    arc_box = (
        center - orb_size * 0.28,
        center - orb_size * 0.28,
        center + orb_size * 0.28,
        center + orb_size * 0.28,
    )
    for scale in (1.0, 1.38):
        left, top, right, bottom = arc_box
        cx = (left + right) / 2
        cy = (top + bottom) / 2
        half_w = (right - left) * scale / 2
        half_h = (bottom - top) * scale / 2
        canvas.create_arc(
            cx - half_w,
            cy - half_h,
            cx + half_w,
            cy + half_h,
            start=305,
            extent=110,
            style="arc",
            outline=wave_color,
            width=wave_width,
        )

    triangle = (
        center - orb_size * 0.12,
        center - orb_size * 0.18,
        center - orb_size * 0.12,
        center + orb_size * 0.18,
        center + orb_size * 0.18,
        center,
    )
    canvas.create_polygon(
        triangle,
        fill=primary_color,
        outline=primary_color,
        width=max(size * 0.025, 1),
        smooth=True,
    )
    canvas.create_oval(
        center - orb_size * 0.04,
        center - orb_size * 0.04,
        center + orb_size * 0.04,
        center + orb_size * 0.04,
        fill=palette["surface"],
        outline="",
    )

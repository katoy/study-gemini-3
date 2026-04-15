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

    canvas.create_oval(
        orb_left,
        orb_top,
        orb_right,
        orb_bottom,
        fill=palette["accent_soft"],
        outline=palette["accent"],
        width=max(size * 0.04, 2),
    )

    wave_width = max(size * 0.045, 2)
    wave_color = palette["accent_dark"]
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
        fill=palette["accent"],
        outline=palette["accent_dark"],
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

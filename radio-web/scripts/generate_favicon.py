#!/usr/bin/env python3
"""NHK ラジオアイコンを生成して favicon として出力。"""

from pathlib import Path

from PIL import Image, ImageDraw


def draw_nhk_radio_logo(size: int = 256) -> Image.Image:
    """NHK ラジオの波ロゴを描画。"""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # 色設定
    primary_color = "#0078D4"  # NHK ラジオ青
    bg_circle_color = "#E7F5FF"  # 薄い青系背景

    pad = max(size * 0.12, 7)
    center = size / 2
    orb_size = size - pad * 2

    # 外側の円
    draw.ellipse(
        [pad, pad, size - pad, size - pad],
        fill=bg_circle_color,
        outline=primary_color,
        width=max(int(size * 0.04), 2),
    )

    # 波のアーク（2段階）
    wave_width = max(int(size * 0.045), 2)
    arc_box_size = orb_size * 0.28

    for scale in (1.0, 1.38):
        half_w = arc_box_size * scale / 2
        half_h = arc_box_size * scale / 2
        draw.arc(
            [
                center - half_w,
                center - half_h,
                center + half_w,
                center + half_h,
            ],
            start=305,
            end=415,
            fill=primary_color,
            width=wave_width,
        )

    # 再生ボタン（三角形）
    triangle_offset = orb_size * 0.12
    triangle_height = orb_size * 0.18
    triangle = [
        center - triangle_offset,
        center - triangle_height,
        center - triangle_offset,
        center + triangle_height,
        center + triangle_offset * 1.5,
        center,
    ]
    draw.polygon(triangle, fill=primary_color, outline=primary_color)

    # 中央の円（装飾）
    circle_size = orb_size * 0.04
    draw.ellipse(
        [
            center - circle_size,
            center - circle_size,
            center + circle_size,
            center + circle_size,
        ],
        fill=(255, 255, 255, 0),
    )

    return img


def main():
    project_root = Path(__file__).resolve().parent.parent
    static_dir = project_root / "static"
    static_dir.mkdir(exist_ok=True)

    # PNG として出力（256x256）
    logo_png = draw_nhk_radio_logo(256)
    favicon_png_path = static_dir / "favicon-256.png"
    logo_png.save(favicon_png_path, "PNG")
    print(f"✓ PNG ファイルを生成: {favicon_png_path}")

    # favicon.ico へ変換（複数サイズ）
    sizes = [16, 32, 64, 128, 256]
    icons = [draw_nhk_radio_logo(size) for size in sizes]

    favicon_path = static_dir / "favicon.ico"
    icons[0].save(favicon_path, "ICO", sizes=[(size, size) for size in sizes])
    print(f"✓ favicon.ico を生成: {favicon_path}")


if __name__ == "__main__":
    main()

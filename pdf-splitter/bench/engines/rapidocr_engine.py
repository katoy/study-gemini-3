#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "rapidocr==3.10.0",
#     "onnxruntime",
# ]
# ///
"""RapidOCR (PP-OCRv6, 日本語指定) で画像を OCR し、ページごとのテキストと処理時間を書き出す。"""

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np
from rapidocr import RapidOCR

LANG = "japan"
# 縦書き本文の列幅に対して、これより細い縦長の枠はルビとみなして捨てる（ルビは列幅の約 0.65 倍）
RUBY_WIDTH_RATIO = 0.75


def order_vertical(boxes: np.ndarray, texts: tuple[str, ...]) -> list[str]:
    """
    縦書きページの認識結果を読み順に並べる。

    横長の枠（ヘッダー・フッター）は上から順、縦長の枠（本文の列）は右から順に並べ、
    本文の列幅より明らかに細い枠（ルビ）と、列幅より小さい横長の枠（ウィンドウの●など）は除外する。
    """
    items = []
    for box, text in zip(boxes, texts):
        (left, top), (right, bottom) = box.min(axis=0), box.max(axis=0)
        items.append((left, top, right, bottom, text))
    columns = [it for it in items if it[3] - it[1] > it[2] - it[0]]
    if not columns:
        return [it[4] for it in sorted(items, key=lambda it: (it[1], it[0]))]

    column_width = statistics.median(it[2] - it[0] for it in columns)
    min_width = column_width * RUBY_WIDTH_RATIO
    body_top = min(it[1] for it in columns)
    lines = [it for it in items if it[2] - it[0] > it[3] - it[1] and it[2] - it[0] >= column_width]

    def row_order(it: tuple) -> tuple[int, float]:
        # 上端の差が列幅未満の枠は同じ行とみなし、行内は左から並べる
        return round(it[1] / column_width), it[0]

    header = sorted((it for it in lines if it[1] < body_top), key=row_order)
    footer = sorted((it for it in lines if it[1] >= body_top), key=row_order)
    body = sorted((it for it in columns if it[2] - it[0] >= min_width), key=lambda it: -it[2])
    return [it[4] for it in [*header, *body, *footer]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="OCR する画像ファイル")
    parser.add_argument("--out", type=Path, required=True, help="結果の出力ディレクトリ")
    parser.add_argument("--vertical", action="store_true", help="縦書きとして読み順を並べ替える")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    engine = RapidOCR(params={"Det.lang_type": LANG, "Rec.lang_type": LANG})
    timings: dict[str, float] = {}
    for image_path in args.images:
        start = time.perf_counter()
        result = engine(str(image_path))
        timings[image_path.stem] = time.perf_counter() - start
        texts = result.txts or ()
        if args.vertical and texts:
            lines = order_vertical(result.boxes, texts)
        else:
            lines = list(texts)
        (args.out / f"{image_path.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{image_path.name}: {timings[image_path.stem]:.2f}s")
    (args.out / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

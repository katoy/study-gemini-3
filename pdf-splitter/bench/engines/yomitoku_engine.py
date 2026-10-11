#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#     "yomitoku==0.15.0",
# ]
# ///
"""
YomiToku で画像を OCR し、ページごとのテキストと処理時間を書き出す。

段落 (paragraphs) を YomiToku の読み順 (order) で並べ、ルビは除外する。
--lite で CPU 向けの軽量モデルを使う。
"""

import argparse
import json
import time
from pathlib import Path

import cv2
from yomitoku import DocumentAnalyzer

DEVICE = "cpu"
# CLI の --lite に相当する設定（README の「Python API から軽量モードを利用する」より）
LITE_CONFIGS = {
    "ocr": {
        "text_recognizer": {
            "model_name": "parseq-tiny-dynw-v4",
            "dynamic_width": True,
            "batch_bucketing": True,
            "device": DEVICE,
        },
        "text_detector": {"device": DEVICE, "infer_onnx": True},
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="OCR する画像ファイル")
    parser.add_argument("--out", type=Path, required=True, help="結果の出力ディレクトリ")
    parser.add_argument("--lite", action="store_true", help="軽量モデルを使う")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    analyzer = DocumentAnalyzer(
        configs=LITE_CONFIGS if args.lite else {}, device=DEVICE, ignore_ruby=True
    )
    timings: dict[str, float] = {}
    for image_path in args.images:
        image = cv2.imread(str(image_path))
        start = time.perf_counter()
        results, _, _ = analyzer(image)
        timings[image_path.stem] = time.perf_counter() - start
        paragraphs = sorted(results.paragraphs, key=lambda p: (p.order is None, p.order or 0))
        text = "\n".join(p.contents for p in paragraphs)
        (args.out / f"{image_path.stem}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"{image_path.name}: {timings[image_path.stem]:.2f}s")
    (args.out / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

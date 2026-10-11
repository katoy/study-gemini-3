#!/usr/bin/env python3
"""
Tesseract（現行の ocrmypdf と同じ -l jpn+eng）で画像を OCR し、
ページごとのテキストと処理時間を書き出す。
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

DEFAULT_LANG = "jpn+eng"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="OCR する画像ファイル")
    parser.add_argument("--out", type=Path, required=True, help="結果の出力ディレクトリ")
    parser.add_argument("--lang", default=DEFAULT_LANG, help="Tesseract の言語 (縦書きは jpn_vert)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    for image_path in args.images:
        start = time.perf_counter()
        completed = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", args.lang],
            check=True,
            capture_output=True,
            text=True,
        )
        timings[image_path.stem] = time.perf_counter() - start
        (args.out / f"{image_path.stem}.txt").write_text(completed.stdout, encoding="utf-8")
        print(f"{image_path.name}: {timings[image_path.stem]:.2f}s")
    (args.out / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

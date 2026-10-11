#!/usr/bin/env python3
"""
NDLOCR-Lite (ndl-lab/ndlocr-lite) の ocr.py を実行し、ページごとのテキストと処理時間を書き出す。

ocr.py は <stem>.txt を出力先に直接書くので、ここでは処理時間 (timings.json) だけを補う。
NDLOCR-Lite の依存は requirements.txt で固定されているため、uv の一時環境で実行する。
"""

import argparse
import glob
import json
import os
import re
import subprocess
from pathlib import Path

IMAGE_EXTS = {"jpg", "jpeg", "png", "tiff", "tif", "jp2", "bmp", "webp"}
TIME_RE = re.compile(r"^Total calculation time \(Detection \+ Recognition\): ([\d.]+)$", re.M)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sourcedir", type=Path, help="OCR する画像のディレクトリ")
    parser.add_argument("--out", type=Path, required=True, help="結果の出力ディレクトリ")
    parser.add_argument("--ndlocr-dir", type=Path, required=True, help="ndlocr-lite を clone したディレクトリ")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "uv", "run", "-q", "--no-project", "--python", "3.12",
            "--with-requirements", str(args.ndlocr_dir / "requirements.txt"),
            "python", "ocr.py",
            "--sourcedir", str(args.sourcedir.resolve()),
            "--output", str(args.out.resolve()),
        ],
        cwd=args.ndlocr_dir / "src",
        check=True,
        capture_output=True,
        text=True,
    )
    # ocr.py と同じ glob の順で画像が処理され、1 枚ごとに処理時間が 1 行出力される
    images = [
        Path(p) for p in glob.glob(os.path.join(args.sourcedir.resolve(), "*"))
        if p.rsplit(".", 1)[-1].lower() in IMAGE_EXTS
    ]
    seconds = [float(s) for s in TIME_RE.findall(completed.stdout)]
    if len(seconds) != len(images):
        raise RuntimeError(f"処理時間の行数 ({len(seconds)}) が画像数 ({len(images)}) と一致しません")
    timings = {image.stem: sec for image, sec in zip(images, seconds)}
    for stem, sec in timings.items():
        print(f"{stem}: {sec:.2f}s")
    (args.out / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

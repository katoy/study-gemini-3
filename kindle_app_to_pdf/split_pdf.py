#!/usr/bin/env python3
"""
PDF を指定サイズ以下に分割するスクリプト。

使い方:
    python split_pdf.py <input.pdf> [--max-mb 200] [--output-dir ./output]
"""

import argparse
import io
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def split_pdf(input_path: str, max_mb: float, output_dir: str) -> list[str]:
    """
    PDF を max_mb MB 以下のファイルに分割する。

    Args:
        input_path: 入力 PDF のパス
        max_mb: 分割後の最大ファイルサイズ（MB）
        output_dir: 出力ディレクトリ

    Returns:
        生成したファイルパスのリスト
    """
    max_bytes = int(max_mb * 1024 * 1024)
    input_file = Path(input_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(input_path)
    total_pages = len(reader.pages)
    print(f"入力: {input_file.name}  ({input_file.stat().st_size / 1_048_576:.1f} MB, {total_pages} ページ)")

    output_files: list[str] = []
    part = 1
    start = 0

    while start < total_pages:
        # 二分探索で max_bytes に収まる最大ページ数を求める
        lo, hi = 1, total_pages - start
        best_end = start + 1  # 少なくとも 1 ページは書き出す

        while lo <= hi:
            mid = (lo + hi) // 2
            end = start + mid

            # 試し書き
            writer = PdfWriter()
            for i in range(start, end):
                writer.add_page(reader.pages[i])

            buf = io.BytesIO()
            writer.write(buf)
            size = buf.tell()

            if size <= max_bytes:
                best_end = end
                lo = mid + 1
            else:
                hi = mid - 1

        # 1 ページでも超える場合はそのまま書き出す（分割不可能なケース）
        end = best_end

        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        stem = input_file.stem
        out_path = out_dir / f"{stem}_part{part:02d}.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)

        size_mb = out_path.stat().st_size / 1_048_576
        print(f"  → {out_path.name}  (ページ {start + 1}〜{end}, {size_mb:.1f} MB)")
        output_files.append(str(out_path))

        start = end
        part += 1

    print(f"\n合計 {len(output_files)} ファイルに分割しました。")
    return output_files


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF を指定サイズ以下に分割します")
    parser.add_argument("input", help="入力 PDF ファイルのパス")
    parser.add_argument("--max-mb", type=float, default=200.0,
                        help="分割後の最大サイズ（MB）。デフォルト: 200")
    parser.add_argument("--output-dir", "-o", default="./output",
                        help="出力ディレクトリ。デフォルト: ./output")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"エラー: ファイルが見つかりません: {args.input}", file=sys.stderr)
        sys.exit(1)

    split_pdf(args.input, args.max_mb, args.output_dir)


if __name__ == "__main__":
    main()

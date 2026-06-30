#!/usr/bin/env python3
"""PDF をページ範囲ごとに分割するスクリプト。"""

import io
import math
import shutil
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter  # type: ignore


MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024


def _build_pdf_writer(reader, start_page: int, end_page: int):
    """指定ページ範囲の PDF Writer を作る。"""
    writer = PdfWriter()

    # ページインデックスは 0 ベースなので -1 する
    for page_num in range(start_page - 1, end_page):
        writer.add_page(reader.pages[page_num])

    return writer


def _measure_pdf_size(reader, start_page: int, end_page: int) -> int:
    """指定ページ範囲を PDF 化したときのサイズをバイトで返す。"""
    writer = _build_pdf_writer(reader, start_page, end_page)

    with io.BytesIO() as buffer:
        writer.write(buffer)
        return len(buffer.getvalue())


def _write_pdf_range(reader, start_page: int, end_page: int, output_file: Path) -> None:
    """指定ページ範囲をファイルへ書き出す。"""
    writer = _build_pdf_writer(reader, start_page, end_page)

    with open(output_file, "wb") as file_obj:
        writer.write(file_obj)


def _split_page_range_evenly(
    start_page: int, end_page: int, part_count: int
) -> list[tuple[int, int]]:
    """ページ数がなるべく均等になるように連続範囲へ分割する。"""
    total_pages = end_page - start_page + 1
    if total_pages < 1:
        raise ValueError("start_page は end_page 以下である必要があります")

    part_count = max(1, min(part_count, total_pages))
    base_page_count = total_pages // part_count
    remainder = total_pages % part_count

    page_ranges: list[tuple[int, int]] = []
    current_start = start_page

    for index in range(part_count):
        pages_in_part = base_page_count + (1 if index < remainder else 0)
        current_end = current_start + pages_in_part - 1
        page_ranges.append((current_start, current_end))
        current_start = current_end + 1

    return page_ranges


def _plan_pdf_ranges(
    reader,
    start_page: int,
    end_page: int,
    max_size_bytes: int = MAX_PDF_SIZE_BYTES,
) -> list[tuple[int, int]]:
    """サイズ上限を超えないページ範囲の並びを決める。"""
    total_pages = end_page - start_page + 1
    if total_pages < 1:
        raise ValueError("start_page は end_page 以下である必要があります")

    total_size = _measure_pdf_size(reader, start_page, end_page)
    if total_size <= max_size_bytes:
        return [(start_page, end_page)]

    part_count = max(2, math.ceil(total_size / max_size_bytes))
    part_count = min(part_count, total_pages)

    while part_count <= total_pages:
        page_ranges = _split_page_range_evenly(start_page, end_page, part_count)
        part_sizes = [
            _measure_pdf_size(reader, range_start, range_end)
            for range_start, range_end in page_ranges
        ]

        if max(part_sizes) <= max_size_bytes:
            return page_ranges

        if part_count == total_pages:
            break

        part_count += 1

    raise ValueError(
        "1 ページごとに分割してもサイズ上限を超えるため、"
        f"{start_page}-{end_page} を {max_size_bytes} バイト以下にできません"
    )


def split_pdf(
    input_path: str,
    output_dir: str,
    chapters_list: list[list],
    max_size_bytes: int = MAX_PDF_SIZE_BYTES,
) -> None:
    """PDF をページ範囲ごとに分割する。

    Args:
        input_path: 入力 PDF ファイルのパス
        output_dir: 出力ディレクトリのパス
        chapters_list: チャプター名、開始ページ、終了ページのリスト [[name, start, end], ...]
        max_size_bytes: 1 ファイルあたりの上限サイズ
    """
    reader = PdfReader(input_path)
    output_path = Path(output_dir)

    # 出力ディレクトリをクリアする
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    for chapter_info in chapters_list:
        chapter_name, start_page, end_page = chapter_info
        page_ranges = _plan_pdf_ranges(
            reader, start_page, end_page, max_size_bytes=max_size_bytes
        )

        if len(page_ranges) == 1:
            output_file = output_path / f"{chapter_name}.pdf"
            _write_pdf_range(reader, start_page, end_page, output_file)
            print(f"✓ {output_file.name} を作成しました（ページ {start_page}-{end_page}）")
            continue

        part_width = max(2, len(str(len(page_ranges))))
        for index, (range_start, range_end) in enumerate(page_ranges, start=1):
            output_file = output_path / f"{chapter_name}_part{index:0{part_width}d}.pdf"
            _write_pdf_range(reader, range_start, range_end, output_file)
            print(
                f"✓ {output_file.name} を作成しました（ページ {range_start}-{range_end}）"
            )


if __name__ == "__main__":
    # 章構成の定義: [章名, 開始ページ, 終了ページ]
    chapters = [
        ["ch_00", 1, 12],
        ["ch_01", 13, 26],
        ["ch_02", 27, 64],
        ["ch_03", 65, 92],
        ["ch_04", 87, 108],
        ["ch_05", 109, 136],
        ["ch_06", 137, 184],
        ["ch_07", 185, 230],
        ["ch_08", 231, 262],
        ["ch_09", 263, 298],
        ["ch_10", 299, 346],
        ["ch_11", 347, 372],
    ]

    input_pdf = "./Kindle_12.pdf"
    output_directory = "./chapters"

    split_pdf(input_pdf, output_directory, chapters)
    print(f"\n完了。すべての PDF は {output_directory}/ に保存されました。")

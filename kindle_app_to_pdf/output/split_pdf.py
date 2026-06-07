#!/usr/bin/env python3
"""PDF をページ範囲ごとに分割するスクリプト。"""

from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter  # type: ignore


def split_pdf(input_path: str, output_dir: str, chapters: dict[str, tuple[int, int]]) -> None:
    """PDF をページ範囲ごとに分割する。

    Args:
        input_path: 入力 PDF ファイルのパス
        output_dir: 出力ディレクトリのパス
        chapters: チャプター名とページ範囲のマッピング
    """
    reader = PdfReader(input_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for chapter_name, (start_page, end_page) in chapters.items():
        writer = PdfWriter()

        # ページインデックスは 0 ベースなので -1 する
        for page_num in range(start_page - 1, end_page):
            writer.add_page(reader.pages[page_num])

        output_file = output_path / f"{chapter_name}.pdf"
        with open(output_file, "wb") as f:
            writer.write(f)

        print(f"✓ {chapter_name}.pdf を作成しました（ページ {start_page}-{end_page}）")


if __name__ == "__main__":
    chapters = {
        "ch_00": (1, 10),
        "ch_01": (11, 40),
        "ch_02": (41, 66),
        "ch_03": (67, 92),
        "ch_04": (93, 116),
        "ch_05": (117, 146),
        "ch_06": (147, 170),
        "ch_07": (171, 204),
        "ch_08": (205, 214),
        "ch_09": (215, 226),
    }

    input_pdf = "./Kindle_7.pdf"
    output_directory = "./chapters"

    split_pdf(input_pdf, output_directory, chapters)
    print(f"\n完了。すべての PDF は {output_directory}/ に保存されました。")

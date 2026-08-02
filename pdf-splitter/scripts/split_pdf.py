#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pypdf",
# ]
# ///
"""
PDF 分割スクリプト
フォルダ内のすべての PDF を ocrmypdf で OCR 処理し、20MB 以下に分割します。
"""

import os
import sys
import shutil
from pathlib import Path
from typing import List

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter

import pdf_utils


def split_pdf(pdf_path: str, output_dir: str, base_filename: str) -> List[str]:
    """
    PDF を分割します。
    各パートがなるべく同じページ数になるように分割します。
    """
    try:
        file_size_mb = pdf_utils.get_file_size_mb(pdf_path)
        page_count = pdf_utils.get_page_count(pdf_path)

        if page_count == 0:
            print(f"⚠️  スキップ: {base_filename} (ページ数を取得できません)")
            return []

        # 分割数を計算
        num_parts = max(1, int(__import__('math').ceil(file_size_mb / 20)))

        if num_parts == 1:
            # 20MB 以下なのでコピーするだけ
            output_path = os.path.join(output_dir, base_filename)
            shutil.copy2(pdf_path, output_path)
            print(f"✓ コピー: {base_filename} ({file_size_mb:.2f} MB)")
            return [output_path]

        # 分割処理
        print(f"📄 分割中: {base_filename}")
        print(f"   ファイルサイズ: {file_size_mb:.2f} MB")
        print(f"   ページ数: {page_count}")
        print(f"   分割数: {num_parts} 個に分割")

        reader = PdfReader(pdf_path)
        pages_per_part = max(1, int(__import__('math').ceil(page_count / num_parts)))

        output_files = []

        for part_num in range(num_parts):
            writer = PdfWriter()

            start_page = part_num * pages_per_part
            end_page = min((part_num + 1) * pages_per_part, page_count)

            # このパートにページを追加
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])

            # ファイル名を生成（拡張子なしの部分と拡張子を分離）
            name_without_ext = base_filename.rsplit('.', 1)[0]
            output_filename = f"{name_without_ext}_part{part_num + 1}.pdf"
            output_path = os.path.join(output_dir, output_filename)

            # ファイルを保存
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)

            output_size_mb = pdf_utils.get_file_size_mb(output_path)
            output_files.append(output_path)
            print(f"   ✓ {output_filename} ({end_page - start_page} ページ, {output_size_mb:.2f} MB)")

        return output_files

    except Exception as e:
        print(f"❌ エラー: {base_filename} の分割に失敗しました: {e}")
        return []


def process_folder(folder_path: str) -> None:
    """
    フォルダ内のすべての PDF を処理します。
    """
    folder_path = Path(folder_path).resolve()

    if not folder_path.exists():
        print(f"❌ エラー: フォルダが見つかりません: {folder_path}")
        sys.exit(1)

    if not folder_path.is_dir():
        print(f"❌ エラー: これはフォルダではありません: {folder_path}")
        sys.exit(1)

    if not pdf_utils.ensure_ocrmypdf_installed():
        print("❌ エラー: ocrmypdf がインストールされていません。'brew install ocrmypdf' 等を実行してください。", file=sys.stderr)
        sys.exit(1)


    # PDF ファイルを検出 (split_output 配下のファイルは除外)
    pdf_files = sorted([p for p in folder_path.glob("*.pdf") if p.parent == folder_path])

    if not pdf_files:
        print(f"⚠️  PDF ファイルが見つかりません: {folder_path}")
        return

    print(f"📁 フォルダ: {folder_path}")
    print(f"📄 対象 PDF ファイル数: {len(pdf_files)}\n")

    # 出力フォルダを作成
    output_dir = folder_path / "split_output"
    output_dir.mkdir(exist_ok=True)
    print(f"📁 出力フォルダ: {output_dir}\n")

    # 各 PDF を処理
    total_files = 0
    total_parts = 0

    for pdf_file in pdf_files:
        base_filename = pdf_file.name
        print(f"\n--- 処理開始: {base_filename} ---")
        
        # 1. まず ocrmypdf で OCR 処理を行う
        ocr_temp_pdf = output_dir / f"{pdf_file.stem}_ocr_temp.pdf"
        ocr_success = pdf_utils.run_ocr(pdf_file, ocr_temp_pdf)
        
        if ocr_success:
            # 2. OCR済みPDFを分割対象として処理する
            result = split_pdf(str(ocr_temp_pdf), str(output_dir), base_filename)
            
            # 一時ファイルを削除
            if ocr_temp_pdf.exists():
                ocr_temp_pdf.unlink()
                
            if result:
                total_files += 1
                total_parts += len(result)
        else:
            print(f"❌ {base_filename} のOCR処理に失敗したため、分割処理をスキップします。")

    # 結果をサマリー
    print(f"\n{'='*50}")
    print("✅ 処理完了")
    print(f"   処理済みファイル: {total_files}")
    print(f"   出力ファイル: {total_parts}")
    print(f"   出力先: {output_dir}")
    print(f"{'='*50}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用法: uv run split_pdf.py <フォルダパス>")
        sys.exit(1)

    folder_path = sys.argv[1]
    process_folder(folder_path)

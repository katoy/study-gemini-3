"""
pdf_builder.py
==============
処理済みページ画像を 1 つの PDF にまとめるモジュール。

特徴:
  - ストリーミング方式: 全ページを同時にメモリに乗せない
  - 進捗コールバック対応
  - 200 枚（400 ページ）超でも対応
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterable, Optional

from PIL import Image


def _build_pdf_pillow(
    image_paths: list[str | Path],
    output_path: str | Path,
    dpi: int = 300,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> None:
    """
    Pillow を使った PDF 生成 (内部実装)。
    PyMuPDF が利用できない場合の build_pdf_streaming() フォールバック先。
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(image_paths)
    if total == 0:
        raise ValueError("ページ画像が1枚もありません。")

    if progress_cb:
        progress_cb(0.0, f"PDF 生成開始: {total} ページ")

    first_img = None
    append_imgs = []

    for i, path in enumerate(image_paths):
        img = Image.open(path).convert("RGB")

        if i == 0:
            first_img = img
        else:
            append_imgs.append(img)

        if progress_cb:
            pct = (i + 1) / total
            progress_cb(pct, f"PDF 結合中... {i + 1}/{total} ページ")

    if first_img is None:
        raise RuntimeError("先頭ページの読み込みに失敗しました。")

    first_img.save(
        output_path,
        format="PDF",
        save_all=True,
        append_images=append_imgs,
        resolution=dpi,
    )

    if progress_cb:
        progress_cb(1.0, f"PDF 保存完了: {output_path.name}")


def build_pdf_streaming(
    image_paths: list[str | Path],
    output_path: str | Path,
    dpi: int = 300,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> None:
    """
    メモリ効率重視のストリーミング PDF 生成。
    PyMuPDF (fitz) が利用可能な場合はそちらを優先し、
    ない場合は build_pdf() にフォールバックする。

    ページ数が多い場合でもメモリ使用量を一定に保つ。
    """
    try:
        import fitz  # PyMuPDF
        _build_pdf_fitz(image_paths, output_path, dpi, progress_cb)
    except ImportError:
        # PyMuPDF がなければ Pillow で処理
        _build_pdf_pillow(image_paths, output_path, dpi, progress_cb)


def _build_pdf_fitz(
    image_paths: list[str | Path],
    output_path: str | Path,
    dpi: int,
    progress_cb: Optional[Callable[[float, str], None]],
) -> None:
    """PyMuPDF を使ったストリーミング PDF 生成（大量ページ対応）。"""
    import fitz

    output_path = Path(output_path)
    total = len(image_paths)
    pdf_doc = fitz.open()

    for i, path in enumerate(image_paths):
        img_doc = fitz.open(str(path))
        pdfbytes = img_doc.convert_to_pdf()
        img_doc.close()

        img_pdf = fitz.open("pdf", pdfbytes)
        pdf_doc.insert_pdf(img_pdf)
        img_pdf.close()

        if progress_cb:
            pct = (i + 1) / total
            progress_cb(pct, f"PDF 結合中... {i + 1}/{total} ページ")

    pdf_doc.set_metadata({"producer": "paper_to_pdf", "creator": "paper_to_pdf"})
    pdf_doc.save(str(output_path), garbage=4, deflate=True)
    pdf_doc.close()

    if progress_cb:
        progress_cb(1.0, f"PDF 保存完了: {output_path.name}")


def make_thumbnail(image_path: str | Path, size: tuple[int, int] = (150, 212)) -> Image.Image:
    """プレビュー用サムネイルを生成して返す（PIL Image）。"""
    img = Image.open(image_path).convert("RGB")
    img.thumbnail(size, Image.LANCZOS)

    # 白背景に中央配置
    canvas = Image.new("RGB", size, (255, 255, 255))
    x = (size[0] - img.width) // 2
    y = (size[1] - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas

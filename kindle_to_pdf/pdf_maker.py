"""
スクリーンショット画像から PDF を生成するモジュール。
img2pdf を使用して、画像を劣化させることなく PDF に結合します。
"""

import logging
from pathlib import Path
from typing import List

import img2pdf

logger = logging.getLogger(__name__)


def make_pdf(
    screenshots: List[str],
    output_path: str,
) -> None:
    """
    スクリーンショット画像から PDF を生成します。

    Args:
        screenshots:  画像ファイルパスのリスト（ページ順）
        output_path:  出力する PDF の保存先パス
    """
    if not screenshots:
        raise ValueError("スクリーンショットが 0 枚です。")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("画像を PDF に結合中 (%d ページ)...", len(screenshots))

    with open(output_path, "wb") as f:
        f.write(img2pdf.convert(screenshots))

    size_mb = output_file.stat().st_size / 1_048_576
    logger.info("PDF 生成完了: %s (%.1f MB)", output_path, size_mb)

"""
core/constants.py
=================
複数モジュールで共有する定数。
"""

# テキスト密度の最低閾値。これ未満のページは疎すぎてスキップ・チェック不能とみなす。
# image_processor.deskew_page と steps.quality_check で共用。
MIN_TEXT_DENSITY: float = 0.005

# 一時ページ画像の JPEG 品質。processor._run_pipeline で使用。
JPEG_QUALITY: int = 92

"""
processor.py
============
書籍処理パイプラインを管理するコアモジュール。
"""

from __future__ import annotations

import logging
import tempfile
import shutil
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from core.config import ProcessingConfig
from core.pipeline import Pipeline
from dewarper import Dewarper
from steps.detection import DetectionStep
from steps.dewarp import DewarpStep
from steps.enhancement import EnhancementStep
from steps.postprocess import PostProcessStep
from steps.quality_check import QualityCheckStep
from utils.image import fix_exif_rotation, sort_by_filename
from pdf_builder import build_pdf_streaming

# ロガー設定
logger = logging.getLogger(__name__)

class BookProcessor:
    """
    一連の画像処理から PDF 生成までを管理するプロセッサクラス。
    """
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self.tmp_dir: Path | None = None

    def _init_workspace(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="paper_to_pdf_"))
        logger.debug(f"Temporary workspace created: {self.tmp_dir}")

    def _cleanup_workspace(self):
        if self.tmp_dir and self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            logger.debug("Temporary workspace cleaned up.")

    def run(self, input_folder: Path, output_pdf: Path,
            progress_cb: Callable[[float, str], None] | None = None):
        """
        処理パイプラインを実行する。
        """
        self._init_workspace()
        
        # 1. パイプラインの構築
        pipeline = Pipeline(self.config)
        # show_book_area / show_page_area は検出確認モード。
        # 後続の補正ステップをスキップして検出結果をそのまま PDF に出力する。
        run_full = not self.config.show_book_area and not self.config.show_page_area

        # 補正戦略:
        #   dewarpnet / doctr : DetectionStep で見開き全体に AI 湾曲補正を適用（split 前）。
        #                       BM 縮退時はスキップ。その後 DewarpStep で polynomial を各ページに適用。
        #   polynomial        : DetectionStep では補正なし。DewarpStep で各ページに polynomial 適用。
        #   none              : 補正なし。
        spread_dewarper = None
        page_dewarp_mode = "none"
        if run_full and self.config.dewarp_mode != "none":
            if self.config.dewarp_mode in ("dewarpnet", "doctr"):
                spread_dewarper = Dewarper(mode=self.config.dewarp_mode)
            page_dewarp_mode = "polynomial"

        pipeline.add_step(DetectionStep(self.config, dewarper=spread_dewarper,
                                        progress_cb=progress_cb))
        if run_full:
            pipeline.add_step(DewarpStep(self.config, mode=page_dewarp_mode))
            pipeline.add_step(EnhancementStep(self.config))

        # PostProcessStep は検出確認モードでも追加
        # (サイズ正規化と PDF 出力のため。内部でフラグを見て処理を分岐する)
        pipeline.add_step(PostProcessStep(self.config))

        if run_full:
            pipeline.add_step(QualityCheckStep(self.config))
        
        try:
            # 2. ファイルの読み込みとソート
            input_paths = sort_by_filename([
                p for p in input_folder.iterdir()
                if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".bmp", ".tiff", ".tif"}
            ])
            
            if not input_paths:
                raise ValueError(f"No valid images found in {input_folder}")

            logger.info(f"Processing {len(input_paths)} raw images...")
            
            # 3. パイプラインの初期化 (モデルロード等)
            pipeline.initialize()

            processed_paths = []
            total = len(input_paths)

            # 4. 画像処理ループ
            for i, img_path in enumerate(input_paths):
                logger.info(f"[{i+1}/{total}] Processing {img_path.name}")
                if progress_cb:
                    progress_cb(i / total, f"Processing {img_path.name}")

                # 画像読み込み (EXIF回転補正)
                image_bgr = fix_exif_rotation(img_path)
                if image_bgr is None:
                    logger.error(f"Cannot load image: {img_path}")
                    continue

                # パイプライン実行
                logger.debug(f"Running pipeline for {img_path.name}")
                pages = pipeline.run(image_bgr)

                # 結果の保存
                for page_bgr in pages:
                    tmp_path = self.tmp_dir / f"page_{len(processed_paths):05d}.jpg"
                    cv2.imwrite(str(tmp_path), page_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    processed_paths.append(tmp_path)

            # 5. PDF 生成
            if not processed_paths:
                raise RuntimeError("No pages were processed successfully.")

            logger.info(f"Building PDF: {output_pdf}")
            build_pdf_streaming(
                processed_paths,
                output_pdf,
                dpi=self.config.dpi,
                progress_cb=progress_cb
            )

        finally:
            pipeline.finalize()
            self._cleanup_workspace()

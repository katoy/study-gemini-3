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

from core.config import ProcessingConfig, SUPPORTED_EXTENSIONS
from core.constants import JPEG_QUALITY
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

_MAX_FAILURE_RATE = 0.25  # 25% 超で中断


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
            try:
                shutil.rmtree(self.tmp_dir)
            except Exception as e:
                logger.warning("一時ディレクトリの削除に失敗しました %s: %s", self.tmp_dir, e)
            logger.debug("Temporary workspace cleaned up.")

    # ──────────────────────────────────────────────
    # パイプライン構築
    # ──────────────────────────────────────────────

    def _create_pipeline(self, progress_cb: Callable | None) -> Pipeline:
        """設定に基づいてパイプラインを構築して返す。"""
        pipeline = Pipeline(self.config)
        # show_book_area / show_page_area は検出確認モード。
        # 後続の補正ステップをスキップして検出結果をそのまま PDF に出力する。
        run_full = not self.config.show_book_area and not self.config.show_page_area

        # 補正戦略:
        #   dewarpnet / doctr : DetectionStep で見開き全体に AI 湾曲補正を適用（split 前）。
        #   polynomial        : DetectionStep では補正なし。DewarpStep で各ページに polynomial 適用。
        #   none              : 補正なし。
        spread_dewarper = None
        page_dewarp_mode = "none"
        if run_full and self.config.dewarp_mode != "none":
            if self.config.dewarp_mode in ("dewarpnet", "doctr"):
                # 縦書き書籍の見開きに横書き前提の polynomial 補正をかけると、
                # 横組み要素 (図版キャプション等) を水平行として誤検出し、
                # 補正で文字が押し出されて消える。縦書きモードでは無効化する。
                if self.config.writing_mode != "vertical":
                    spread_dewarper = Dewarper(mode=self.config.dewarp_mode)
            # 縦書きページへの分割後 polynomial 補正は、各列の長さの差を
            # 「湾曲」として誤検出して文字を消すため無効化する。
            if self.config.writing_mode == "vertical":
                page_dewarp_mode = "none"
            else:
                page_dewarp_mode = self.config.dewarp_mode

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

        return pipeline

    # ──────────────────────────────────────────────
    # 入力ファイル読み込み
    # ──────────────────────────────────────────────

    def _load_images(self, input_folder: Path) -> list[Path]:
        """対応フォーマットの画像をソートして返す。"""
        paths = sort_by_filename([
            p for p in input_folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ])
        if not paths:
            raise ValueError(f"No valid images found in {input_folder}")
        logger.info(f"Processing {len(paths)} raw images...")
        return paths

    # ──────────────────────────────────────────────
    # 画像処理ループ
    # ──────────────────────────────────────────────

    def _run_pipeline(self, pipeline: Pipeline, input_paths: list[Path],
                      progress_cb: Callable | None) -> list[Path]:
        """全入力画像をパイプラインで処理し、一時ページ画像パスのリストを返す。"""
        processed_paths: list[Path] = []
        failed_images: list[str] = []
        total = len(input_paths)

        for i, img_path in enumerate(input_paths):
            logger.info(f"[{i+1}/{total}] Processing {img_path.name}")
            if progress_cb:
                progress_cb(i / total, f"Processing {img_path.name}")

            # 画像読み込み (EXIF回転補正)
            image_bgr = fix_exif_rotation(img_path)
            if image_bgr is None:
                logger.error(f"Cannot load image: {img_path}")
                failed_images.append(img_path.name)
                continue

            # パイプライン実行
            logger.debug(f"Running pipeline for {img_path.name}")
            try:
                pages = pipeline.run(image_bgr)
            except Exception as e:
                logger.error(f"Pipeline failed for {img_path.name}: {e}")
                failed_images.append(img_path.name)
                continue

            # 結果の保存
            write_failed = False
            for page_bgr in pages:
                tmp_path = self.tmp_dir / f"page_{len(processed_paths):05d}.jpg"
                success = cv2.imwrite(str(tmp_path), page_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if not success:
                    logger.error("ページ画像の書き込みに失敗しました: %s (画像: %s)",
                                 tmp_path, img_path.name)
                    write_failed = True
                    break
                processed_paths.append(tmp_path)
            if write_failed:
                failed_images.append(img_path.name)
                continue

        # 処理結果サマリー
        succeeded = total - len(failed_images)
        if failed_images:
            logger.warning(
                "処理結果: %d/%d 成功, %d 件失敗: %s",
                succeeded, total, len(failed_images), ", ".join(failed_images)
            )
            failure_rate = len(failed_images) / total
            if failure_rate > _MAX_FAILURE_RATE:
                raise RuntimeError(
                    f"失敗率が{int(_MAX_FAILURE_RATE * 100)}%を超えました"
                    f" ({len(failed_images)}/{total} 件失敗)。処理を中断します。"
                )
        else:
            logger.info("処理結果: %d/%d 成功", succeeded, total)

        return processed_paths

    # ──────────────────────────────────────────────
    # メインエントリポイント
    # ──────────────────────────────────────────────

    def run(self, input_folder: Path, output_pdf: Path,
            progress_cb: Callable[[float, str], None] | None = None):
        """処理パイプラインを実行する。"""
        self._init_workspace()
        pipeline = self._create_pipeline(progress_cb)
        try:
            input_paths = self._load_images(input_folder)
            pipeline.initialize()
            processed_paths = self._run_pipeline(pipeline, input_paths, progress_cb)

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
            try:
                pipeline.finalize()
            except Exception as e:
                logger.warning("pipeline.finalize() failed: %s", e)
            self._cleanup_workspace()

"""
processor.py のテスト。
"""
from unittest.mock import patch, MagicMock

import cv2
import numpy as np
import pytest

from core.config import ProcessingConfig


# ── BookProcessor のテスト ────────────────────────────────────────────
# 重いモデルロード・実際のパイプライン実行はモックで代替する。

class TestBookProcessor:
    def _make_input_dir(self, tmp_path, n_images=2):
        """入力画像ディレクトリを作成する。"""
        img_dir = tmp_path / "input"
        img_dir.mkdir()
        for i in range(n_images):
            img = np.full((300, 200, 3), 200, dtype=np.uint8)
            cv2.imwrite(str(img_dir / f"img{i:02d}.jpg"), img)
        return img_dir

    def _make_processor(self, **cfg_kwargs):
        from processor import BookProcessor
        cfg = ProcessingConfig(**cfg_kwargs)
        return BookProcessor(cfg)

    def test_init_workspace_creates_dir(self):
        from processor import BookProcessor
        cfg = ProcessingConfig()
        proc = BookProcessor(cfg)
        proc._init_workspace()
        assert proc.tmp_dir is not None
        assert proc.tmp_dir.exists()
        proc._cleanup_workspace()

    def test_cleanup_workspace_removes_dir(self):
        from processor import BookProcessor
        cfg = ProcessingConfig()
        proc = BookProcessor(cfg)
        proc._init_workspace()
        tmp = proc.tmp_dir
        proc._cleanup_workspace()
        assert not tmp.exists()

    def test_cleanup_idempotent_when_no_dir(self):
        from processor import BookProcessor
        cfg = ProcessingConfig()
        proc = BookProcessor(cfg)
        proc._cleanup_workspace()  # tmp_dir=None でもクラッシュしない

    def test_run_basic(self, tmp_path):
        """基本的な処理フローがクラッシュなく終了する。"""
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=2)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(
            dewarp_mode="none",
            ai_enhance=False,
            split=False,
            border=False,
            shadow_strength=0.0,
        )
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming") as mock_pdf:
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.run.return_value = [
                np.full((300, 200, 3), 200, dtype=np.uint8)
            ]
            MockPipeline.return_value = mock_pipeline_inst

            proc.run(img_dir, out_pdf)
            mock_pdf.assert_called_once()

    def test_run_no_images_raises(self, tmp_path):
        """入力ディレクトリが空の場合は ValueError。"""
        from processor import BookProcessor
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="none")
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline:
            MockPipeline.return_value = MagicMock()
            with pytest.raises(ValueError, match="No valid images"):
                proc.run(empty_dir, out_pdf)

    def test_run_with_show_book_area(self, tmp_path):
        """show_book_area モードではパイプライン構成が変わる。"""
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=1)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="none", show_book_area=True)
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming"):
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.run.return_value = [
                np.full((300, 200, 3), 200, dtype=np.uint8)
            ]
            MockPipeline.return_value = mock_pipeline_inst
            proc.run(img_dir, out_pdf)

    def test_run_with_show_page_area(self, tmp_path):
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=1)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="none", show_page_area=True)
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming"):
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.run.return_value = [
                np.full((300, 200, 3), 200, dtype=np.uint8)
            ]
            MockPipeline.return_value = mock_pipeline_inst
            proc.run(img_dir, out_pdf)

    def test_run_progress_callback(self, tmp_path):
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=1)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="none", split=False)
        proc = BookProcessor(cfg)
        calls = []

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming"):
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.run.return_value = [
                np.full((300, 200, 3), 200, dtype=np.uint8)
            ]
            MockPipeline.return_value = mock_pipeline_inst
            proc.run(img_dir, out_pdf, progress_cb=lambda p, m: calls.append(p))
        assert len(calls) >= 1

    def test_run_load_error_continues(self, tmp_path):
        """fix_exif_rotation が None を返しても続行する。"""
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=2)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="none", split=False)
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming") as mock_pdf, \
             patch("processor.fix_exif_rotation", return_value=None):
            MockPipeline.return_value = MagicMock()
            with pytest.raises(RuntimeError, match="No pages"):
                proc.run(img_dir, out_pdf)

    def test_run_pipeline_error_continues(self, tmp_path):
        """pipeline.run() が例外を送出しても続行し、全失敗なら RuntimeError。"""
        from processor import BookProcessor
        img_dir = tmp_path / "pipeline_input"
        img_dir.mkdir()
        dummy_img = np.full((300, 200, 3), 200, dtype=np.uint8)
        for i in range(2):
            cv2.imwrite(str(img_dir / f"img{i:02d}.jpg"), dummy_img)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="none", split=False)
        proc = BookProcessor(cfg)

        dummy_image = np.zeros((10, 10, 3), dtype=np.uint8)
        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming"), \
             patch("processor.fix_exif_rotation", return_value=dummy_image):
            mock_inst = MagicMock()
            mock_inst.run.side_effect = RuntimeError("pipeline error")
            MockPipeline.return_value = mock_inst
            with pytest.raises(RuntimeError, match="No pages"):
                proc.run(img_dir, out_pdf)


        """dewarpnet モードでは spread_dewarper が作られる。"""
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=1)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="dewarpnet", split=False)
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming"), \
             patch("processor.Dewarper") as MockDewarper:
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.run.return_value = [
                np.full((300, 200, 3), 200, dtype=np.uint8)
            ]
            MockPipeline.return_value = mock_pipeline_inst
            proc.run(img_dir, out_pdf)
            MockDewarper.assert_called()

    def test_run_imwrite_failure_raises(self, tmp_path):
        """cv2.imwrite が失敗した場合は IOError が発生する（lines 126-127）。"""
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=1)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="none", split=False)
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.cv2.imwrite", return_value=False):
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.run.return_value = [
                np.full((300, 200, 3), 200, dtype=np.uint8)
            ]
            MockPipeline.return_value = mock_pipeline_inst
            with pytest.raises(IOError, match="Cannot write image"):
                proc.run(img_dir, out_pdf)

    def test_vertical_writing_mode_disables_all_dewarp(self, tmp_path):
        """writing_mode='vertical' のとき spread_dewarper も page_dewarp_mode も無効化される。
        縦書き書籍への polynomial 補正は横書き要素の誤検出・列長差の誤検出で
        文字を消すため、spread/page 両方を無効化する。"""
        from processor import BookProcessor
        img_dir = self._make_input_dir(tmp_path, n_images=1)
        out_pdf = tmp_path / "out.pdf"
        cfg = ProcessingConfig(dewarp_mode="dewarpnet", writing_mode="vertical", split=False)
        proc = BookProcessor(cfg)

        with patch("processor.Pipeline") as MockPipeline, \
             patch("processor.build_pdf_streaming"), \
             patch("processor.Dewarper") as MockDewarper, \
             patch("processor.DewarpStep") as MockDewarpStep:
            mock_pipeline_inst = MagicMock()
            mock_pipeline_inst.run.return_value = [
                np.full((300, 200, 3), 200, dtype=np.uint8)
            ]
            MockPipeline.return_value = mock_pipeline_inst
            proc.run(img_dir, out_pdf)
            # spread_dewarper は生成されない
            MockDewarper.assert_not_called()
            # page_dewarp_mode="none" で DewarpStep が呼ばれる
            args, kwargs = MockDewarpStep.call_args
            assert kwargs.get("mode", args[1] if len(args) > 1 else None) == "none"

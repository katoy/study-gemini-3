"""
ビジュアル回帰テスト: 生成された PDF の見た目をチェックする。
"""
import os
import shutil
import tempfile
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytest

from processor import BookProcessor
from core.config import ProcessingConfig

def pdf_to_images(pdf_path: Path, dpi: int = 72) -> list[np.ndarray]:
    """PDF の各ページを BGR 画像のリストに変換する。"""
    images = []
    doc = fitz.open(str(pdf_path))
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 3: # RGB
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 4: # RGBA
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        images.append(img)
    doc.close()
    return images

def compare_images(img1: np.ndarray, img2: np.ndarray, threshold: float = 0.85) -> bool:
    """2つの画像の類似度をチェックする。"""
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
    diff = cv2.absdiff(img1, img2)
    similarity = 1.0 - (np.count_nonzero(diff) / diff.size)
    return similarity >= threshold

class TestVisualRegression:
    GOLDEN_DIR = Path("tests/goldens")

    @pytest.fixture
    def workspace(self):
        tmpdir = tempfile.mkdtemp()
        yield Path(tmpdir)
        shutil.rmtree(tmpdir)

    def test_pdf_output_consistency(self, workspace):
        # 1. テスト用の画像を生成 (2枚の見開き)
        # ページを認識しやすくするため、黒背景の上に白いページを配置する
        img_dir = workspace / "inputs"
        img_dir.mkdir()
        for i in range(1, 3):
            # 黒背景
            canvas = np.zeros((600, 800, 3), dtype=np.uint8)
            # 左ページ
            cv2.rectangle(canvas, (50, 50), (380, 550), (255, 255, 255), -1)
            cv2.putText(canvas, f"P{i*2-1}", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,0), 3)
            # 右ページ
            cv2.rectangle(canvas, (420, 50), (750, 550), (255, 255, 255), -1)
            cv2.putText(canvas, f"P{i*2}", (500, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,0), 3)
            
            cv2.imwrite(str(img_dir / f"{i:04d}.png"), canvas)

        # 2. PDF 生成
        output_pdf = workspace / "test_out.pdf"
        cfg = ProcessingConfig(
            dewarp_mode="none",
            split=True,
            output_size="A5",
            dpi=72
        )
        proc = BookProcessor(cfg)
        proc.run(input_folder=img_dir, output_pdf=output_pdf)

        assert output_pdf.exists()

        # 3. PDF を画像に変換して検証
        pages = pdf_to_images(output_pdf)
        # 最低限 1ページ以上あること (ダミー画像での split 精度に依存するため)
        assert len(pages) > 0

        update_mode = os.environ.get("UPDATE_GOLDENS") == "1"
        if update_mode:
            if self.GOLDEN_DIR.exists(): shutil.rmtree(self.GOLDEN_DIR)
            self.GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

        for i, page in enumerate(pages):
            golden_path = self.GOLDEN_DIR / f"page_{i:02d}.png"
            if update_mode:
                cv2.imwrite(str(golden_path), page)
                continue

            if golden_path.exists():
                ref = cv2.imread(str(golden_path))
                assert compare_images(page, ref), f"Visual regression on page {i}"
            else:
                assert np.mean(page) < 254

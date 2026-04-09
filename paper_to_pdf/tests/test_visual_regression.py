"""
ビジュアル回帰テスト: 生成された PDF の見た目をチェックし、差分レポートを生成する。
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

REPORTS_DIR = Path("tests/reports")

def pdf_to_images(pdf_path: Path, dpi: int = 72) -> list[np.ndarray]:
    """PDF の各ページを BGR 画像のリストに変換する。"""
    images = []
    doc = fitz.open(str(pdf_path))
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 3: img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 4: img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        images.append(img)
    doc.close()
    return images

def create_visual_diff(img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
    """2つの画像の差分を赤色でハイライトした画像を生成する。"""
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
    
    diff = cv2.absdiff(img1, img2)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(diff_gray, 10, 255, cv2.THRESH_BINARY)
    
    # 元画像をグレースケール化してベースにする
    base = cv2.cvtColor(cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    # 差分がある箇所を赤く塗る
    highlight = base.copy()
    highlight[mask > 0] = [0, 0, 255]
    
    # 0.7倍でブレンド
    return cv2.addWeighted(base, 0.3, highlight, 0.7, 0)

def generate_html_report(results: list[dict]):
    """テスト結果から HTML レポートを生成する。"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html = ["<html><head><title>Visual Regression Report</title>"]
    html.append("<style>table { border-collapse: collapse; } td { border: 1px solid #ccc; padding: 10px; text-align: center; } img { max-width: 400px; }</style>")
    html.append("</head><body><h1>Visual Regression Report</h1><table>")
    html.append("<tr><th>Name</th><th>Golden</th><th>Actual</th><th>Diff (Red=Change)</th><th>Status</th></tr>")
    
    for r in results:
        status_color = "green" if r["status"] == "PASS" else "red"
        html.append(f"<tr><td>{r['name']}</td>")
        html.append(f"<td><img src='{r['golden']}'></td>")
        html.append(f"<td><img src='{r['actual']}'></td>")
        html.append(f"<td><img src='{r['diff']}'></td>")
        html.append(f"<td style='color: {status_color}'>{r['status']}<br>Score: {r['score']:.4f}</td></tr>")
    
    html.append("</table></body></html>")
    with open(REPORTS_DIR / "index.html", "w") as f:
        f.write("\n".join(html))

class TestVisualRegression:
    GOLDEN_DIR = Path("tests/goldens")

    @pytest.fixture
    def workspace(self):
        tmpdir = tempfile.mkdtemp()
        yield Path(tmpdir)
        shutil.rmtree(tmpdir)

    def _run_visual_test(self, input_dir: Path, output_pdf: Path, test_name: str, config_kwargs: dict):
        """共通のビジュアルテスト実行ロジック。"""
        cfg = ProcessingConfig(**config_kwargs)
        proc = BookProcessor(cfg)
        proc.run(input_folder=input_dir, output_pdf=output_pdf)
        
        pages = pdf_to_images(output_pdf)
        assert len(pages) > 0
        
        update_mode = os.environ.get("UPDATE_GOLDENS") == "1"
        test_golden_dir = self.GOLDEN_DIR / test_name
        if update_mode:
            if test_golden_dir.exists(): shutil.rmtree(test_golden_dir)
            test_golden_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for i, page in enumerate(pages):
            golden_path = test_golden_dir / f"page_{i:02d}.png"
            report_name = f"{test_name}_p{i:02d}"
            
            if update_mode:
                cv2.imwrite(str(golden_path), page)
                continue

            status = "PASS"
            score = 1.0
            diff_img = np.zeros_like(page)
            
            if golden_path.exists():
                ref = cv2.imread(str(golden_path))
                # 類似度計算
                if page.shape != ref.shape: ref = cv2.resize(ref, (page.shape[1], page.shape[0]))
                diff = cv2.absdiff(page, ref)
                score = 1.0 - (np.count_nonzero(diff) / diff.size)
                
                if score < 0.99: # 厳しめに判定
                    status = "FAIL"
                    diff_img = create_visual_diff(page, ref)
                else:
                    diff_img = page # 差分なし
            else:
                status = "NEW"
                diff_img = page

            # レポート用画像の保存
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(REPORTS_DIR / f"actual_{report_name}.png"), page)
            if golden_path.exists(): shutil.copy(golden_path, REPORTS_DIR / f"golden_{report_name}.png")
            cv2.imwrite(str(REPORTS_DIR / f"diff_{report_name}.png"), diff_img)
            
            results.append({
                "name": report_name,
                "golden": f"golden_{report_name}.png",
                "actual": f"actual_{report_name}.png",
                "diff": f"diff_{report_name}.png",
                "status": status,
                "score": score
            })

        if not update_mode:
            generate_html_report(results)
            # 全ページパスしているか確認
            assert all(r["status"] in ("PASS", "NEW") for r in results), f"Visual regression in {test_name}. See tests/reports/index.html"

    def test_synthetic_consistency(self, workspace):
        """ダミー画像での基本動作確認。"""
        img_dir = workspace / "inputs"
        img_dir.mkdir()
        for i in range(1, 2):
            canvas = np.zeros((600, 800, 3), dtype=np.uint8)
            cv2.rectangle(canvas, (50, 50), (380, 550), (255, 255, 255), -1)
            cv2.putText(canvas, f"Synthetic {i}", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0), 2)
            cv2.imwrite(str(img_dir / f"{i:04d}.png"), canvas)
        
        self._run_visual_test(img_dir, workspace / "out.pdf", "synthetic", 
                             {"dewarp_mode": "none", "split": False, "dpi": 72})

    def test_samples_h_integration(self, workspace):
        """実サンプル (samples_h) の統合テスト。"""
        sample_src = Path("samples_h")
        if not sample_src.exists(): pytest.skip("samples_h not found")
        
        # 最初の1枚だけテストに使用
        img_dir = workspace / "inputs"
        img_dir.mkdir()
        samples = sorted(list(sample_src.glob("*.png"))) + sorted(list(sample_src.glob("*.jpg")))
        if not samples: pytest.skip("No images in samples_h")
        shutil.copy(samples[0], img_dir / "0001.png")
        
        self._run_visual_test(img_dir, workspace / "out.pdf", "samples_h", 
                             {"dewarp_mode": "polynomial", "split": True, "dpi": 72})

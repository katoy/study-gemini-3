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
        if pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
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
    base = cv2.cvtColor(cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    highlight = base.copy()
    highlight[mask > 0] = [0, 0, 255]
    return cv2.addWeighted(base, 0.3, highlight, 0.7, 0)

def generate_html_report(results: list[dict]):
    """テスト結果から HTML レポートを生成する。"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html = ["<html><head><title>Visual Regression Report</title>"]
    html.append("<style>table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #ccc; padding: 8px; text-align: center; } img { max-width: 300px; height: auto; }</style>")
    html.append("</head><body><h1>Visual Regression Report</h1>")
    
    # テスト名ごとにグループ化して表示
    current_test = ""
    for r in results:
        test_base = r["name"].split("_p")[0]
        if test_base != current_test:
            if current_test != "":
                html.append("</table>")
            html.append(f"<h2>Test: {test_base}</h2><table>")
            html.append("<tr><th>Page</th><th>Golden</th><th>Actual</th><th>Diff</th><th>Status</th></tr>")
            current_test = test_base
        
        status_color = "green" if r["status"] == "PASS" else "red"
        html.append(f"<tr><td>{r['name']}</td>")
        html.append(f"<td><img src='{r['golden']}'></td>")
        html.append(f"<td><img src='{r['actual']}'></td>")
        html.append(f"<td><img src='{r['diff']}'></td>")
        html.append(f"<td style='color: {status_color}'>{r['status']}<br>Score: {r['score']:.4f}</td></tr>")
    
    html.append("</table></body></html>")
    with open(REPORTS_DIR / "index.html", "w") as f:
        f.write("\n".join(html))

# 全テストを通した結果を保持するためのグローバルリスト (pytest 実行単位)
_all_results = []

class TestVisualRegression:
    GOLDEN_DIR = Path("tests/goldens")

    @pytest.fixture
    def workspace(self):
        tmpdir = tempfile.mkdtemp()
        yield Path(tmpdir)
        shutil.rmtree(tmpdir)

    def _run_visual_test(self, input_dir: Path, output_pdf: Path, test_name: str, config_kwargs: dict):
        cfg = ProcessingConfig(**config_kwargs)
        proc = BookProcessor(cfg)
        proc.run(input_folder=input_dir, output_pdf=output_pdf)
        
        pages = pdf_to_images(output_pdf)
        assert len(pages) > 0
        
        update_mode = os.environ.get("UPDATE_GOLDENS") == "1"
        test_golden_dir = self.GOLDEN_DIR / test_name
        if update_mode:
            if test_golden_dir.exists():
                shutil.rmtree(test_golden_dir)
            test_golden_dir.mkdir(parents=True, exist_ok=True)

        local_results = []
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
            if page.shape != ref.shape:
                ref = cv2.resize(ref, (page.shape[1], page.shape[0]))
                diff = cv2.absdiff(page, ref)
                score = 1.0 - (np.count_nonzero(diff) / diff.size)
                if score < 0.99:
                    status = "FAIL"
                    diff_img = create_visual_diff(page, ref)
                else:
                    diff_img = page
            else:
                status = "NEW"
                diff_img = page

            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(REPORTS_DIR / f"actual_{report_name}.png"), page)
            if golden_path.exists():
                shutil.copy(golden_path, REPORTS_DIR / f"golden_{report_name}.png")
            else: # ダミーの空画像を作成
                cv2.imwrite(str(REPORTS_DIR / f"golden_{report_name}.png"), np.full_like(page, 240))
            cv2.imwrite(str(REPORTS_DIR / f"diff_{report_name}.png"), diff_img)
            
            res = {
                "name": report_name, "golden": f"golden_{report_name}.png",
                "actual": f"actual_{report_name}.png", "diff": f"diff_{report_name}.png",
                "status": status, "score": score
            }
            local_results.append(res)
            _all_results.append(res)

        if not update_mode:
            generate_html_report(_all_results)
            assert all(r["status"] in ("PASS", "NEW") for r in local_results)

    def test_synthetic_consistency(self, workspace):
        img_dir = workspace / "inputs"
        img_dir.mkdir()
        canvas = np.zeros((600, 800, 3), dtype=np.uint8)
        cv2.rectangle(canvas, (50, 50), (380, 550), (255, 255, 255), -1)
        cv2.putText(canvas, "Synthetic", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0), 2)
        cv2.imwrite(str(img_dir / "0001.png"), canvas)
        self._run_visual_test(img_dir, workspace / "out.pdf", "synthetic", 
                             {"dewarp_mode": "none", "split": False, "dpi": 72})

    def test_samples_h_dewarpnet(self, workspace):
        sample_src = Path("samples_h")
        if not sample_src.exists():
            pytest.skip("samples_h not found")
        img_dir = workspace / "inputs"
        img_dir.mkdir()
        for f in sorted(list(sample_src.glob("*.png")) + list(sample_src.glob("*.jpg"))):
            shutil.copy(f, img_dir / f.name)
        self._run_visual_test(img_dir, workspace / "out.pdf", "samples_h_dewarpnet",
                             {"dewarp_mode": "dewarpnet", "split": True, "dpi": 72,
                              "rotate_angle": 180, "writing_mode": "horizontal"})

    def test_samples_h_polynomial(self, workspace):
        sample_src = Path("samples_h")
        if not sample_src.exists():
            pytest.skip("samples_h not found")
        img_dir = workspace / "inputs"
        img_dir.mkdir()
        for f in sorted(list(sample_src.glob("*.png")) + list(sample_src.glob("*.jpg"))):
            shutil.copy(f, img_dir / f.name)
        self._run_visual_test(img_dir, workspace / "out.pdf", "samples_h_polynomial",
                             {"dewarp_mode": "polynomial", "split": True, "dpi": 72,
                              "rotate_angle": 180, "writing_mode": "horizontal"})

    def test_samples_v_integration(self, workspace):
        sample_src = Path("samples_v")
        if not sample_src.exists():
            pytest.skip("samples_v not found")
        img_dir = workspace / "inputs"
        img_dir.mkdir()
        # すべての画像をコピー
        for f in sorted(list(sample_src.glob("*.png")) + list(sample_src.glob("*.jpg"))):
            shutil.copy(f, img_dir / f.name)
        self._run_visual_test(img_dir, workspace / "out.pdf", "samples_v", 
                             {"dewarp_mode": "none", "split": True, "dpi": 72, 
                              "rotate_angle": 180, "writing_mode": "vertical"})

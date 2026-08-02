import os
import sys
import subprocess
import shutil
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter

def ensure_ocrmypdf_installed() -> bool:
    """ocrmypdfが利用可能であることを確認。"""
    return bool(shutil.which("ocrmypdf"))

def ensure_tesseract_installed() -> bool:
    """tesseractが利用可能か確認。"""
    return bool(shutil.which("tesseract"))

def run_ocr(input_pdf: Path, output_pdf: Path, lang: str = "jpn+eng", force: bool = False, step_label: str = "") -> bool:
    """ocrmypdf でOCR実行。既存ファイルがあれば (force=False) スキップ。"""
    if output_pdf.exists() and not force:
        prefix = f"{step_label} " if step_label else ""
        print(f"{prefix}OCR済みPDF既存: {output_pdf}", file=sys.stderr)
        return True

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{step_label} " if step_label else ""
    print(f"{prefix}ocrmypdf実行中 ({input_pdf.stat().st_size / (1024**2):.1f}MB)...", file=sys.stderr)
    try:
        subprocess.run(
            [
                "ocrmypdf",
                "--skip-text",
                "-l", lang,
                str(input_pdf),
                str(output_pdf),
            ],
            check=True,
            capture_output=True,
            timeout=1800,  # 30分タイムアウト
        )
        print(f"OCR完了: {output_pdf}", file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running ocrmypdf: {e.stderr.decode()}", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("ocrmypdf timeout (>30min)", file=sys.stderr)
        return False

def get_file_size_mb(file_path: str | Path) -> float:
    """ファイルサイズを MB で取得"""
    return os.path.getsize(file_path) / (1024 * 1024)

def get_page_count(pdf_path: str | Path) -> int:
    """PDF のページ数を取得"""
    try:
        reader = PdfReader(pdf_path)
        return len(reader.pages)
    except Exception as e:
        print(f"エラー: {pdf_path} のページ数を取得できません: {e}", file=sys.stderr)
        return 0

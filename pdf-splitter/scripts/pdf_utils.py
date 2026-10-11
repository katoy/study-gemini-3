import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader

OCR_ENGINES = ("ndlocr", "tesseract")
DEFAULT_OCR_ENGINE = "ndlocr"
NDLOCR_DIR_ENV = "NDLOCR_LITE_DIR"
NDLOCR_PYTHON = "3.12"
OCR_TIMEOUT_SEC = 1800  # 30分タイムアウト


def ensure_ocrmypdf_installed() -> bool:
    """ocrmypdfが利用可能であることを確認。"""
    return bool(shutil.which("ocrmypdf"))


def get_ndlocr_dir() -> Path | None:
    """環境変数 NDLOCR_LITE_DIR で指定された ndlocr-lite の clone 先を返す。未設定なら None。"""
    value = os.environ.get(NDLOCR_DIR_ENV)
    return Path(value).expanduser() if value else None


def ensure_ocr_engine_available(engine: str) -> bool:
    """指定した OCR エンジン (ndlocr / tesseract) が利用可能であることを確認。"""
    if engine == "tesseract":
        return ensure_ocrmypdf_installed()
    ndlocr_dir = get_ndlocr_dir()
    return bool(shutil.which("uv")) and ndlocr_dir is not None and (ndlocr_dir / "src" / "ocr.py").is_file()


def build_ocr_command(engine: str, input_pdf: Path, output_pdf: Path, lang: str, work_dir: Path) -> list[str]:
    """OCR エンジンごとの実行コマンドを組み立てる。work_dir は NDLOCR-Lite のページ別出力先。"""
    if engine == "tesseract":
        return ["ocrmypdf", "--skip-text", "-l", lang, str(input_pdf), str(output_pdf)]
    ndlocr_dir = get_ndlocr_dir()
    if ndlocr_dir is None:
        raise ValueError(f"環境変数 {NDLOCR_DIR_ENV} が設定されていません")
    # NDLOCR-Lite は依存を requirements.txt で固定しているため、uv の一時環境で実行する
    return [
        "uv", "run", "-q", "--no-project", "--python", NDLOCR_PYTHON,
        "--with-requirements", str(ndlocr_dir / "requirements.txt"),
        "python", str(ndlocr_dir / "src" / "ocr.py"),
        "--sourcepdf", str(input_pdf),
        "--pdf-output", str(output_pdf),
        "--output", str(work_dir),
        "--json-only",
    ]


def run_ocr(
    input_pdf: Path,
    output_pdf: Path,
    lang: str = "jpn+eng",
    force: bool = False,
    step_label: str = "",
    engine: str = DEFAULT_OCR_ENGINE,
) -> bool:
    """OCR を実行して検索可能 PDF を作る。既存ファイルがあれば (force=False) スキップ。

    Args:
        input_pdf: 入力 PDF。
        output_pdf: 文字層付きの出力 PDF。
        lang: ocrmypdf の言語指定 (engine="tesseract" のときだけ使う)。
        force: 既存の出力を無視して再実行するか。
        step_label: 進捗表示の接頭辞。
        engine: "ndlocr" (NDLOCR-Lite) または "tesseract" (ocrmypdf)。

    Returns:
        成功したら True。
    """
    if output_pdf.exists() and not force:
        prefix = f"{step_label} " if step_label else ""
        print(f"{prefix}OCR済みPDF既存: {output_pdf}", file=sys.stderr)
        return True

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{step_label} " if step_label else ""
    print(f"{prefix}{engine} でOCR実行中 ({input_pdf.stat().st_size / (1024**2):.1f}MB)...", file=sys.stderr)
    try:
        with tempfile.TemporaryDirectory() as work_dir:
            subprocess.run(
                build_ocr_command(engine, input_pdf.resolve(), output_pdf.resolve(), lang, Path(work_dir)),
                check=True,
                capture_output=True,
                timeout=OCR_TIMEOUT_SEC,
            )
        if not output_pdf.exists():
            print(f"Error: {engine} が出力PDFを作成しませんでした: {output_pdf}", file=sys.stderr)
            return False
        print(f"OCR完了: {output_pdf}", file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running {engine}: {e.stderr.decode()}", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"{engine} timeout (>{OCR_TIMEOUT_SEC // 60}min)", file=sys.stderr)
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

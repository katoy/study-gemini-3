"""
ocr.py (NDLOCR-Lite), ocrmypdf (Tesseract), および pdf_chapter_pipeline.py のテスト。
縦書き日本語および横書き日本語のサンプル画像/PDFを用いて、OCR認識および章分割の挙動を検証します。
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont
import img2pdf  # type: ignore[import-untyped]
from pypdf import PdfReader
import pytest

# ../pdf-splitter/scripts から安全にモジュールをインポート（sys.path を恒久的に汚染しない）
_PDF_SPLITTER_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "pdf-splitter" / "scripts"
pdf_utils: Any = None
pdf_chapter_pipeline: Any = None

if _PDF_SPLITTER_SCRIPTS.exists():
    _scripts_str = str(_PDF_SPLITTER_SCRIPTS)
    _inserted = False
    if _scripts_str not in sys.path:
        sys.path.insert(0, _scripts_str)
        _inserted = True
    try:
        import importlib

        pdf_utils = importlib.import_module("pdf_utils")
        pdf_chapter_pipeline = importlib.import_module("pdf_chapter_pipeline")
    except ImportError:
        pdf_utils = None
        pdf_chapter_pipeline = None
    finally:
        if _inserted and _scripts_str in sys.path:
            sys.path.remove(_scripts_str)


# ---------------------------------------------------------------------------
# 環境・ツール検出ヘルパー
# ---------------------------------------------------------------------------


def _get_japanese_font(size: int = 36) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """利用可能な日本語フォントを取得します。"""
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "C:\\Windows\\Fonts\\msgothic.ttc",
        "C:\\Windows\\Fonts\\meiryo.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _find_ocrmypdf_executable() -> Optional[str]:
    """PATH または一般的なインストール先から ocrmypdf の実行パスを探します。"""
    found = shutil.which("ocrmypdf")
    if found:
        # asdf shim の場合、バージョン未指定で失敗することがあるため実体を探索
        res = subprocess.run([found, "--version"], capture_output=True, text=True)
        if res.returncode == 0:
            return found
    candidates = [
        "/opt/homebrew/bin/ocrmypdf",
        "/usr/local/bin/ocrmypdf",
    ]
    for c in candidates:
        if Path(c).is_file():
            res = subprocess.run([c, "--version"], capture_output=True, text=True)
            if res.returncode == 0:
                return c
    return None


def _is_ndlocr_available() -> bool:
    """NDLOCR-Lite が利用可能か確認します。"""
    ndl_dir_env = os.environ.get("NDLOCR_LITE_DIR", str(Path.home() / "tools" / "ndlocr-lite"))
    ndl_dir = Path(ndl_dir_env).expanduser()
    ocr_py = ndl_dir / "src" / "ocr.py"
    req_txt = ndl_dir / "requirements.txt"
    has_uv = bool(shutil.which("uv"))
    return has_uv and ocr_py.is_file() and req_txt.is_file()


def _get_ndlocr_dir() -> Path:
    """NDLOCR-Lite のルートディレクトリを返します。"""
    ndl_dir_env = os.environ.get("NDLOCR_LITE_DIR", str(Path.home() / "tools" / "ndlocr-lite"))
    return Path(ndl_dir_env).expanduser()


# ---------------------------------------------------------------------------
# 画像および PDF 生成ヘルパー
# ---------------------------------------------------------------------------


def create_horizontal_japanese_page(
    title: str,
    body_lines: list[str],
    width: int = 800,
    height: int = 600,
) -> Image.Image:
    """横書き日本語の書籍ページ画像を生成します。"""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_japanese_font(32)

    # 枠線
    draw.rectangle([20, 20, width - 20, height - 20], outline=(200, 200, 200), width=2)

    # 見出し
    y = 50
    draw.text((60, y), title, font=font, fill=(0, 0, 0))
    y += 60

    # 本文
    for line in body_lines:
        draw.text((60, y), line, font=font, fill=(50, 50, 50))
        y += 48

    return img


def create_vertical_japanese_page(
    title: str,
    body_columns: list[str],
    width: int = 600,
    height: int = 800,
) -> Image.Image:
    """縦書き日本語の書籍ページ画像を生成します（右から左へ列を配置、上から下へ文字を配置）。"""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = _get_japanese_font(32)

    # 枠線
    draw.rectangle([20, 20, width - 20, height - 20], outline=(200, 200, 200), width=2)

    # 列を右から左へ並べる
    x = width - 80
    all_columns = [title] + body_columns

    for col in all_columns:
        y = 60
        for ch in col:
            draw.text((x, y), ch, font=font, fill=(0, 0, 0))
            y += 40
        x -= 55

    return img


def save_pages_to_pdf(pages: list[Image.Image], pdf_path: Path) -> Path:
    """画像を一時 PNG に保存し、img2pdf で結合した PDF を作成します。"""
    temp_dir = pdf_path.parent / f"_tmp_{pdf_path.stem}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    img_paths: list[str] = []

    try:
        for idx, page in enumerate(pages):
            p = temp_dir / f"page_{idx:03d}.png"
            page.save(str(p))
            img_paths.append(str(p))

        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(img_paths))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return pdf_path


# ---------------------------------------------------------------------------
# 1. ocr.py (NDLOCR-Lite) のテスト
# ---------------------------------------------------------------------------


class TestNDLOCR:
    """NDLOCR-Lite (src/ocr.py) の日本語 OCR テスト。"""

    @pytest.mark.skipif(
        not _is_ndlocr_available(), reason="NDLOCR-Lite または uv が環境に存在しません"
    )
    def test_ndlocr_horizontal_japanese(self, tmp_path: Path) -> None:
        """横書き日本語 PDF に対して ocr.py を実行し、文字層が正しく埋め込まれることを検証。"""
        # 1. 横書き日本語画像の生成
        page_img = create_horizontal_japanese_page(
            title="第1章 はじめに",
            body_lines=[
                "これは横書き日本語のテスト文章です。",
                "自然言語処理と光学文字認識の検証を行います。",
            ],
        )
        input_pdf = tmp_path / "horizontal_in.pdf"
        save_pages_to_pdf([page_img], input_pdf)

        output_pdf = tmp_path / "horizontal_out.pdf"
        work_dir = tmp_path / "ndl_work_h"
        work_dir.mkdir(parents=True, exist_ok=True)

        ndl_dir = _get_ndlocr_dir()

        # 2. ocr.py を実行
        cmd = [
            "uv",
            "run",
            "-q",
            "--no-project",
            "--python",
            "3.12",
            "--with-requirements",
            str(ndl_dir / "requirements.txt"),
            "python",
            str(ndl_dir / "src" / "ocr.py"),
            "--sourcepdf",
            str(input_pdf),
            "--pdf-output",
            str(output_pdf),
            "--output",
            str(work_dir),
            "--json-only",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, f"ocr.py 実行失敗: {result.stderr}"
        assert output_pdf.exists(), "出力 PDF が作成されていること"

        # 3. 生成された PDF からテキスト抽出を検証
        reader = PdfReader(str(output_pdf))
        assert len(reader.pages) == 1
        extracted = reader.pages[0].extract_text() or ""

        # 期待キーワードの確認
        assert "第1章" in extracted
        assert "はじめに" in extracted
        assert "横書き日本語" in extracted

    @pytest.mark.skipif(
        not _is_ndlocr_available(), reason="NDLOCR-Lite または uv が環境に存在しません"
    )
    def test_ndlocr_vertical_japanese(self, tmp_path: Path) -> None:
        """縦書き日本語 PDF に対して ocr.py を実行し、縦書き順でテキスト層が埋め込まれることを検証。"""
        # 1. 縦書き日本語画像の生成（右列から左列、上から下）
        page_img = create_vertical_japanese_page(
            title="第1章 走れメロス",
            body_columns=[
                "メロスは激怒した。",
                "必ずかの邪悪な王を除かねばならぬと決意した。",
            ],
        )
        input_pdf = tmp_path / "vertical_in.pdf"
        save_pages_to_pdf([page_img], input_pdf)

        output_pdf = tmp_path / "vertical_out.pdf"
        work_dir = tmp_path / "ndl_work_v"
        work_dir.mkdir(parents=True, exist_ok=True)

        ndl_dir = _get_ndlocr_dir()

        # 2. ocr.py を実行
        cmd = [
            "uv",
            "run",
            "-q",
            "--no-project",
            "--python",
            "3.12",
            "--with-requirements",
            str(ndl_dir / "requirements.txt"),
            "python",
            str(ndl_dir / "src" / "ocr.py"),
            "--sourcepdf",
            str(input_pdf),
            "--pdf-output",
            str(output_pdf),
            "--output",
            str(work_dir),
            "--json-only",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, f"ocr.py 実行失敗: {result.stderr}"
        assert output_pdf.exists(), "出力 PDF が作成されていること"

        # 3. 生成された PDF からテキスト抽出を検証
        reader = PdfReader(str(output_pdf))
        assert len(reader.pages) == 1
        extracted = reader.pages[0].extract_text() or ""

        # 期待キーワードの確認
        assert "第1章" in extracted
        assert "メロス" in extracted
        assert "激怒" in extracted


# ---------------------------------------------------------------------------
# 2. ocrmypdf (Tesseract) のテスト
# ---------------------------------------------------------------------------


class TestOCRMyPDF:
    """ocrmypdf による日本語 OCR テスト。"""

    @pytest.mark.skipif(
        _find_ocrmypdf_executable() is None, reason="ocrmypdf がインストールされていません"
    )
    def test_ocrmypdf_horizontal_japanese(self, tmp_path: Path) -> None:
        """横書き日本語 PDF に対して ocrmypdf を実行し、検索可能テキスト層が付与されることを検証。"""
        page_img = create_horizontal_japanese_page(
            title="第1章 はじめに",
            body_lines=["横書き日本語のテキスト認識テストです。"],
        )
        input_pdf = tmp_path / "ocrmypdf_h_in.pdf"
        save_pages_to_pdf([page_img], input_pdf)

        output_pdf = tmp_path / "ocrmypdf_h_out.pdf"
        executable = _find_ocrmypdf_executable()
        assert executable is not None

        env = os.environ.copy()
        env["PATH"] = f"/opt/homebrew/bin:{env.get('PATH', '')}"

        cmd = [executable, "-l", "jpn+eng", "--skip-text", str(input_pdf), str(output_pdf)]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
        assert result.returncode == 0, f"ocrmypdf 実行失敗: {result.stderr}"
        assert output_pdf.exists()

        reader = PdfReader(str(output_pdf))
        extracted = reader.pages[0].extract_text() or ""
        # 空白やヌル文字 (\x00) が混入する場合があるため除去して確認
        cleaned = extracted.replace(" ", "").replace("\n", "").replace("\x00", "")
        assert "第1章" in cleaned or "はじめに" in cleaned

    @pytest.mark.skipif(
        _find_ocrmypdf_executable() is None, reason="ocrmypdf がインストールされていません"
    )
    def test_ocrmypdf_vertical_japanese(self, tmp_path: Path) -> None:
        """縦書き日本語 PDF に対して ocrmypdf -l jpn_vert を実行し、PDF が生成されることを検証。"""
        page_img = create_vertical_japanese_page(
            title="第1章 メロス",
            body_columns=["走れメロス。"],
        )
        input_pdf = tmp_path / "ocrmypdf_v_in.pdf"
        save_pages_to_pdf([page_img], input_pdf)

        output_pdf = tmp_path / "ocrmypdf_v_out.pdf"
        executable = _find_ocrmypdf_executable()
        assert executable is not None

        env = os.environ.copy()
        env["PATH"] = f"/opt/homebrew/bin:{env.get('PATH', '')}"

        cmd = [executable, "-l", "jpn_vert", "--skip-text", str(input_pdf), str(output_pdf)]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
        assert result.returncode == 0, f"ocrmypdf 実行失敗: {result.stderr}"
        assert output_pdf.exists()

        reader = PdfReader(str(output_pdf))
        assert len(reader.pages) == 1


# ---------------------------------------------------------------------------
# 3. pdf_chapter_pipeline.py のテスト
# ---------------------------------------------------------------------------


class TestPdfChapterPipeline:
    """pdf_chapter_pipeline による横書き・縦書き日本語書籍の章解析および分割テスト。"""

    @pytest.mark.skipif(
        pdf_chapter_pipeline is None, reason="pdf_chapter_pipeline が見つかりません"
    )
    def test_pipeline_horizontal_japanese_chapters(self, tmp_path: Path) -> None:
        """横書き日本語書籍（複数章）の目次解析または章キーワード検出および分割を検証。"""
        # 1. 3ページの横書き書籍を作成（P1: 表紙, P2: 第1章, P3: 第2章）
        p1 = create_horizontal_japanese_page("書籍タイトル", ["著者: テスト太郎"])
        p2 = create_horizontal_japanese_page("第1章 Python入門", ["Pythonの基礎文法を解説します。"])
        p3 = create_horizontal_japanese_page("第2章 応用処理", ["PDF処理とOCR技術を学びます。"])

        book_pdf = tmp_path / "book_horizontal.pdf"
        save_pages_to_pdf([p1, p2, p3], book_pdf)

        # 2. OCR で検索可能 PDF を準備
        ocr_pdf = tmp_path / "book_horizontal_ocr.pdf"
        if not (_is_ndlocr_available() and pdf_utils is not None):
            pytest.skip("NDLOCR-Lite が利用できないためスキップします")

        success = pdf_utils.run_ocr(book_pdf, ocr_pdf, engine="ndlocr")
        assert success is True

        # 3. pdf_chapter_pipeline の章検出を実行
        reader = PdfReader(str(ocr_pdf))
        detected_chapters = pdf_chapter_pipeline.detect_chapters_by_keywords(reader)

        # 第1章（物理ページ 2）と第2章（物理ページ 3）が検出されること
        assert len(detected_chapters) >= 2
        pages = [c.physical_page for c in detected_chapters]
        assert 2 in pages
        assert 3 in pages

        # 4. 章分割を実行
        out_dir = tmp_path / "split_output_h"
        split_results = pdf_chapter_pipeline.split_by_boundaries(reader, detected_chapters, out_dir)

        # 分割ファイルが生成されていることを検証
        assert len(split_results) >= 2
        for item in split_results:
            p = Path(item["path"])
            assert p.exists()
            assert p.stat().st_size > 0

    @pytest.mark.skipif(
        pdf_chapter_pipeline is None, reason="pdf_chapter_pipeline が見つかりません"
    )
    def test_pipeline_vertical_japanese_chapters(self, tmp_path: Path) -> None:
        """縦書き日本語書籍（複数章）の縦書き章見出し検出および分割を検証。"""
        # 1. 3ページの縦書き書籍を作成（P1: 表紙, P2: 第1章, P3: 第2章）
        p1 = create_vertical_japanese_page("走れメロス", ["太宰治"])
        p2 = create_vertical_japanese_page("第1章 旅立ち", ["メロスは激怒した。"])
        p3 = create_vertical_japanese_page("第2章 友との再会", ["セリヌンティウスよ。"])

        book_pdf = tmp_path / "book_vertical.pdf"
        save_pages_to_pdf([p1, p2, p3], book_pdf)

        ocr_pdf = tmp_path / "book_vertical_ocr.pdf"
        if not (_is_ndlocr_available() and pdf_utils is not None):
            pytest.skip("NDLOCR-Lite が利用できないためスキップします")

        success = pdf_utils.run_ocr(book_pdf, ocr_pdf, engine="ndlocr")
        assert success is True

        reader = PdfReader(str(ocr_pdf))
        detected_chapters = pdf_chapter_pipeline.detect_chapters_by_keywords(reader)

        # 縦書きでも第1章（物理ページ 2）と第2章（物理ページ 3）が検出されること
        assert len(detected_chapters) >= 2
        pages = [c.physical_page for c in detected_chapters]
        assert 2 in pages
        assert 3 in pages

        out_dir = tmp_path / "split_output_v"
        split_results = pdf_chapter_pipeline.split_by_boundaries(reader, detected_chapters, out_dir)
        assert len(split_results) >= 2
        for item in split_results:
            p = Path(item["path"])
            assert p.exists()
            assert p.stat().st_size > 0

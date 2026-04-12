#!/usr/bin/env python3
"""
compare_pages.py
================
元画像とPDFのページを比較して切り取り結果の正否を自動判定する。

使い方:
  python3 compare_pages.py <input_folder> <output_pdf> [options]

オプション:
  --dpi INT       PDF 抽出解像度 (デフォルト: 150)
  --out-dir DIR   比較画像の出力ディレクトリ (省略時は比較画像を保存しない)
  --page-order    portrait-spread のページ順 (right_first / left_first / auto)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cv2
import fitz  # pymupdf
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# PDF → 画像抽出
# ──────────────────────────────────────────────

def extract_pdf_pages(pdf_path: Path, dpi: int = 150) -> list[np.ndarray]:
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    pages = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
            pages.append(img)
    return pages


# ──────────────────────────────────────────────
# 元画像からページ領域を再現
# ──────────────────────────────────────────────

def _is_portrait_spread(image: np.ndarray) -> bool:
    """縦長（portrait）かつ中央に横方向の綴じ目がある見開きかどうか推定する。"""
    h, w = image.shape[:2]
    if w >= h:
        return False
    # 中央付近の水平列の輝度を調べる
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    center_band = gray[h // 2 - h // 20 : h // 2 + h // 20, :]
    return float(np.mean(center_band < 100)) > 0.1  # 暗い帯がある → 綴じ目


def extract_source_pages(
    image: np.ndarray, page_order: str = "right_first"
) -> list[np.ndarray]:
    """
    元画像から各ページに対応する領域を切り出して返す。

    Portrait spread の場合:
      上半分 → 右ページ (90°CW回転)
      下半分 → 左ページ (90°CW回転)
      right_first: [上ハーフ, 下ハーフ]
      left_first : [下ハーフ, 上ハーフ]

    Landscape spread の場合:
      左半分 → left page
      右半分 → right page

    単一ページの場合:
      画像全体
    """
    h, w = image.shape[:2]
    is_portrait = h > w

    if is_portrait:
        top = cv2.rotate(image[: h // 2, :], cv2.ROTATE_90_CLOCKWISE)
        bot = cv2.rotate(image[h // 2 :, :], cv2.ROTATE_90_CLOCKWISE)
        if page_order == "right_first":
            return [top, bot]
        else:
            return [bot, top]
    elif w / h > 1.3:
        # Landscape spread
        left  = image[:, : w // 2]
        right = image[:, w // 2 :]
        if page_order == "right_first":
            return [right, left]
        else:
            return [left, right]
    else:
        return [image]


# ──────────────────────────────────────────────
# 定量比較
# ──────────────────────────────────────────────

def _text_density(gray: np.ndarray) -> float:
    return float(np.mean(gray < 80))


def _white_border_ratio(gray: np.ndarray, frac: float = 0.05) -> dict[str, float]:
    h, w = gray.shape
    bh = max(4, int(h * frac))
    bw = max(4, int(w * frac))
    white = gray >= 200
    return {
        "top":    float(np.mean(white[:bh, :])),
        "bottom": float(np.mean(white[-bh:, :])),
        "left":   float(np.mean(white[:, :bw])),
        "right":  float(np.mean(white[:, -bw:])),
    }


def _edge_text_density(gray: np.ndarray, px: int = 5) -> dict[str, float]:
    """各辺の端 px ピクセル内のテキスト密度を返す。"""
    text = gray < 80
    return {
        "top":    float(np.mean(text[:px, :])),
        "bottom": float(np.mean(text[-px:, :])),
        "left":   float(np.mean(text[:, :px])),
        "right":  float(np.mean(text[:, -px:])),
    }


def compare_page(
    src: np.ndarray,
    pdf: np.ndarray,
    page_num: int,
) -> dict:
    """
    元画像の対応領域と PDF ページを比較して判定結果を返す。

    注意: 元画像には撮影背景（机・テクスチャ）が含まれるため、
    テキスト密度の単純比較は不正確。PDF ページ自体の品質を中心に判定する。

    判定基準:
      1. PDFページのテキスト不足: テキスト密度 < 0.5% → ほぼ空白ページ
      2. アスペクト比乖離: 元（書籍領域推定）と PDF で 30% 以上乖離
      3. 文字切れ: PDF の端 5px にテキスト密度 > 2%
      4. 余分な背景: PDF の外縁 5% の白比率 < 30%
      5. ページ数不足: PDF のページ数が元より少ない（呼び出し元で検出）
    """
    src_gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
    pdf_gray = cv2.cvtColor(pdf, cv2.COLOR_BGR2GRAY)

    # テキスト密度（参考値として保持、判定には絶対閾値を使う）
    src_density = _text_density(src_gray)
    pdf_density = _text_density(pdf_gray)

    sh, sw = src.shape[:2]
    ph, pw = pdf.shape[:2]
    src_ar = sw / sh
    pdf_ar = pw / ph
    ar_diff = abs(src_ar - pdf_ar) / max(src_ar, 0.001)

    edge_text    = _edge_text_density(pdf_gray, px=5)
    white_border = _white_border_ratio(pdf_gray, frac=0.05)

    issues: list[str] = []

    # 1. PDFページがほぼ空白（コンテンツがない）
    if pdf_density < 0.005:
        issues.append(
            f"ページがほぼ空白: テキスト密度 {pdf_density:.4f} (< 0.5%)"
        )

    # 2. アスペクト比乖離
    if ar_diff > 0.30:
        issues.append(
            f"アスペクト比不整合: 元≈{src_ar:.2f} / PDF={pdf_ar:.2f} (差 {ar_diff:.0%})"
        )

    # 3. 文字切れ (PDF の端 5px にテキスト密度 > 2%)
    clipped_sides = [k for k, v in edge_text.items() if v > 0.02]
    if clipped_sides:
        issues.append(
            f"文字切れ疑い: {clipped_sides} "
            + str({k: f"{v:.3f}" for k, v in edge_text.items() if k in clipped_sides})
        )

    # 4. 余分な背景 (外縁 5% の白比率が 30% 未満)
    dark_sides = [k for k, v in white_border.items() if v < 0.30]
    if dark_sides:
        issues.append(
            f"余分な背景残留: {dark_sides} "
            + str({k: f"{v:.2f}" for k, v in white_border.items() if k in dark_sides})
        )

    return {
        "page":         page_num,
        "ok":           len(issues) == 0,
        "issues":       issues,
        "src_density":  src_density,
        "pdf_density":  pdf_density,
        "src_ar":       src_ar,
        "pdf_ar":       pdf_ar,
        "ar_diff":      ar_diff,
        "edge_text":    edge_text,
        "white_border": white_border,
    }


# ──────────────────────────────────────────────
# 比較画像の生成
# ──────────────────────────────────────────────

def _resize_to_height(img: np.ndarray, h: int) -> np.ndarray:
    scale = h / img.shape[0]
    return cv2.resize(img, (int(img.shape[1] * scale), h))


def make_comparison_image(
    src: np.ndarray,
    pdf: np.ndarray,
    result: dict,
) -> np.ndarray:
    """元画像対応領域と PDF ページを横並びにした比較画像を生成する。"""
    target_h = 600
    src_resized = _resize_to_height(src, target_h)
    pdf_resized = _resize_to_height(pdf, target_h)

    gap = np.ones((target_h, 20, 3), dtype=np.uint8) * 200
    combined = np.hstack([src_resized, gap, pdf_resized])

    # 枠・テキスト描画
    color = (0, 200, 0) if result["ok"] else (0, 0, 220)
    cv2.rectangle(combined, (0, 0), (combined.shape[1] - 1, combined.shape[0] - 1), color, 3)

    label = f"Page {result['page']}  {'OK' if result['ok'] else 'NG'}"
    cv2.putText(combined, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    cv2.putText(combined, "< Source >", (10, target_h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 80, 80), 1)
    pdf_x = src_resized.shape[1] + 30
    cv2.putText(combined, "< PDF page >", (pdf_x, target_h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 80, 80), 1)

    for i, issue in enumerate(result["issues"][:4]):
        cv2.putText(combined, f"! {issue[:70]}", (10, 55 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 220), 1)

    return combined


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────

def run(
    input_folder: Path,
    output_pdf: Path,
    dpi: int = 150,
    out_dir: Path | None = None,
    page_order: str = "right_first",
) -> bool:
    # 元画像読み込み（ソート済み）
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
    src_paths = sorted(p for p in input_folder.iterdir() if p.suffix.lower() in exts)
    if not src_paths:
        logger.error("入力フォルダに画像が見つかりません: %s", input_folder)
        return False

    src_images = [cv2.imread(str(p)) for p in src_paths]

    # 元画像からページ領域を再現
    src_pages: list[np.ndarray] = []
    for img in src_images:
        src_pages.extend(extract_source_pages(img, page_order=page_order))

    # PDF ページ抽出
    pdf_pages = extract_pdf_pages(output_pdf, dpi=dpi)

    logger.info("元画像ページ数: %d  /  PDF ページ数: %d", len(src_pages), len(pdf_pages))

    if len(src_pages) != len(pdf_pages):
        logger.warning(
            "ページ数が一致しません (元: %d, PDF: %d)。ページ数の少ない方に合わせます。",
            len(src_pages), len(pdf_pages),
        )

    n = min(len(src_pages), len(pdf_pages))

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    all_ok = True
    results = []
    for i in range(n):
        r = compare_page(src_pages[i], pdf_pages[i], page_num=i + 1)
        results.append(r)
        if not r["ok"]:
            all_ok = False

        if out_dir:
            cmp_img = make_comparison_image(src_pages[i], pdf_pages[i], r)
            out_path = out_dir / f"compare_page_{i+1:02d}.png"
            cv2.imwrite(str(out_path), cmp_img)
            logger.info("  比較画像保存: %s", out_path)

    # ── サマリー出力 ──
    print()
    print("=" * 70)
    print(f"  切り取り品質チェック: {output_pdf.name}")
    print("=" * 70)
    header = f"  {'Page':>4}  {'元密度':>6}  {'PDF密度':>7}  {'AR元':>5}  {'AR-PDF':>6}  {'結果'}"
    print(header)
    print("  " + "─" * 65)
    for r in results:
        mark = "○ OK" if r["ok"] else "✗ NG"
        print(
            f"  {r['page']:>4}  {r['src_density']:>5.3f}  "
            f"  {r['pdf_density']:>6.3f}  "
            f"  {r['src_ar']:>4.2f}  {r['pdf_ar']:>5.2f}  {mark}"
        )
        for issue in r["issues"]:
            print(f"         └ {issue}")
    print("  " + "─" * 60)
    overall = "全ページ正常" if all_ok else "問題あり"
    print(f"  総合判定: {overall}  ({sum(r['ok'] for r in results)}/{n} ページ OK)")
    print("=" * 70)

    return all_ok


def main():
    parser = argparse.ArgumentParser(description="元画像と PDF を比較して切り取り品質を判定する")
    parser.add_argument("input_folder", type=Path)
    parser.add_argument("output_pdf",   type=Path)
    parser.add_argument("--dpi",        type=int, default=150)
    parser.add_argument("--out-dir",    type=Path, default=None)
    parser.add_argument("--page-order", default="right_first",
                        choices=["right_first", "left_first", "auto"])
    args = parser.parse_args()

    ok = run(
        args.input_folder,
        args.output_pdf,
        dpi=args.dpi,
        out_dir=args.out_dir,
        page_order=args.page_order,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

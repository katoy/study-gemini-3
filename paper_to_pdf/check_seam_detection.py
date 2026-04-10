#!/usr/bin/env python3
"""
check_seam_detection.py
=======================
書籍エリアからのページ綴じ目（seam line）抽出能力を判定・評価する。

処理フロー:
  1. 書籍エリアを検出・透視変換で切り出す
  2. 見開きタイプを判定 (landscape / portrait spread / single)
  3. 綴じ目を検出し位置・信頼スコアを計算
  4. 分割後のページ品質を評価
  5. 可視化画像と定量サマリーを出力

使い方:
  python3 check_seam_detection.py <input_folder> [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from page_detector import (
    detect_page_contour,
    four_point_transform,
    trim_page_border,
    find_horizontal_seam,
    center_seam_confidence,
    split_spread,
)


# ──────────────────────────────────────────────
# 見開きタイプ判定
# ──────────────────────────────────────────────

_LANDSCAPE_AR   = 1.3   # 幅/高さ がこれ以上 → landscape spread 候補
_SEAM_CONF_THR  = 140   # portrait 画像での縦 seam 信頼度閾値

def classify_spread(image: np.ndarray) -> str:
    """
    'landscape_spread' / 'portrait_spread' / 'single' を返す。
    portrait_spread: 縦長画像の中央に横の綴じ目がある（landscape見開きを90°回転して撮影）
    """
    h, w = image.shape[:2]
    ar = w / h
    if ar >= _LANDSCAPE_AR:
        return "landscape_spread"
    if h > w:
        conf = center_seam_confidence(image)
        if conf > _SEAM_CONF_THR:
            return "portrait_spread"
    return "single"


# ──────────────────────────────────────────────
# Landscape spread: 縦の綴じ目検出
# ──────────────────────────────────────────────

def _score_profile_landscape(image: np.ndarray) -> np.ndarray:
    """列スコアプロファイル（landscape 用）を返す。値が大きいほど綴じ目らしい。"""
    h, w = image.shape[:2]
    s, e = w // 3, 2 * w // 3
    roi = cv2.cvtColor(image[:, s:e], cv2.COLOR_BGR2GRAY)
    v_blur = cv2.blur(roi, (1, max(3, h // 10)))
    col_intens = v_blur.mean(axis=0)
    grad_x = cv2.Sobel(v_blur, cv2.CV_32F, 1, 0, ksize=3)
    col_grad = np.abs(grad_x).mean(axis=0)
    score = (255 - col_intens) * 1.5 + col_grad
    smooth_k = max(11, (e - s) // 20) | 1
    score = cv2.GaussianBlur(score.reshape(1, -1), (smooth_k, 1), 0).flatten()
    return score  # 長さ = e - s, インデックスは s+i が元画像 x 座標


# ──────────────────────────────────────────────
# Portrait spread: 横の綴じ目スコアプロファイル（可視化用）
# ──────────────────────────────────────────────

def _portrait_seam_score_profile(image: np.ndarray) -> tuple[np.ndarray, float]:
    """
    コンテンツ領域面積均等のスコアプロファイル（可視化用）。
    コンテンツ領域の上端〜下端を検出し、中点が seam。
    各行のスコア = 中点からの距離が近いほど高い。
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h = gray.shape[0]
    row_white_ratio = np.mean(gray >= 200, axis=1)
    content_rows = np.where(row_white_ratio >= 0.20)[0]
    if len(content_rows) < h * 0.10:
        return np.zeros(h), 0.0
    top    = int(content_rows[0])
    bottom = int(content_rows[-1])
    mid    = (top + bottom) // 2
    # 中点からの距離を 0〜1 に正規化してスコア化（中点で最大 1.0）
    dist = np.abs(np.arange(h) - mid).astype(np.float64)
    max_dist = max(mid - top, bottom - mid, 1)
    score = np.clip(1.0 - dist / max_dist, 0.0, 1.0)
    return score, float(score[mid])


# ──────────────────────────────────────────────
# 定量評価
# ──────────────────────────────────────────────

def _text_density(gray: np.ndarray) -> float:
    return float(np.mean(gray < 80))

def _white_ratio(gray: np.ndarray) -> float:
    return float(np.mean(gray >= 200))

def evaluate_split_pages(pages: list[np.ndarray]) -> list[dict]:
    """分割後の各ページを評価する。"""
    results = []
    for i, p in enumerate(pages):
        gray = cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)
        h, w = p.shape[:2]
        results.append({
            "page":         i + 1,
            "size":         (w, h),
            "ar":           w / h,
            "text_density": _text_density(gray),
            "white_ratio":  _white_ratio(gray),
        })
    return results


def seam_center_offset(seam_pos: int, img_dim: int) -> float:
    """綴じ目位置の中心からのずれ（±%）。0 が理想。"""
    return (seam_pos / img_dim - 0.5) * 100


# ──────────────────────────────────────────────
# 可視化
# ──────────────────────────────────────────────

def _score_bar(score: np.ndarray, width: int, height: int = 60,
               peak_x: int | None = None) -> np.ndarray:
    """スコアプロファイルを棒グラフ画像にして返す。"""
    bar = np.ones((height, width, 3), dtype=np.uint8) * 240
    if len(score) == 0:
        return bar
    s_min, s_max = score.min(), score.max()
    if s_max == s_min:
        return bar
    norm = (score - s_min) / (s_max - s_min)
    xs = np.linspace(0, width - 1, len(norm)).astype(int)
    for xi, val in zip(xs, norm):
        bar_h = int(val * (height - 4))
        cv2.line(bar, (xi, height - 2), (xi, height - 2 - bar_h), (120, 160, 240), 1)
    if peak_x is not None:
        px = int(peak_x / len(score) * width)
        cv2.line(bar, (px, 0), (px, height), (0, 0, 220), 2)
    cv2.rectangle(bar, (0, 0), (width - 1, height - 1), (180, 180, 180), 1)
    return bar


def make_seam_sheet(
    orig: np.ndarray,
    book: np.ndarray,
    spread_type: str,
    seam_pos: int,
    seam_score: float,
    score_profile: np.ndarray,
    pages: list[np.ndarray],
    page_evals: list[dict],
    img_name: str,
) -> np.ndarray:
    TARGET_H = 500
    scale_o = TARGET_H / orig.shape[0]
    orig_th = cv2.resize(orig, (int(orig.shape[1] * scale_o), TARGET_H))

    scale_b = TARGET_H / book.shape[0]
    book_th = cv2.resize(book, (int(book.shape[1] * scale_b), TARGET_H))

    # 書籍画像に綴じ目線を描画
    book_ann = book_th.copy()
    h_b, w_b = book_th.shape[:2]
    if spread_type == "landscape_spread":
        px = int(seam_pos * scale_b)
        cv2.line(book_ann, (px, 0), (px, h_b), (0, 0, 220), 2)
        cv2.putText(book_ann, f"seam x={seam_pos}", (max(0, px - 60), 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 220), 1)
    elif spread_type == "portrait_spread":
        py = int(seam_pos * scale_b)
        cv2.line(book_ann, (0, py), (w_b, py), (0, 0, 220), 2)
        cv2.putText(book_ann, f"seam y={seam_pos}", (5, max(15, py - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 220), 1)

    # スコアプロファイルバー
    bar_w = book_ann.shape[1]
    if spread_type == "landscape_spread":
        score_bar = _score_bar(score_profile, bar_w, 60, peak_x=seam_pos - book.shape[1] // 3)
    elif spread_type == "portrait_spread":
        score_bar = _score_bar(score_profile, bar_w, 60, peak_x=seam_pos - book.shape[0] // 3)
    else:
        score_bar = np.ones((60, bar_w, 3), dtype=np.uint8) * 200

    # 分割後ページのサムネイル
    page_panels = []
    for p, ev in zip(pages, page_evals):
        ph, pw = p.shape[:2]
        scale_p = min(TARGET_H / ph, bar_w // 2 / pw)
        p_th = cv2.resize(p, (int(pw * scale_p), int(ph * scale_p)))
        # ラベル
        label_h = 48
        label = np.full((label_h, p_th.shape[1], 3), 245, dtype=np.uint8)
        cv2.putText(label, f"Page {ev['page']}  {ev['size'][0]}x{ev['size'][1]}",
                    (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (40, 40, 40), 1)
        cv2.putText(label, f"text={ev['text_density']:.3f}  white={ev['white_ratio']:.3f}",
                    (4, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (40, 40, 40), 1)
        ok = ev["text_density"] > 0.005 and ev["white_ratio"] > 0.35
        status = "OK" if ok else "NG"
        cv2.putText(label, status, (4, 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 160, 0) if ok else (0, 0, 200), 1)
        panel = np.vstack([p_th, label])
        page_panels.append(panel)

    # ページパネルを横並び (高さを揃える)
    max_panel_h = max(p.shape[0] for p in page_panels) if page_panels else 1
    padded = []
    for p in page_panels:
        diff = max_panel_h - p.shape[0]
        p = np.vstack([p, np.ones((diff, p.shape[1], 3), dtype=np.uint8) * 245])
        padded.append(p)

    # 各パネル幅を揃えて横結合
    target_pw = max(p.shape[1] for p in padded) if padded else 1
    resized_panels = [cv2.resize(p, (target_pw, max_panel_h)) for p in padded]

    if resized_panels:
        pages_row = np.hstack(resized_panels)
    else:
        pages_row = np.ones((max_panel_h, bar_w, 3), dtype=np.uint8) * 200

    # 右カラム: 書籍 + スコアバー + ページパネル
    right_w = max(book_ann.shape[1], score_bar.shape[1], pages_row.shape[1])

    def _pad_w(img, w):
        diff = w - img.shape[1]
        if diff > 0:
            img = np.hstack([img, np.ones((img.shape[0], diff, 3), dtype=np.uint8) * 245])
        return img

    book_ann   = _pad_w(book_ann, right_w)
    score_bar  = _pad_w(score_bar, right_w)
    pages_row  = _pad_w(pages_row, right_w)

    right_col = np.vstack([book_ann, score_bar, pages_row])

    # 左カラム: 元画像
    orig_h_total = right_col.shape[0]
    orig_th_resized = cv2.resize(orig_th, (orig_th.shape[1], orig_h_total))

    sheet = np.hstack([orig_th_resized, right_col])

    # タイトルバー
    title_h = 32
    title_bar = np.full((title_h, sheet.shape[1], 3), 50, dtype=np.uint8)
    cv2.putText(title_bar,
                f"{img_name}  [{spread_type}]  seam_score={seam_score:.1f}  seam_pos={seam_pos}",
                (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 180), 1)
    sheet = np.vstack([title_bar, sheet])
    return sheet


# ──────────────────────────────────────────────
# 1 枚の画像を評価
# ──────────────────────────────────────────────

def evaluate_image(image: np.ndarray, img_name: str, out_dir: Path | None) -> dict:
    h, w = image.shape[:2]

    # 1. 書籍エリア抜き出し
    contour = detect_page_contour(image)
    if contour is not None:
        book = four_point_transform(image, contour)
        book = trim_page_border(book)
        print(f"  書籍エリア: 検出成功 → {book.shape[1]}x{book.shape[0]}px")
    else:
        book = image.copy()
        print("  書籍エリア: 検出失敗 → 元画像をそのまま使用")

    bh, bw = book.shape[:2]

    # 2. 見開きタイプ判定
    spread_type = classify_spread(book)
    print(f"  見開きタイプ: {spread_type}")

    # 3. 綴じ目検出
    seam_pos = 0
    seam_score = 0.0
    score_profile = np.array([])
    pages: list[np.ndarray] = []

    if spread_type == "landscape_spread":
        # 縦の綴じ目 (X 座標)
        s, e = bw // 3, 2 * bw // 3
        roi = cv2.cvtColor(book[:, s:e], cv2.COLOR_BGR2GRAY)
        v_blur = cv2.blur(roi, (1, max(3, bh // 10)))
        col_intens = v_blur.mean(axis=0)
        grad_x = cv2.Sobel(v_blur, cv2.CV_32F, 1, 0, ksize=3)
        col_grad = np.abs(grad_x).mean(axis=0)
        score_profile = (255 - col_intens) * 1.5 + col_grad
        smooth_k = max(11, (e - s) // 20) | 1
        score_profile = cv2.GaussianBlur(
            score_profile.reshape(1, -1), (smooth_k, 1), 0).flatten()

        best_rel = int(np.argmax(score_profile))
        seam_pos   = s + best_rel
        seam_score = float(score_profile[best_rel])
        offset_pct = seam_center_offset(seam_pos, bw)

        pages = split_spread(book, "left_first")
        print(f"  縦綴じ目: x={seam_pos} ({seam_pos/bw*100:.1f}%)  "
              f"中心ずれ={offset_pct:+.1f}%  score={seam_score:.1f}")

    elif spread_type == "portrait_spread":
        # 横の綴じ目 (Y 座標) — 面積均等分割
        seam_pos = find_horizontal_seam(book)
        offset_pct = seam_center_offset(seam_pos, bh)

        # 可視化用スコアプロファイル（累積白面積の 0.5 クロス）
        score_profile, seam_score = _portrait_seam_score_profile(book)

        print(f"  横綴じ目(面積均等): y={seam_pos} ({seam_pos/bh*100:.1f}%)  "
              f"中心ずれ={offset_pct:+.1f}%  score={seam_score:.3f}")

        # 検出位置で分割
        margin = max(4, int(bh * 0.005))
        top_img = book[:seam_pos, :].copy()
        bot_img = book[seam_pos:, :].copy()
        top_img[-margin:, :] = 255
        bot_img[:margin, :] = 255
        top_page = cv2.rotate(top_img, cv2.ROTATE_90_CLOCKWISE)
        bot_page = cv2.rotate(bot_img, cv2.ROTATE_90_CLOCKWISE)
        pages = [top_page, bot_page]

    else:
        # 単一ページ: 綴じ目なし
        pages = [book]
        print("  単一ページ: 綴じ目検出不要")

    # 4. 分割後ページ評価
    page_evals = evaluate_split_pages(pages)
    for ev in page_evals:
        ok = ev["text_density"] > 0.005 and ev["white_ratio"] > 0.35
        mark = "○" if ok else "✗"
        print(f"    Page {ev['page']}: {ev['size'][0]}x{ev['size'][1]}  "
              f"AR={ev['ar']:.2f}  text={ev['text_density']:.3f}  "
              f"white={ev['white_ratio']:.3f}  {mark}")

    # 5. 総合判定
    issues = []
    if spread_type != "single":
        if abs(seam_center_offset(seam_pos,
                bw if spread_type == "landscape_spread" else bh)) > 15:
            issues.append(f"綴じ目が中心から大きくずれている (>{15}%)")
        # スコア閾値: landscape は輝度ベース(0〜数百)、portrait は面積均等(0〜1)
        if spread_type == "landscape_spread" and seam_score < 100:
            issues.append(f"綴じ目スコアが低い ({seam_score:.1f} < 100)")
        elif spread_type == "portrait_spread" and seam_score < 0.5:
            issues.append(f"面積均等スコアが低い ({seam_score:.3f} < 0.5、コンテンツ行不足)")
    for ev in page_evals:
        if ev["text_density"] <= 0.005:
            issues.append(f"Page {ev['page']} がほぼ空白")
        if ev["white_ratio"] <= 0.30:
            issues.append(f"Page {ev['page']} の白比率が低い ({ev['white_ratio']:.2f} ≤ 0.30)")

    ok = len(issues) == 0
    mark = "○ OK" if ok else "✗ NG"
    print(f"  総合: {mark}" + (f"  ({'; '.join(issues)})" if issues else ""))

    # 6. 可視化
    if out_dir is not None:
        sheet = make_seam_sheet(
            image, book, spread_type,
            seam_pos, seam_score, score_profile,
            pages, page_evals, img_name,
        )
        out_path = out_dir / f"seam_{Path(img_name).stem}.png"
        cv2.imwrite(str(out_path), sheet)
        print(f"  → 可視化: {out_path}")

    return {
        "img":         img_name,
        "spread_type": spread_type,
        "seam_pos":    seam_pos,
        "seam_score":  seam_score,
        "ok":          ok,
        "issues":      issues,
        "page_evals":  page_evals,
    }


# ──────────────────────────────────────────────
# エントリポイント
# ──────────────────────────────────────────────

def run(input_folder: Path, out_dir: Path | None) -> bool:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
    paths = sorted(p for p in input_folder.iterdir() if p.suffix.lower() in exts)
    if not paths:
        print("入力フォルダに画像が見つかりません:", input_folder)
        return False

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("  ページ綴じ目 抽出能力チェック")
    print("=" * 65)

    all_results = []
    for p in paths:
        image = cv2.imread(str(p))
        if image is None:
            print(f"[スキップ] 読み込み失敗: {p.name}")
            continue
        print(f"\n▶ {p.name}")
        r = evaluate_image(image, p.name, out_dir)
        all_results.append(r)

    # サマリー
    n_ok = sum(1 for r in all_results if r["ok"])
    print("\n" + "=" * 65)
    print(f"  総合: {n_ok}/{len(all_results)} 画像で綴じ目検出 OK")
    print("=" * 65)
    return n_ok == len(all_results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_folder", type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    ok = run(args.input_folder, args.out_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

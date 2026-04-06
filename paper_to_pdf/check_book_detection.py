#!/usr/bin/env python3
"""
check_book_detection.py
=======================
書籍エリア抜き出し能力を評価するスクリプト。

各入力画像に対して 5 段階の検出手法を個別に試し、
どの手法が成功したか・検出エリアの品質を可視化・定量評価する。

使い方:
  python3 check_book_detection.py <input_folder> [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

# page_detector の内部関数を直接インポート
from page_detector import (
    _detect_by_edge_and_profile,
    _detect_by_book_region,
    _detect_by_adaptive_thresh,
    _detect_by_brightness,
    _detect_by_canny,
    _detect_by_white_profile,
    _detect_by_saturation,
    _is_valid_quad,
    order_points,
    four_point_transform,
    trim_page_border,
)

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)

METHODS = [
    ("edge_and_profile", _detect_by_edge_and_profile),
    ("book_region",      _detect_by_book_region),
    ("adaptive_thresh",  _detect_by_adaptive_thresh),
    ("brightness",       _detect_by_brightness),
    ("canny",            _detect_by_canny),
    ("white_profile",    _detect_by_white_profile),
    ("saturation",       _detect_by_saturation),
]

# 各手法の表示色 (BGR)
METHOD_COLORS = {
    "edge_and_profile": (0,   255, 128),   # 黄緑
    "book_region":      (0,   255, 255),   # シアン
    "adaptive_thresh":  (0,   200,   0),   # 緑
    "brightness":       (255, 150,   0),   # 水色
    "canny":            (0,   100, 255),   # オレンジ
    "white_profile":    (200,   0, 200),   # 紫
    "saturation":       (0,   200, 200),   # 黄
}


# ──────────────────────────────────────────────
# 定量指標
# ──────────────────────────────────────────────

def _quad_area_ratio(pts: np.ndarray, img_shape: tuple) -> float:
    """検出クォッドの面積 / 画像面積 の比率。"""
    ordered = order_points(pts)
    x, y = ordered[:, 0], ordered[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    return area / (img_shape[0] * img_shape[1])


def _quad_rectangularity(pts: np.ndarray) -> float:
    """
    クォッドの矩形度 (0〜1)。
    凸包面積 / 最小外接矩形面積。1.0 に近いほど矩形に近い。
    """
    ordered = order_points(pts).astype(np.float32)
    hull_area = cv2.contourArea(ordered)
    rect = cv2.minAreaRect(ordered)
    rect_area = rect[1][0] * rect[1][1]
    if rect_area < 1:
        return 0.0
    return min(1.0, hull_area / rect_area)


def _white_ratio_inside(image: np.ndarray, pts: np.ndarray) -> float:
    """
    検出クォッド内部の白ピクセル (輝度 >= 200) 比率。
    書籍ページは白比率が高い (≥ 50%) はず。
    """
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    ordered = order_points(pts).astype(np.int32)
    cv2.fillPoly(mask, [ordered], 255)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    inside = gray[mask == 255]
    if len(inside) == 0:
        return 0.0
    return float(np.mean(inside >= 200))


# ──────────────────────────────────────────────
# 可視化
# ──────────────────────────────────────────────

def _draw_quad(img: np.ndarray, pts: np.ndarray, color: tuple, label: str) -> np.ndarray:
    out = img.copy()
    ordered = order_points(pts).astype(np.int32)
    cv2.polylines(out, [ordered.reshape(-1, 1, 2)], True, color, 3)
    # 左上コーナーにラベル
    x, y = int(ordered[0][0]), int(ordered[0][1])
    cv2.putText(out, label, (max(5, x), max(20, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    return out


def make_detection_sheet(
    image: np.ndarray,
    results: list[dict],
    img_name: str,
) -> np.ndarray:
    """
    全手法の検出結果を 1 枚のシート画像にまとめる。

    レイアウト:
      上段: 元画像 (全手法の検出枠を重ねて描画)
      下段: 各手法の個別結果 (採用手法は warped 画像も表示)
    """
    TARGET_H = 480
    scale = TARGET_H / image.shape[0]
    thumb_h, thumb_w = TARGET_H, int(image.shape[1] * scale)

    # ── 上段: 全手法を重ねた概要画像 ──
    overview = cv2.resize(image, (thumb_w, thumb_h))
    first_valid = None
    for r in results:
        if r["pts"] is not None:
            scaled_pts = (r["pts"] * scale).astype(np.float32)
            color = METHOD_COLORS[r["method"]]
            label = r["method"][:3].upper()
            overview = _draw_quad(overview, scaled_pts, color, label)
            if first_valid is None and r["valid"]:
                first_valid = r

    # タイトル
    cv2.putText(overview, img_name, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    # ── 下段: 各手法の個別パネル ──
    panel_w = thumb_w
    panels = []
    for r in results:
        panel = np.zeros((thumb_h, panel_w, 3), dtype=np.uint8)
        color = METHOD_COLORS[r["method"]]
        bg_color = (30, 30, 30)  # 暗いグレー背景

        if r["pts"] is not None:
            # 検出された → warped 画像を表示
            try:
                warped = four_point_transform(image, r["pts"])
                warped = trim_page_border(warped)
                ph, pw = warped.shape[:2]
                scale_p = min(panel_w / pw, thumb_h / ph)
                disp = cv2.resize(warped, (int(pw * scale_p), int(ph * scale_p)))
                dh, dw = disp.shape[:2]
                y0 = (thumb_h - dh) // 2
                x0 = (panel_w - dw) // 2
                panel[y0:y0 + dh, x0:x0 + dw] = disp
            except Exception:
                pass

        # ステータスバー
        bar_h = 52
        bar = np.full((bar_h, panel_w, 3), bg_color, dtype=np.uint8)
        status = "✓ VALID" if r["valid"] else ("検出済(無効)" if r["pts"] is not None else "× FAILED")
        bar_color = color if r["valid"] else (100, 100, 100)
        cv2.rectangle(bar, (0, 0), (panel_w - 1, bar_h - 1), bar_color, 2)
        cv2.putText(bar, r["method"], (6, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, bar_color, 1)
        cv2.putText(bar, status, (6, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, bar_color, 1)
        if r["pts"] is not None:
            metrics = (
                f"area={r['area_ratio']:.2f}  rect={r['rect']:.2f}  white={r['white']:.2f}"
            )
            cv2.putText(bar, metrics, (6, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
        panel_with_bar = np.vstack([panel, bar])
        panels.append(panel_with_bar)

    bottom_row = np.hstack(panels)
    # overview を bottom_row の幅に合わせてリサイズ
    total_w = bottom_row.shape[1]
    overview_resized = cv2.resize(overview, (total_w, thumb_h))
    sheet = np.vstack([overview_resized, bottom_row])
    return sheet


# ──────────────────────────────────────────────
# 1 枚の画像を評価
# ──────────────────────────────────────────────

def evaluate_image(image: np.ndarray, img_name: str) -> list[dict]:
    h, w = image.shape[:2]
    scale = 600 / h
    small = cv2.resize(image, (int(w * scale), 600))

    results = []
    for method_name, detector in METHODS:
        pts = detector(small, scale)
        valid = _is_valid_quad(pts, image.shape)

        entry: dict = {
            "method": method_name,
            "pts":    pts,
            "valid":  valid,
        }
        if pts is not None:
            entry["area_ratio"] = _quad_area_ratio(pts, image.shape)
            entry["rect"]       = _quad_rectangularity(pts)
            entry["white"]      = _white_ratio_inside(image, pts)
        else:
            entry["area_ratio"] = 0.0
            entry["rect"]       = 0.0
            entry["white"]      = 0.0

        results.append(entry)
    return results


# ──────────────────────────────────────────────
# サマリー出力
# ──────────────────────────────────────────────

def print_summary(img_name: str, results: list[dict]) -> bool:
    first_valid = next((r for r in results if r["valid"]), None)

    print(f"\n{'─'*65}")
    print(f"  画像: {img_name}")
    print(f"  {'手法':<20}  {'検出':^4}  {'有効':^4}  {'面積比':>6}  {'矩形度':>6}  {'白比率':>6}")
    print(f"  {'─'*60}")
    for r in results:
        det  = "○" if r["pts"] is not None else "×"
        val  = "○" if r["valid"] else ("△" if r["pts"] is not None else "×")
        print(
            f"  {r['method']:<20}  {det:^4}  {val:^4}  "
            f"{r['area_ratio']:>6.3f}  {r['rect']:>6.3f}  {r['white']:>6.3f}"
        )
    print(f"  {'─'*60}")
    if first_valid:
        print(f"  採用手法: {first_valid['method']}  "
              f"(面積比={first_valid['area_ratio']:.3f}, "
              f"矩形度={first_valid['rect']:.3f}, "
              f"白比率={first_valid['white']:.3f})")
    else:
        print("  !! 全手法が失敗 — フォールバック（輪郭なし）になります")

    return first_valid is not None


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

    all_ok = True
    print("=" * 65)
    print("  書籍エリア抜き出し能力チェック")
    print("  凡例: 面積比=0.25〜0.995 / 矩形度≥0.8 / 白比率≥0.5 が理想")
    print("=" * 65)

    for p in paths:
        image = cv2.imread(str(p))
        if image is None:
            print(f"  [スキップ] 読み込み失敗: {p.name}")
            continue

        results = evaluate_image(image, p.name)
        ok = print_summary(p.name, results)
        if not ok:
            all_ok = False

        if out_dir:
            sheet = make_detection_sheet(image, results, p.name)
            out_path = out_dir / f"detect_{p.stem}.png"
            cv2.imwrite(str(out_path), sheet)
            print(f"  → 可視化画像: {out_path}")

    print("=" * 65)
    print(f"  総合: {'全画像で書籍エリア検出成功' if all_ok else '一部画像で検出失敗あり'}")
    print("=" * 65)
    return all_ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_folder", type=Path)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    ok = run(args.input_folder, args.out_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

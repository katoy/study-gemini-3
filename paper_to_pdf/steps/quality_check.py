"""
steps/quality_check.py
======================
PDF結合前に各ページ画像の品質を自動評価するステップ。
画像は変更せず、評価結果をログに出力する。

評価基準:
  1. 文字が見切れていない  (text_clipped)
  2. 余分な領域が残っていない (extra_region)
  3. ページのゆがみが補正されている (distorted)
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from steps.base import ProcessingStep

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 個別評価関数
# ──────────────────────────────────────────────

def _check_text_clipping(gray: np.ndarray) -> tuple[bool, dict]:
    """
    外縁 (画像短辺の 3%) にテキストピクセルが存在するかで見切れを検出する。

    2段階判定:
      1. 外縁マージン全体 (3%) のテキスト密度が threshold 以上 → 候補
      2. 端から edge_safe_px 以内にテキストが存在する → 真に見切れ
         (余白が端から edge_safe_px 以上あればページ内容がマージンに来ていても見切れでない)

    この方式により「ページ余白が狭くてテキストが3%マージン内に入る」ケースの
    false positive を抑制しつつ、実際に端まで文字が達しているケースを検出できる。
    """
    h, w = gray.shape
    margin_h = max(15, int(h * 0.03))
    margin_w = max(15, int(w * 0.03))
    text = gray < 80
    densities = {
        "top":    float(np.mean(text[:margin_h, :])),
        "bottom": float(np.mean(text[-margin_h:, :])),
        "left":   float(np.mean(text[:, :margin_w])),
        "right":  float(np.mean(text[:, -margin_w:])),
    }
    threshold = 0.02
    # 端から何px以内にテキストがあれば「見切れ」とみなすか
    # 0.5% or 最低 5px
    edge_safe_px = max(5, int(min(h, w) * 0.005))

    flags: dict[str, bool] = {}
    for k, density in densities.items():
        if density <= threshold:
            flags[k] = False
            continue
        # マージン内にテキストはあるが、端そのものにテキストがあるか確認
        if k == "top":
            edge_d = float(np.mean(text[:edge_safe_px, :]))
        elif k == "bottom":
            edge_d = float(np.mean(text[-edge_safe_px:, :]))
        elif k == "left":
            edge_d = float(np.mean(text[:, :edge_safe_px]))
        else:  # right
            edge_d = float(np.mean(text[:, -edge_safe_px:]))
        flags[k] = edge_d > threshold

    return any(flags.values()), densities


def _check_extra_region(gray: np.ndarray, border_frac: float = 0.08) -> tuple[bool, dict]:
    """
    外周 border_frac 割合の白ピクセル比率で余分な背景を検出する。

    根拠: ページ内容（白地＋テキスト）は白ピクセル≥ 45% を持つ。
    籐・机テクスチャは中程度輝度が多く白比率 < 45% になる。
    """
    h, w = gray.shape
    bh = max(4, int(h * border_frac))
    bw = max(4, int(w * border_frac))
    white = gray >= 200

    ratios = {
        "top":    float(np.mean(white[:bh, :])),
        "bottom": float(np.mean(white[-bh:, :])),
        "left":   float(np.mean(white[:, :bw])),
        "right":  float(np.mean(white[:, -bw:])),
    }
    threshold = 0.45
    flags = {k: v < threshold for k, v in ratios.items()}
    return any(flags.values()), ratios


def _check_bottom_cut(gray: np.ndarray) -> tuple[bool, dict]:
    """
    下部欠けを検出する。

    パターン: 下部20%にテキストが一切ない AND 60-80%領域にテキストが存在する
    → テキストが続いているはずなのに下部で急に消えている = 下部欠け
    """
    h = gray.shape[0]
    text = (gray < 80)
    row_has_text = np.mean(text, axis=1) > 0.01

    region_60_80 = bool(np.any(row_has_text[int(h * 0.60): int(h * 0.80)]))
    bottom_20    = bool(np.any(row_has_text[int(h * 0.80):]))

    cut = region_60_80 and not bottom_20
    details = {
        "region_60_80_has_text": region_60_80,
        "bottom_20_has_text":    bottom_20,
    }
    return cut, details


def _check_content_coverage(gray: np.ndarray) -> tuple[bool, dict]:
    """
    ページを上下・左右の2分割で比較し、一方が著しく空白なら欠けと判断する。

    旧実装では未検出だった問題:
      - 90°回転でページ内容が半分 (一方向のみに集中)
      - 下部が大きく欠けてほぼ空白になっている

    判定: 一方の密度が他方の 15% 以下なら「片側欠け」とする。
    """
    h, w = gray.shape
    text = (gray < 80).astype(np.float32)

    top_d    = float(np.mean(text[:h // 2, :]))
    bottom_d = float(np.mean(text[h // 2:, :]))
    left_d   = float(np.mean(text[:, :w // 2]))
    right_d  = float(np.mean(text[:, w // 2:]))

    details = {
        "top": top_d, "bottom": bottom_d,
        "left": left_d, "right": right_d,
    }

    ratio_thresh = 0.15  # 一方が他方の 15% 以下なら欠けと判断
    issues: dict[str, bool] = {}
    _pair_check = [
        ("top",    "bottom", top_d,    bottom_d),
        ("left",   "right",  left_d,   right_d),
    ]
    for a_name, b_name, a_val, b_val in _pair_check:
        ref = max(a_val, b_val)
        if ref > 0.001:
            if a_val < ref * ratio_thresh:
                issues[f"{a_name}_empty"] = True
            if b_val < ref * ratio_thresh:
                issues[f"{b_name}_empty"] = True

    return bool(issues), details


def _check_distortion(gray: np.ndarray, angle_threshold: float = 2.0) -> tuple[bool, float]:
    """
    2段階で傾き・90°回転を検出する。

    Stage 1 (粗探索 ±90°, 5°刻み): 90°近辺の大きな回転を検出。
      旧実装は ±15° しか探索せず、90°回転を「縦書き正常」と誤判定していた。
    Stage 2 (精細探索 ±15°, 0.5°刻み): 微小傾きを精密検出。

    angle_threshold を超えた場合に歪みありと判断する。
    """
    scale = 400.0 / gray.shape[0]
    small = cv2.resize(gray, (int(gray.shape[1] * scale), 400))
    blur = cv2.GaussianBlur(small, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    sh, sw = thresh.shape
    cx, cy = sw // 2, sh // 2

    def _score_at(angle: float) -> float:
        M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        rot = cv2.warpAffine(thresh, M, (sw, sh), flags=cv2.INTER_NEAREST)
        return max(
            float(np.var(np.sum(rot, axis=1))),
            float(np.var(np.sum(rot, axis=0))),
        )

    # Stage 1: 粗探索 ±90° (5° 刻み)
    # 角度ペナルティ (0.1%/degree) を加えて 0° 付近を優先する。
    # 同スコアのとき ±90° でなく 0° が選ばれるようにする。
    _ANGLE_PENALTY = 0.001  # per degree
    coarse_best_score, coarse_best = -1.0, 0.0
    for a in np.arange(-90.0, 90.1, 5.0):
        s = _score_at(a) * (1.0 - abs(a) * _ANGLE_PENALTY)
        if s > coarse_best_score:
            coarse_best_score = s
            coarse_best = a

    # Stage 2: Stage1 中心の ±15° を精細探索
    fine_best_score, fine_best = -1.0, coarse_best
    for a in np.arange(coarse_best - 15.0, coarse_best + 15.1, 0.5):
        s = _score_at(a)
        if s > fine_best_score:
            fine_best_score = s
            fine_best = a

    return abs(fine_best) > angle_threshold, fine_best


# ──────────────────────────────────────────────
# ページ評価エントリポイント
# ──────────────────────────────────────────────

def evaluate_page(image: np.ndarray, page_num: int = 1) -> dict:
    """
    1枚のページ画像に対して4基準の品質評価を実施し、結果辞書を返す。

    Returns:
      page              : int   ページ番号
      ok                : bool  全基準クリアなら True
      text_clipped      : bool  文字が見切れている疑いがある (端部 3% にテキスト)
      extra_region      : bool  余分な領域が残っている
      distorted         : bool  傾き/回転あり (±90° 粗探索 + ±15° 精細)
      half_content      : bool  コンテンツが片側のみ (欠けまたは90°回転の疑い)
      skew_angle        : float 推定傾き角度 (度)
      clip_detail       : dict  各辺のテキスト密度
      extra_detail      : dict  各辺の白ピクセル比率
      coverage_detail   : dict  上下左右のテキスト密度
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    clipped,      clip_detail     = _check_text_clipping(gray)
    has_extra,    extra_detail    = _check_extra_region(gray)
    distorted,    skew_angle      = _check_distortion(gray)
    half_content, coverage_detail = _check_content_coverage(gray)
    bottom_cut,   bottom_detail   = _check_bottom_cut(gray)

    ok = not clipped and not has_extra and not distorted and not half_content and not bottom_cut
    return {
        "page":            page_num,
        "ok":              ok,
        "text_clipped":    clipped,
        "extra_region":    has_extra,
        "distorted":       distorted,
        "half_content":    half_content,
        "bottom_cut":      bottom_cut,
        "skew_angle":      skew_angle,
        "clip_detail":     clip_detail,
        "extra_detail":    extra_detail,
        "coverage_detail": coverage_detail,
        "bottom_detail":   bottom_detail,
    }


def _log_page_result(r: dict) -> None:
    sym = lambda b: "✗" if b else "○"
    level = logging.WARNING if not r["ok"] else logging.INFO
    logger.log(
        level,
        "品質評価 Page %2d: 文字見切れ=%s  余分領域=%s  歪み=%s(%.1f°)  半欠け=%s  下部欠け=%s%s",
        r["page"],
        sym(r["text_clipped"]),
        sym(r["extra_region"]),
        sym(r["distorted"]),
        r["skew_angle"],
        sym(r["half_content"]),
        sym(r["bottom_cut"]),
        "  ← 要確認" if not r["ok"] else "",
    )
    if r["text_clipped"]:
        logger.warning(
            "    └ text_clipping: %s",
            {k: f"{v:.3f}" for k, v in r["clip_detail"].items()},
        )
    if r["extra_region"]:
        logger.warning(
            "    └ extra_region : %s",
            {k: f"{v:.2f}" for k, v in r["extra_detail"].items()},
        )
    if r["half_content"]:
        logger.warning(
            "    └ coverage    : %s",
            {k: f"{v:.3f}" for k, v in r["coverage_detail"].items()},
        )
    if r["bottom_cut"]:
        logger.warning(
            "    └ bottom_cut  : %s",
            r["bottom_detail"],
        )


# ──────────────────────────────────────────────
# パイプラインステップ
# ──────────────────────────────────────────────

class QualityCheckStep(ProcessingStep):
    """
    各ページ画像の品質を自動評価し、結果をログに出力する。
    画像リストは変更せずそのまま返す（非破壊ステップ）。
    """

    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        results = [evaluate_page(img, i + 1) for i, img in enumerate(images)]

        # ── サマリーテーブルをログ出力 ──
        n_ok = sum(1 for r in results if r["ok"])
        logger.info("━━━ 品質評価サマリー: %d / %d ページ 全基準クリア ━━━", n_ok, len(results))
        logger.info("  %4s  %-8s  %-8s  %-8s  %-8s  %-8s  %s",
                    "Page", "文字見切", "余分領域", "歪み", "半欠け", "下部欠け", "傾き°")
        logger.info("  %s", "─" * 64)

        for r in results:
            sym = lambda b: "✗ NG" if b else "○ OK"
            logger.info(
                "  %4d  %-8s  %-8s  %-8s  %-8s  %-8s  %+.1f",
                r["page"],
                sym(r["text_clipped"]),
                sym(r["extra_region"]),
                sym(r["distorted"]),
                sym(r["half_content"]),
                sym(r["bottom_cut"]),
                r["skew_angle"],
            )
            _log_page_result(r)

        if n_ok < len(results):
            logger.warning("品質基準を満たさないページがあります。上記の詳細を確認してください。")

        return images  # 画像は変更しない

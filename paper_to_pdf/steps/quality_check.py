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
import sys

import cv2
import numpy as np

from steps.base import ProcessingStep
from utils.image import extract_line_profiles

logger = logging.getLogger(__name__)


def _red(s: str) -> str:
    """stderr が TTY の場合のみ赤色 ANSI コードを付ける。"""
    if sys.stderr.isatty():
        return f"\033[31m{s}\033[0m"
    return s


def _content_bbox(gray: np.ndarray) -> tuple[int, int, int, int]:
    """
    normalize_size が作る白キャンバス上の実コンテンツ領域を返す。
    非白ピクセル（< 250）が存在する行・列の範囲を求める。
    全白の場合は画像全体を返す。
    """
    non_white = gray < 250
    rows = np.any(non_white, axis=1)
    cols = np.any(non_white, axis=0)
    if not rows.any() or not cols.any():
        return 0, 0, gray.shape[1] - 1, gray.shape[0] - 1
    r_min = int(np.argmax(rows))
    r_max = int(len(rows) - 1 - np.argmax(rows[::-1]))
    c_min = int(np.argmax(cols))
    c_max = int(len(cols) - 1 - np.argmax(cols[::-1]))
    return c_min, r_min, c_max, r_max


# ──────────────────────────────────────────────
# 個別評価関数
# ──────────────────────────────────────────────

def _check_text_clipping(gray: np.ndarray) -> tuple[bool, dict]:
    """
    コンテンツ領域の外縁にテキストが端まで達しているかで見切れを検出する。

    normalize_size は実コンテンツを白キャンバスに中央配置するため、
    キャンバス端ではなくコンテンツ境界で判定する。

    2段階判定:
      1. コンテンツ外縁マージン (2%) のテキスト密度が margin_threshold 以上 → 候補
      2. コンテンツ境界から edge_safe_px (短辺の 0.8%) 以内にテキストが存在する → 真に見切れ
    """
    x0, y0, x1, y1 = _content_bbox(gray)
    # コンテンツ領域を切り出して判定
    content = gray[y0:y1 + 1, x0:x1 + 1]
    ch, cw = content.shape

    # 白紙・扉ページ等、全体テキスト密度が極めて低い場合は見切れ判定をスキップ
    # 判定用の文字閾値を 80 -> 60 に厳格化（薄い影を無視）
    overall_density = float(np.mean(content < 60))
    if overall_density < 0.005:
        return False, {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}

    margin_h = max(10, int(ch * 0.02))
    margin_w = max(10, int(cw * 0.02))
    text = content < 60
    densities = {
        "top":    float(np.mean(text[:margin_h, :])),
        "bottom": float(np.mean(text[-margin_h:, :])),
        "left":   float(np.mean(text[:, :margin_w])),
        "right":  float(np.mean(text[:, -margin_w:])),
    }
    # マージン全体の密度閾値（10% 以上で見切れの可能性）
    margin_threshold = 0.10
    # コンテンツ端そのものにテキストがある場合の閾値
    edge_threshold = 0.08
    # コンテンツ端から何px以内にテキストがあれば「見切れ」とみなすか
    edge_safe_px = max(6, int(min(ch, cw) * 0.008))

    flags: dict[str, bool] = {}
    for k, density in densities.items():
        if density <= margin_threshold:
            flags[k] = False
            continue
        if k == "top":
            edge_d = float(np.mean(text[:edge_safe_px, :]))
        elif k == "bottom":
            edge_d = float(np.mean(text[-edge_safe_px:, :]))
        elif k == "left":
            edge_d = float(np.mean(text[:, :edge_safe_px]))
        else:  # right
            edge_d = float(np.mean(text[:, -edge_safe_px:]))
        flags[k] = edge_d > edge_threshold

    return any(flags.values()), densities


def _check_extra_region(gray: np.ndarray, border_frac: float = 0.08) -> tuple[bool, dict]:
    h, w = gray.shape
    bh = max(4, int(h * border_frac))
    bw = max(4, int(w * border_frac))
    # 「白」の定義を 200 -> 180 へ緩和（少し暗い紙でもOK）
    white   = gray >= 180
    midgray = (gray >= 100) & (gray < 220)

    # ページ中央のテキスト密度（文字数が多いページは判定をスキップ）
    center = gray[bh:h - bh, bw:w - bw]
    center_text_density = float(np.mean(center < 80)) if center.size > 0 else 0.0

    regions = {
        "top":    (white[:bh, :],   midgray[:bh, :]),
        "bottom": (white[-bh:, :],  midgray[-bh:, :]),
        "left":   (white[:, :bw],   midgray[:, :bw]),
        "right":  (white[:, -bw:],  midgray[:, -bw:]),
    }
    # 白比率 30% 未満を背景残留と判定（旧 35%）
    white_threshold   = 0.30
    # 中間グレー密度 80% 超を背景残留と判定（旧 65%）
    midgray_threshold = 0.80

    ratios: dict[str, float] = {}
    flags:  dict[str, bool]  = {}
    for k, (wr, mr) in regions.items():
        w_ratio = float(np.mean(wr))
        m_ratio = float(np.mean(mr))
        ratios[k] = w_ratio
        low_white  = w_ratio < white_threshold
        # 白比率が高い（w_ratio >= 0.80）場合はチェックをスキップ（旧 0.85）
        grayish    = (w_ratio < 0.80) and m_ratio > midgray_threshold and center_text_density < 0.03
        flags[k]   = low_white or grayish

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

    # 60-80% 領域でテキスト行が「連続的に存在する」かを確認（単一の疎な行は除外）
    # 10% 以上の行にテキストがある場合のみ「コンテンツ継続」と判断する
    rows_60_80   = row_has_text[int(h * 0.60): int(h * 0.80)]
    region_60_80 = float(np.mean(rows_60_80)) > 0.10  # 10% 以上の行にテキスト
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

    判定: 密な側のテキスト密度が 0.5% 以上で、かつ疎な側が密な側の 15% 以下なら「片側欠け」とする。
    テキスト密度が全体的に低いページ（表紙・扉・図版等）は除外する。
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

    ratio_thresh   = 0.15   # 一方が他方の 15% 以下なら欠けと判断
    min_dense_side = 0.008  # 0.8% 未満なら疎すぎてチェック不能（図版ページ等）


    issues: dict[str, bool] = {}
    _pair_check = [
        ("top",    "bottom", top_d,    bottom_d),
        ("left",   "right",  left_d,   right_d),
    ]
    for a_name, b_name, a_val, b_val in _pair_check:
        ref = max(a_val, b_val)
        if ref < min_dense_side:
            continue  # 両方とも疎 → 図版ページ等なのでスキップ
        if a_val < ref * ratio_thresh:
            issues[f"{a_name}_empty"] = True
        if b_val < ref * ratio_thresh:
            issues[f"{b_name}_empty"] = True

    return bool(issues), details


def _check_distortion(gray: np.ndarray, angle_threshold: float = 2.0, curve_threshold_pct: float = 3.0) -> tuple[bool, float, float]:
    """
    傾き（Skew）と湾曲（Curvature）の両方を検出する。
    評価対象を中央部に限定し、ページ端のカーブによる誤判定を防止する。
    """
    h, w = gray.shape
    scale = 400.0 / h
    small = cv2.resize(gray, (int(w * scale), 400))
    
    # 1. 傾き検出
    blur = cv2.GaussianBlur(small, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    sh, sw = thresh.shape
    cx, cy = sw // 2, sh // 2

    def _score_at(angle: float) -> float:
        M = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
        rot = cv2.warpAffine(thresh, M, (sw, sh), flags=cv2.INTER_NEAREST)
        return float(np.var(np.sum(rot, axis=1)))

    best_angle = 0.0
    if np.mean(thresh) > 0.001:
        best_score = -1.0
        for a in np.arange(-5.0, 5.1, 0.5):
            s = _score_at(a)
            if s > best_score:
                best_score = s
                best_angle = a

    # 2. 湾曲検出 (共通ロジックを使用)
    pts_np, weights_np, inv_scale = extract_line_profiles(gray, target_h=400, margin_v=0.15, margin_h=0.10)
    
    max_curve_off_pct = 0.0
    if len(pts_np) > 50:
        # スケールを small (400px) 基準に戻してフィッティング
        xs, ys = pts_np[:, 0] / inv_scale, pts_np[:, 1] / inv_scale
        z = np.polyfit(xs, ys, 2, w=weights_np)
        poly = np.poly1d(z)
        target = poly(np.arange(sw))
        offset = np.max(target) - np.min(target)
        max_curve_off_pct = (offset / sh) * 100.0

    is_distorted = abs(best_angle) > angle_threshold or max_curve_off_pct > curve_threshold_pct
    return is_distorted, best_angle, max_curve_off_pct


# ──────────────────────────────────────────────
# ページ評価エントリポイント
# ──────────────────────────────────────────────

def evaluate_page(image: np.ndarray, page_num: int = 1) -> dict:
    """
    1枚のページ画像に対して品質評価を実施し、結果辞書を返す。
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # ページ全体の白比率 (背景除去の成否の指標)
    overall_white = float(np.mean(gray >= 200))

    clipped,      clip_detail     = _check_text_clipping(gray)
    has_extra,    extra_detail    = _check_extra_region(gray)
    is_distorted, skew_angle, curve_pct = _check_distortion(gray)
    half_content, coverage_detail = _check_content_coverage(gray)
    bottom_cut,   bottom_detail   = _check_bottom_cut(gray)

    ok = not clipped and not has_extra and not is_distorted and not half_content and not bottom_cut
    return {
        "page":            page_num,
        "ok":              ok,
        "white_ratio":     overall_white,
        "text_clipped":    clipped,
        "extra_region":    has_extra,
        "distorted":       is_distorted,
        "half_content":    half_content,
        "bottom_cut":      bottom_cut,
        "skew_angle":      skew_angle,
        "curve_pct":       curve_pct,
        "clip_detail":     clip_detail,
        "extra_detail":    extra_detail,
        "coverage_detail": coverage_detail,
        "bottom_detail":   bottom_detail,
    }


def _log_page_result(r: dict) -> None:
    """問題があるページのみログ出力する（OK ページはサイレント）。"""
    if r["ok"]:
        return  # 全基準クリアのページは個別ログを省略
    sym = lambda b: _red("✗") if b else "○"
    logger.warning(
        "品質評価 Page %2d: 文字見切れ=%s  余分領域=%s  歪み=%s(傾き%.1f°,湾曲%.1f%%)  半欠け=%s  下部欠け=%s  ← 要確認",
        r["page"],
        sym(r["text_clipped"]),
        sym(r["extra_region"]),
        sym(r["distorted"]),
        r["skew_angle"],
        r["curve_pct"],
        sym(r["half_content"]),
        sym(r["bottom_cut"]),
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
    ページ番号は全入力画像を通した通し番号で管理する。
    """

    def __init__(self, config):
        super().__init__(config)
        self._page_offset = 0  # 全入力画像を通した累積ページ数

    def process(self, images: list[np.ndarray]) -> list[np.ndarray]:
        results = [evaluate_page(img, self._page_offset + i + 1)
                   for i, img in enumerate(images)]
        self._page_offset += len(images)

        n_ok = sum(1 for r in results if r["ok"])
        total = len(results)

        if n_ok == total:
            # 全ページOK → 簡潔に1行で通知
            logger.info("品質評価: 全 %d ページ OK", total)
        else:
            # 問題ページがある場合のみサマリーテーブルを表示
            logger.info("━━━ 品質評価: %d / %d ページ OK ━━━", n_ok, total)
            logger.info("  %4s  %-8s  %-8s  %-8s  %-8s  %-8s  %s",
                        "Page", "文字見切", "余分領域", "歪み", "半欠け", "下部欠け", "傾き/湾曲")
            logger.info("  %s", "─" * 72)
            sym = lambda b: _red("✗ NG") if b else "○ OK"
            for r in results:
                dist_str = f"{r['skew_angle']:+.1f}°/{r['curve_pct']:.1f}%"
                logger.info(
                    "  %4d  %-8s  %-8s  %-8s  %-8s  %-8s  %s",
                    r["page"],
                    sym(r["text_clipped"]),
                    sym(r["extra_region"]),
                    sym(r["distorted"]),
                    sym(r["half_content"]),
                    sym(r["bottom_cut"]),
                    dist_str,
                )
            for r in results:
                _log_page_result(r)
            logger.warning("品質基準を満たさないページがあります。上記の詳細を確認してください。")

        return images  # 画像は変更しない

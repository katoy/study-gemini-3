"""
image_processor.py
==================
ページ画像の後処理モジュール。
裏写り除去と背景白色化を大幅に強化。
"""

from __future__ import annotations

import cv2
import numpy as np
import logging

from core.config import OUTPUT_SIZES

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 1. 強化された影・裏写り除去 (Document Cleaner)
# ──────────────────────────────────────────────

def remove_shadow(image: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """
    強力なドキュメントクリーン処理。
    紙の色を検出し、裏写りや影を完全に排除して純白にする。
    """
    if strength <= 0:
        return image

    # 1. 輝度チャンネル (L) の抽出
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)

    # 2. 背景（紙の色）の推定
    # かなり大きなカーネルで文字を消し、紙の地の色だけを抽出する
    kernel_size = max(31, int(min(image.shape[:2]) * 0.2) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    
    # 膨張処理で文字を消す
    bg_l = cv2.dilate(l_ch, kernel)
    # medianBlur は ksize ≤ 31 (8bit SIMD 制約)。大きい場合は blur で代替
    blur_k = min(kernel_size, 31) | 1
    if kernel_size <= 31:
        bg_l = cv2.medianBlur(bg_l, blur_k)
    else:
        bg_l = cv2.blur(bg_l, (kernel_size, kernel_size))
    
    # 3. 背景正規化 (Division normalization)
    # 影や色ムラをキャンセルする
    l_float = l_ch.astype(np.float32)
    bg_float = bg_l.astype(np.float32)
    bg_float[bg_float < 1.0] = 1.0
    
    # result = l / bg * 255
    res_l = (l_float / bg_float * 255.0).clip(0, 255).astype(np.uint8)

    # 4. ホワイトバランス・ストレッチ (裏写り除去の核心)
    # 高輝度側（紙の色の周辺）を強制的に白に寄せる
    # OCR等で使われる手法: 背景を 200〜255 の間に圧縮して飛ばす
    res_l = cv2.normalize(res_l, None, 0, 255, cv2.NORM_MINMAX)
    
    # ガンマ補正で中間色の裏写りをさらに飛ばす
    gamma = 1.2 if strength > 0.5 else 1.0
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
    res_l = cv2.LUT(res_l, table)

    # 5. 黒の締め
    # 文字をはっきりさせる
    res_l = cv2.addWeighted(res_l, 1.2, res_l, 0, -20)
    res_l = np.clip(res_l, 0, 255).astype(np.uint8)

    # ブレンド
    final_l = cv2.addWeighted(res_l, strength, l_ch, 1.0 - strength, 0)

    # 再合成
    lab_corrected = cv2.merge([final_l, a_ch, b_ch])
    return cv2.cvtColor(lab_corrected, cv2.COLOR_LAB2BGR)

# ──────────────────────────────────────────────
# 2. 傾き補正 (Deskew)
# ──────────────────────────────────────────────

def deskew_page(image: np.ndarray) -> np.ndarray:
    """
    画像内のテキストの傾きを検出し、水平に回転補正する。

    改良点:
      - ±10° に探索範囲を拡大
      - 横書き・縦書き両方に対応: 水平射影分散と垂直射影分散の大きい方を採用
      - 回転前にキャンバスをパディングして四隅のテキストが欠けないようにする
    """
    h, w = image.shape[:2]
    # 処理高速化のために縮小
    scale = 600 / h
    small = cv2.resize(image, (int(w * scale), 600))
    sh, sw = small.shape[:2]
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    best_score = -1
    best_angle = 0

    # ±10° を 0.25° 刻みで探索（細かくすることで小さな傾きも補正）
    for angle in np.arange(-10, 10.1, 0.25):
        M = cv2.getRotationMatrix2D((sw // 2, sh // 2), angle, 1.0)
        rotated = cv2.warpAffine(thresh, M, (sw, sh), flags=cv2.INTER_NEAREST)

        # 横書き: 水平射影分散（行ごとのピクセル和の分散）
        h_score = float(np.var(np.sum(rotated, axis=1)))
        # 縦書き: 垂直射影分散（列ごとのピクセル和の分散）
        v_score = float(np.var(np.sum(rotated, axis=0)))
        # どちらか大きい方を採用（横書き/縦書き両対応）
        score = max(h_score, v_score)

        if score > best_score:
            best_score = score
            best_angle = angle

    if abs(best_angle) < 0.3:
        return image

    logger.debug("Deskew: angle = %.2f degrees", best_angle)

    # 四隅のコンテンツを失わないよう、対角長以上のパディングを追加してから回転
    diag = int(np.sqrt(w * w + h * h)) + 4
    pad_x = (diag - w) // 2
    pad_y = (diag - h) // 2
    padded = cv2.copyMakeBorder(
        image, pad_y, pad_y, pad_x, pad_x,
        cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )
    ph, pw = padded.shape[:2]
    M = cv2.getRotationMatrix2D((pw // 2, ph // 2), best_angle, 1.0)
    rotated_full = cv2.warpAffine(
        padded, M, (pw, ph),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)
    )
    # パディング分を除いて元サイズに戻す
    return rotated_full[pad_y:pad_y + h, pad_x:pad_x + w]

# ──────────────────────────────────────────────
# 3. 向き補正 (Orientation)
# ──────────────────────────────────────────────

def _is_upside_down(image: np.ndarray) -> bool:
    """
    ページが 180° 逆さまかを検出する。

    3 つのシグナルを組み合わせてスコアリング:
      1. 上下マージン差  : 逆さまなら上マージンが大きくなりやすい
      2. 垂直ストローク方向: 正位置では「黒の上端」遷移が多い
      3. 上下 20% テキスト密度差: フッター (ページ番号のみ) が上に来ると疎になる
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    scale = 600 / h
    small = cv2.resize(gray, (int(w * scale), 600))
    sh = small.shape[0]

    blur = cv2.GaussianBlur(small, (5, 5), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    row_density = binary.mean(axis=1)
    text_thr = row_density.max() * 0.15
    is_text = row_density > text_thr

    if not is_text.any():
        return False

    first_text = int(np.where(is_text)[0][0])
    last_text  = int(np.where(is_text)[0][-1])

    # ── Signal 1: マージン差 ──
    top_margin = first_text / sh
    bot_margin = (sh - 1 - last_text) / sh
    margin_score = top_margin - bot_margin  # 正 → 逆さまの疑い

    # ── Signal 2: 垂直ストローク方向 ──
    b = binary.astype(np.int32)
    diff = b[1:] - b[:-1]
    top_edges = float(np.sum(diff >  50))   # 白→黒 = 文字上端
    bot_edges = float(np.sum(diff < -50))   # 黒→白 = 文字下端
    total_edges = top_edges + bot_edges
    stroke_score = (bot_edges - top_edges) / total_edges if total_edges > 0 else 0.0

    # ── Signal 3: 上下 20% テキスト密度差 ──
    fifth = sh // 5
    top_count = float(is_text[:fifth].sum())
    bot_count = float(is_text[4 * fifth:].sum())
    total_count = top_count + bot_count
    density_score = (bot_count - top_count) / total_count if total_count > 0 else 0.0

    score = margin_score * 0.5 + stroke_score * 0.2 + density_score * 0.3
    logger.debug(
        "_is_upside_down: margin=%.3f stroke=%.3f density=%.3f → score=%.3f",
        margin_score, stroke_score, density_score, score,
    )
    return score > 0.08


def fix_orientation(image: np.ndarray) -> np.ndarray:
    """
    画像の向きを補正する。
      Step 1: landscape (h < w) なら 90° 回転して portrait にする。
    """
    h, w = image.shape[:2]

    # Step 1: 90° 補正
    if h < w:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges_h = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        edges_v = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        if np.abs(edges_h).sum() >= np.abs(edges_v).sum():
            image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

    return image

# ──────────────────────────────────────────────
# 4a. テクスチャ背景除去 (籐・机など)
# ──────────────────────────────────────────────

def remove_textured_border(image: np.ndarray) -> np.ndarray:
    """
    行/列ごとの「白ピクセル比率」でページ領域を特定し、
    籐や机などのテクスチャ背景を上下左右からクロップする。

    識別ロジック:
      - ページ行/列: 白ピクセル (輝度 ≥ 200) が 40% 以上 → ページとして保持
      - 籐/机テクスチャ行/列: 中程度輝度が多く白が 30% 以下 → 背景として除去
    パーセンタイルではなく白比率を使うことで、籐テクスチャのハイライト
    （藤繊維の光沢で 75%ile が高い）による誤検出を防ぐ。
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 白ピクセル比率: 輝度 ≥ 200 のピクセルの割合
    white_thresh = 200
    min_white_ratio = 0.25  # この比率未満の行/列はテクスチャ背景と判定

    row_white = np.mean(gray >= white_thresh, axis=1)
    col_white = np.mean(gray >= white_thresh, axis=0)

    page_rows = row_white >= min_white_ratio
    page_cols = col_white >= min_white_ratio

    if not page_rows.any() or not page_cols.any():
        logger.debug("remove_textured_border: 有効なページ領域が見つからない")
        return image

    r_min = int(np.where(page_rows)[0][0])
    r_max = int(np.where(page_rows)[0][-1])
    c_min = int(np.where(page_cols)[0][0])
    c_max = int(np.where(page_cols)[0][-1])

    # ほぼ削る必要がない場合はそのまま
    if r_min < h * 0.02 and r_max > h * 0.98 and c_min < w * 0.02 and c_max > w * 0.98:
        return image

    # 安全余白を追加してクロップ（テキストを絶対に切らない）
    pad = max(10, int(min(h, w) * 0.01))
    r_min = max(0, r_min - pad)
    r_max = min(h - 1, r_max + pad)
    c_min = max(0, c_min - pad)
    c_max = min(w - 1, c_max + pad)

    # アスペクト比保護: クロップで Portrait→Landscape に転換しない
    # (転換するとfix_orientationが誤方向に回転する原因になる)
    new_h = r_max - r_min + 1
    new_w = c_max - c_min + 1
    original_portrait = h >= w
    if original_portrait and new_w > new_h:
        # 縦が足りなくなった分、上下にパディングを追加して Portrait を維持
        extra = (new_w - new_h + 1) // 2
        r_min = max(0, r_min - extra)
        r_max = min(h - 1, r_max + extra)
        logger.debug(
            "remove_textured_border: portrait guard applied, extra=%d", extra
        )

    logger.debug(
        "remove_textured_border: crop rows %d-%d, cols %d-%d (original %dx%d)",
        r_min, r_max, c_min, c_max, w, h,
    )
    return image[r_min:r_max + 1, c_min:c_max + 1]


# ──────────────────────────────────────────────
# 4. 黒縁除去
# ──────────────────────────────────────────────

def remove_border(image: np.ndarray, threshold: int = 30, padding: int = 2) -> np.ndarray:
    """
    画像の外周にある暗い「黒縁」(撮影時の背景) を除去する。
    
    改良点:
      - ページ全体をクロップするのではなく、外周から中心に向かって
        連続する暗いピクセルのみを削る。
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # マスク作成 (暗い部分を True)
    dark = gray < threshold
    
    # 各辺からどこまで暗いピクセルが続いているかを探す
    top, bottom, left, right = 0, h - 1, 0, w - 1
    
    # 上から
    while top < h // 4 and np.mean(dark[top, :]) > 0.5:
        top += 1
    # 下から
    while bottom > 3 * h // 4 and np.mean(dark[bottom, :]) > 0.5:
        bottom -= 1
    # 左から
    while left < w // 4 and np.mean(dark[:, left]) > 0.5:
        left += 1
    # 右から
    while right > 3 * w // 4 and np.mean(dark[:, right]) > 0.5:
        right -= 1
        
    # 安全のためパディング（戻し）
    top = max(0, top - padding)
    bottom = min(h - 1, bottom + padding)
    left = max(0, left - padding)
    right = min(w - 1, right + padding)
    
    return image[top:bottom+1, left:right+1]

# ──────────────────────────────────────────────
# 5. サイズ正規化
# ──────────────────────────────────────────────

def normalize_size(image: np.ndarray, target_size: str = "A4", grayscale: bool = False) -> np.ndarray:
    """
    画像をターゲットサイズ (A4, B5 等) に合わせ、背景を浄化してページいっぱいに収める。
    画像の縦横比に応じて portrait / landscape を自動判別する。
    """
    size = OUTPUT_SIZES.get(target_size, OUTPUT_SIZES["A4"])
    portrait_w, portrait_h = size  # OUTPUT_SIZES は常に portrait (幅 < 高さ) で定義

    h, w = image.shape[:2]

    # 画像が横長なら landscape A4 を使用
    if w > h:
        target_w, target_h = portrait_h, portrait_w  # 幅と高さを入れ替え
    else:
        target_w, target_h = portrait_w, portrait_h
    
    # 1. 適応的背景浄化 (Document Cleaning)
    # 画像の明るい部分（上位 10%）の中央値をホワイトポイントとする
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    white_point = np.percentile(gray, 90)
    
    # ホワイトポイントを 255 に、0 はそのままに引き伸ばす
    # 200〜240程度のグレー背景を白く飛ばす
    if white_point > 150:
        image_f = image.astype(np.float32)
        image_f = (image_f * (255.0 / white_point))
        image = np.clip(image_f, 0, 255).astype(np.uint8)

    # 2. サイズ調整と配置
    # マージン 0% (ページいっぱいに配置)
    margin_x = 0
    margin_y = 0
    inner_w = target_w
    inner_h = target_h
    
    scale = min(inner_w / w, inner_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    
    # 白背景のキャンバス作成
    canvas = np.full((target_h, target_w, 3), 255, dtype=np.uint8)
    
    # 中央配置
    y_off = (target_h - new_h) // 2
    x_off = (target_w - new_w) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    
    if grayscale:
        gray_out = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        canvas = cv2.cvtColor(gray_out, cv2.COLOR_GRAY2BGR)
        
    return canvas

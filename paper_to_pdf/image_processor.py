"""
image_processor.py
==================
ページ画像の後処理モジュール。
裏写り除去と背景白色化を大幅に強化。
"""

from __future__ import annotations

import cv2
import numpy as np

from core.config import OUTPUT_SIZES

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
    画像内のテキストの傾きを検出し、水平に回転補正する（強化版）。
    
    アルゴリズム:
      -10度〜+10度の範囲で画像を回転させ、水平方向の射影分布の「分散」が
      最大になる角度（＝文字行が最も水平に重なる角度）を特定する。
    """
    h, w = image.shape[:2]
    # 処理高速化のために縮小
    scale = 600 / h
    small = cv2.resize(image, (int(w * scale), 600))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    
    # ノイズ除去とコントラスト強調
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    best_score = -1
    best_angle = 0
    
    # -5度から+5度の範囲を 0.5度刻みで探索
    for angle in np.arange(-5, 5.1, 0.5):
        # 中心で回転
        M = cv2.getRotationMatrix2D((small.shape[1] // 2, 300), angle, 1.0)
        rotated = cv2.warpAffine(thresh, M, (small.shape[1], 600), flags=cv2.INTER_NEAREST)
        
        # 水平方向の投影（行ごとのピクセル和）
        hist = np.sum(rotated, axis=1)
        
        # 文字が水平なら、hist の「差」が激しくなる（分散が大きくなる）
        score = np.var(hist)
        
        if score > best_score:
            best_score = score
            best_angle = angle
            
    if abs(best_angle) < 0.1:
        return image
        
    logger.debug(f"Deskew: Optimized angle = {best_angle:.2f} degrees")
    
    # 元の画像に最適な回転を適用
    M = cv2.getRotationMatrix2D((w // 2, h // 2), best_angle, 1.0)
    return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LANCZOS4, 
                         borderMode=cv2.BORDER_REPLICATE)

# ──────────────────────────────────────────────
# 3. 向き補正 (Orientation)
# ──────────────────────────────────────────────

def fix_orientation(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    if h >= w:
        return image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges_h = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    edges_v = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    if np.abs(edges_h).sum() >= np.abs(edges_v).sum():
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

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
    画像をターゲットサイズ (A4, B5 等) に合わせ、ページいっぱいに表示されるよう拡大・配置する。
    """
    size = OUTPUT_SIZES.get(target_size, OUTPUT_SIZES["A4"])
    target_w, target_h = size
    
    # 向きを縦長に統一 (必要なら)
    if image.shape[1] > image.shape[0]:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        
    h, w = image.shape[:2]
    
    # マージンを最小限（0.5%）にする
    margin_x = int(target_w * 0.005)
    margin_y = int(target_h * 0.005)
    inner_w = target_w - (margin_x * 2)
    inner_h = target_h - (margin_y * 2)
    
    # アスペクト比を維持して最大限にリサイズ
    scale = min(inner_w / w, inner_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    
    # --- 背景の純白化 (Normalization) ---
    # 端の影を飛ばして PDF の白に溶け込ませる
    if grayscale:
        gray_res = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray_res[gray_res > 248] = 255
        resized = cv2.cvtColor(gray_res, cv2.COLOR_GRAY2BGR)
    else:
        lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l[l > 248] = 255
        resized = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    
    # 白背景のキャンバス作成
    canvas = np.full((target_h, target_w, 3), 255, dtype=np.uint8)
    
    # 中央配置 (マージンが最小なので、ほぼページいっぱいになる)
    y_off = (target_h - new_h) // 2
    x_off = (target_w - new_w) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    
    return canvas

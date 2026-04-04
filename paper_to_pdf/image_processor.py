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
    画像内のテキスト行の傾きを検出し、水平に回転補正する。
    """
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # エッジ抽出
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    
    # ハフ変換で直線（行）を検出
    # 解像度 1度単位で -10度 〜 +10度の範囲を探す
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, 
                            minLineLength=w // 5, maxLineGap=20)
    
    if lines is None:
        return image
        
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # 極端な傾き（縦書きの縦線など）を除外、±15度以内を対象
        if abs(angle) < 15:
            angles.append(angle)
            
    if not angles:
        return image
        
    # 最頻値（中央値）の角度を採用
    median_angle = np.median(angles)
    
    if abs(median_angle) < 0.1: # 傾きが微小なら何もしない
        return image
        
    # 回転行列の作成
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    
    # 回転（余白は白で埋める）
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LANCZOS4, 
                             borderMode=cv2.BORDER_REPLICATE)
    
    return rotated

# ──────────────────────────────────────────────
# 3. 黒縁除去
# ──────────────────────────────────────────────

def fix_orientation(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    if h >= w: return image
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges_h = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    edges_v = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    if np.abs(edges_h).sum() >= np.abs(edges_v).sum():
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    else:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

# ──────────────────────────────────────────────
# 4. 黒縁除去
# ──────────────────────────────────────────────

def remove_border(image: np.ndarray, threshold: int = 40, padding: int = 5) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    rows = np.any(mask > 0, axis=1)
    cols = np.any(mask > 0, axis=0)
    if not rows.any() or not cols.any(): return image
    r_min, r_max = np.where(rows)[0][[0, -1]]
    c_min, c_max = np.where(cols)[0][[0, -1]]
    h, w = image.shape[:2]
    return image[max(0, r_min-padding):min(h, r_max+padding), max(0, c_min-padding):min(w, c_max+padding)]

# ──────────────────────────────────────────────
# 5. サイズ正規化
# ──────────────────────────────────────────────

def normalize_size(image: np.ndarray, target_size: str = "A4", grayscale: bool = False) -> np.ndarray:
    size = OUTPUT_SIZES.get(target_size, OUTPUT_SIZES["A4"])
    target_w, target_h = size
    if image.shape[1] > image.shape[0]:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    h, w = image.shape[:2]
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((target_h, target_w, 3), 255, dtype=np.uint8)
    y_off, x_off = (target_h - new_h) // 2, (target_w - new_w) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    if grayscale:
        canvas = cv2.cvtColor(cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    return canvas

import cv2
import numpy as np

def order_points(pts: np.ndarray) -> np.ndarray:
    sorted_by_y = pts[np.argsort(pts[:, 1])]
    top = sorted_by_y[:2]
    bot = sorted_by_y[2:]
    tl = top[np.argmin(top[:, 0])]
    tr = top[np.argmax(top[:, 0])]
    bl = bot[np.argmin(bot[:, 0])]
    br = bot[np.argmax(bot[:, 0])]
    return np.array([tl, tr, br, bl], dtype="float32")

def _detect_by_white_profile(small: np.ndarray, scale: float):
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    row_white = np.mean(gray >= 190, axis=1)
    col_white = np.mean(gray >= 190, axis=0)
    _WHITE_THRESH = 0.25
    page_rows = np.where(row_white >= _WHITE_THRESH)[0]
    page_cols = np.where(col_white >= _WHITE_THRESH)[0]
    if len(page_rows) < h * 0.2 or len(page_cols) < w * 0.2:
        return None
    r_min, r_max = int(page_rows.min()), int(page_rows.max())
    c_min, c_max = int(page_cols.min()), int(page_cols.max())
    pts = np.array([
        [c_min / scale, r_min / scale],
        [c_max / scale, r_min / scale],
        [c_max / scale, r_max / scale],
        [c_min / scale, r_max / scale],
    ], dtype="float32")
    return pts

img = cv2.imread("samples_h/0002.png")
h, w = img.shape[:2]
scale = 600 / h
small = cv2.resize(img, (int(w * scale), 600))
pts = _detect_by_white_profile(small, scale)
print("Original pts:\n", pts)
ordered = order_points(pts)
print("Ordered pts:\n", ordered)

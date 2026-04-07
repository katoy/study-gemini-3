import cv2
import numpy as np

img = cv2.imread("samples_h/0001.png")
h, w = img.shape[:2]
scale = 600 / h
small = cv2.resize(img, (int(w * scale), 600))
gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

row_white = np.mean(gray >= 190, axis=1)
edge_band = max(w // 10, 5)
rw_left  = np.mean(gray[:, 0:edge_band] >= 190, axis=1)
rw_right = np.mean(gray[:, w - edge_band:w] >= 190, axis=1)

def _scan_boundary_bot(rw):
    for i in range(small.shape[0] - 1, -1, -1):
        if rw[i] >= 0.25:
            return i
    return small.shape[0] - 1

r_bl_raw = _scan_boundary_bot(rw_left)
r_br_raw = _scan_boundary_bot(rw_right)
print(f"r_bl_raw = {r_bl_raw}, r_br_raw = {r_br_raw}")

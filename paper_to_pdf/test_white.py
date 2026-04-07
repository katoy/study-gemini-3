import cv2
import numpy as np

img = cv2.imread("samples_h/0001.png")
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
h, w = gray.shape
row_white = np.mean(gray >= 190, axis=1)
page_rows = np.where(row_white >= 0.25)[0]
print(f"h={h}, w={w}")
if len(page_rows) > 0:
    print(f"page_rows: min={page_rows.min()}, max={page_rows.max()}, len={len(page_rows)}")
else:
    print("No page rows >= 0.25")

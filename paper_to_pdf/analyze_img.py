
import cv2
import numpy as np

def analyze_spread(path):
    img = cv2.imread(path)
    if img is None:
        print("Failed to load")
        return
    h, w = img.shape[:2]
    print(f"Original size: {w}x{h}")
    
    # Simulate DetectionStep rotation
    if h > w:
        img = np.ascontiguousarray(np.rot90(img, k=-1))
        h, w = img.shape[:2]
        print(f"Rotated size: {w}x{h}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Check text density in 10 sections
    for i in range(10):
        start = w * i // 10
        end = w * (i + 1) // 10
        density = np.count_nonzero(bw[:, start:end]) / (h * (end - start))
        print(f"Section {i} ({(i*10)}%-{(i+1)*10}%): {density:.4f}")

    # Vertical projection (sum of rows) to find if it's rotated correctly
    row_density = bw.sum(axis=1)
    # Horizontal projection (sum of columns) to find the valley
    col_density = bw.sum(axis=0)
    
    # Find valley in center 40%
    s, e = w * 3 // 10, w * 7 // 10
    subset = col_density[s:e]
    # Smooth subset
    k = max(21, (e-s)//10) | 1
    smoothed = cv2.GaussianBlur(subset.reshape(1, -1), (k, 1), 0).flatten()
    best_rel = np.argmin(smoothed)
    best_abs = s + best_rel
    print(f"Best valley at {best_abs} ({best_abs/w*100:.1f}%) with smoothed density {smoothed[best_rel]}")

analyze_spread('samples/0001.png')

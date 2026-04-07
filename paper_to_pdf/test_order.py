import numpy as np

def order_points(pts):
    sorted_by_y = pts[np.argsort(pts[:, 1])]
    top = sorted_by_y[:2]
    bot = sorted_by_y[2:]
    tl = top[np.argmin(top[:, 0])]
    tr = top[np.argmax(top[:, 0])]
    bl = bot[np.argmin(bot[:, 0])]
    br = bot[np.argmax(bot[:, 0])]
    return np.array([tl, tr, br, bl], dtype="float32")

# Slightly rotated rectangle
pts = np.array([
    [10, 0],   # Top
    [20, 10],  # Right
    [10, 20],  # Bottom
    [0, 10]    # Left
])
print("Original:\n", pts)
print("Ordered:\n", order_points(pts))

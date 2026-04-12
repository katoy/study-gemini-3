"""
共有フィクスチャ定義。
"""
import sys
import os

# paper_to_pdf をルートとして import できるようにする
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
import cv2


# ── ビジュアル回帰テスト用 ────────────────────────────────────────────

@pytest.fixture(scope="session")
def visual_regression_results():
    """ビジュアル回帰テストの全結果を session スコープで共有するリスト。"""
    return []


# ── 基本画像フィクスチャ ──────────────────────────────────────────────

@pytest.fixture
def white_image():
    """白一色の 200×300 BGR 画像 (portrait)。"""
    return np.full((300, 200, 3), 255, dtype=np.uint8)


@pytest.fixture
def black_image():
    """黒一色の 200×300 BGR 画像。"""
    return np.zeros((300, 200, 3), dtype=np.uint8)


@pytest.fixture
def text_image():
    """白背景に黒テキストを描いた 400×600 BGR 画像。"""
    img = np.full((600, 400, 3), 255, dtype=np.uint8)
    for y in range(50, 550, 30):
        cv2.line(img, (30, y), (370, y), (0, 0, 0), 2)
    return img


@pytest.fixture
def spread_image():
    """見開き風の横長 400×800 BGR 画像（両ページにテキスト行）。"""
    img = np.full((400, 800, 3), 255, dtype=np.uint8)
    for y in range(40, 380, 28):
        cv2.line(img, (20, y), (380, y), (10, 10, 10), 2)   # 左ページ
        cv2.line(img, (420, y), (780, y), (10, 10, 10), 2)  # 右ページ
    return img

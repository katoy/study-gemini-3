"""
utils/paths.py
==============
アプリケーション共通のパス定数。
"""

from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "paper_to_pdf"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

"""Shared tkinter imports for GUI modules."""

from typing import Any

tk: Any
tkfont: Any
messagebox: Any
ttk: Any

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox, ttk
except ImportError:
    tk = None
    tkfont = None
    messagebox = None
    ttk = None

"""Shared tkinter imports for GUI modules."""

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import messagebox
    from tkinter import ttk
except ImportError:
    tk = None
    tkfont = None
    messagebox = None
    ttk = None

"""
core/config.py
==============
アプリケーション全体の設定を管理する。
"""

from __future__ import annotations
from dataclasses import dataclass

# 出力用紙サイズ (幅 x 高さ, 単位: px @ 300 dpi)
OUTPUT_SIZES: dict[str, tuple[int, int]] = {
    "A4":     (2480, 3508),
    "A5":     (1748, 2480),
    "B5":     (2079, 2953),
    "Letter": (2550, 3300),
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".heic", ".bmp", ".tiff", ".tif"}
)

_VALID_BOOK_TYPES  = {"jp_vert", "jp_horiz", "en", "manga", "auto"}
_VALID_DEWARP_MODES = {"dewarpnet", "polynomial", "doctr", "none"}
_VALID_SENSITIVITIES = {"low", "medium", "high"}
_VALID_AI_BACKENDS  = {"realesrgan", "swin2sr", "docres"}
_VALID_AI_SCALES    = {1, 2, 4}
_VALID_ROTATE_ANGLES = {0, 90, 180, 270}
_VALID_WRITING_MODES = {"auto", "horizontal", "vertical"}


@dataclass
class ProcessingConfig:
    """処理設定を保持するデータクラス"""
    book_type: str = "auto"
    dewarp_mode: str = "dewarpnet"
    split: bool = True
    orient: bool = True
    border: bool = True
    output_size: str = "A4"
    sensitivity: str = "medium"
    grayscale: bool = False
    shadow_strength: float = 1.0
    dpi: int = 300
    # 書字方向・回転
    rotate_angle: int = 0            # 手動回転指定 (0, 90, 180, 270)
    writing_mode: str = "auto"       # "auto" | "horizontal" | "vertical"
    # AI 画像補正
    ai_enhance: bool = False
    ai_backend: str = "realesrgan"   # "realesrgan" | "swin2sr" | "docres"
    ai_scale: int = 2                # 1 の場合は解像度変更なしで補正のみ
    # 検出確認モード
    show_book_area: bool = False   # 分割なしで書籍領域を赤枠描画して PDF 出力 (後処理スキップ)
    show_page_area: bool = False   # 分割あり でページ領域を赤枠描画して PDF 出力 (後処理スキップ)

    def __post_init__(self) -> None:
        """フィールド値のバリデーション"""
        if self.book_type not in _VALID_BOOK_TYPES:
            raise ValueError(f"book_type は {_VALID_BOOK_TYPES} のいずれかを指定してください: {self.book_type!r}")
        if self.dewarp_mode not in _VALID_DEWARP_MODES:
            raise ValueError(f"dewarp_mode は {_VALID_DEWARP_MODES} のいずれかを指定してください: {self.dewarp_mode!r}")
        if self.sensitivity not in _VALID_SENSITIVITIES:
            raise ValueError(f"sensitivity は {_VALID_SENSITIVITIES} のいずれかを指定してください: {self.sensitivity!r}")
        if self.output_size not in OUTPUT_SIZES:
            raise ValueError(f"output_size は {set(OUTPUT_SIZES)} のいずれかを指定してください: {self.output_size!r}")
        if self.ai_backend not in _VALID_AI_BACKENDS:
            raise ValueError(f"ai_backend は {_VALID_AI_BACKENDS} のいずれかを指定してください: {self.ai_backend!r}")
        if self.ai_scale not in _VALID_AI_SCALES:
            raise ValueError(f"ai_scale は {_VALID_AI_SCALES} のいずれかを指定してください: {self.ai_scale!r}")
        if self.rotate_angle not in _VALID_ROTATE_ANGLES:
            raise ValueError(f"rotate_angle は {_VALID_ROTATE_ANGLES} のいずれかを指定してください: {self.rotate_angle!r}")
        if self.writing_mode not in _VALID_WRITING_MODES:
            raise ValueError(f"writing_mode は {_VALID_WRITING_MODES} のいずれかを指定してください: {self.writing_mode!r}")
        if not (0.0 <= self.shadow_strength <= 1.0):
            raise ValueError(f"shadow_strength は 0.0〜1.0 の範囲で指定してください: {self.shadow_strength!r}")

    @property
    def page_order(self) -> str:
        """書字方向設定に基づくページ順序 (分割時)。"""
        if self.writing_mode == "vertical":
            return "right_first"
        if self.writing_mode == "horizontal":
            return "left_first"
        
        # writing_mode == "auto" の場合は、book_type も参考にする
        if self.book_type in ("jp_vert", "manga"):
            return "right_first"
        if self.book_type == "auto":
            return "auto"
        return "left_first"

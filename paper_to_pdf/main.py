"""
main.py
=======
書籍スキャン → PDF 変換アプリ (CLI エントリポイント)
"""

import argparse
import sys
import logging
from pathlib import Path

import cv2
import numpy as np

from processor import BookProcessor
from core.config import ProcessingConfig
from steps.quality_check import evaluate_page

def setup_logging(verbose: bool = False, quiet: bool = False):
    """ロギングの設定を行う"""
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )

def parse_args():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(description="書籍スキャン画像を PDF に変換する高度な CLI ツール")
    
    # 必須引数
    parser.add_argument("input", type=Path, help="入力フォルダパス")
    parser.add_argument("output", type=Path, help="出力 PDF パス")
    
    # オプション
    parser.add_argument("--book-type", choices=["auto", "jp_vert", "jp_horiz", "en", "manga"],
                        default="auto", help="書籍タイプ (default: auto — 縦書き/横書きを自動検出)")
    parser.add_argument("--dewarp-mode", choices=["dewarpnet", "polynomial", "doctr", "none"], 
                        default="dewarpnet", help="湾曲補正モード (default: dewarpnet, doctr: AI Transformer)")
    parser.add_argument("--no-orient", action="store_false", dest="orient", help="向きを自動補正しない")
    parser.add_argument("--no-border", action="store_false", dest="border", help="黒縁を除去しない")
    parser.add_argument("--output-size", default="A4", help="出力サイズ A4/A5/B5/Letter (default: A4)")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high"], default="medium", 
                        help="境界検出感度")
    parser.add_argument("--grayscale", action="store_true", help="グレースケールで出力")
    parser.add_argument("--shadow-strength", type=float, default=1.0, help="影・裏写り除去強度 0-1.0 (default: 1.0)")
    parser.add_argument("--rotate-angle", type=int, choices=[0, 90, 180, 270], default=0,
                        help="手動回転指定 (0, 90, 180, 270)")
    parser.add_argument("--writing-mode", choices=["auto", "horizontal", "vertical"], default="auto",
                        help="書字方向 (horizontal: 横書き/左開き, vertical: 縦書き/右開き)")
    parser.add_argument("--ai-enhance", action="store_true",
                        help="オープンソース AI モデルで超解像・復元補正を行う")
    parser.add_argument("--ai-backend", choices=["realesrgan", "swin2sr", "docres"], default="realesrgan",
                        help="AI 補正バックエンド (docres: AI による影・裏写り除去)")
    parser.add_argument("--ai-scale", type=int, choices=[1, 2, 4], default=2,
                        help="超解像の拡大倍率 (1: 復元のみ, default: 2)")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログを出力")
    parser.add_argument("--quiet", "-q", action="store_true", help="WARNING 以上のみ出力（INFO を抑制）")
    parser.add_argument("--show-book-area", action="store_true",
                        help="書籍領域を赤枠描画した PDF を出力する（分割なし・後処理スキップ）")
    parser.add_argument("--show-page-area", action="store_true",
                        help="ページ領域を赤枠描画した PDF を出力する（見開き分割あり・後処理スキップ）")
    parser.add_argument("--diagnose", action="store_true",
                        help="品質チェック結果を標準出力にサマリー表示する（処理後に判定結果を表示）")

    return parser.parse_args()

def _run_diagnosis(pdf_path: Path) -> None:
    """出力 PDF を読み込んで品質評価を実施し、標準出力に表示する。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("[diagnose] PyMuPDF (fitz) が必要です: pip install pymupdf", file=sys.stderr)
        return

    doc = fitz.open(str(pdf_path))
    results = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
        pix = None  # Pixmapを明示的に解放してメモリを節約
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif img.shape[2] == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        else:
            raise ValueError(f"Unsupported channel count: {img.shape[2]}")
        results.append(evaluate_page(img, i + 1))
    doc.close()
    _print_quality_summary(results)


def _print_quality_summary(results: list) -> None:
    """品質チェック結果を標準出力に表示する。"""
    print("\n" + "=" * 70)
    print("品質診断サマリー")
    print("=" * 70)
    RED = "\033[31m"
    RST = "\033[0m"
    sym = lambda b: f"{RED}✗ NG{RST}" if b else "○ OK"
    header = f"  {'Page':>4}  {'白比率':>5}  {'文字見切':8}  {'余分領域':8}  {'歪み':8}  {'半欠け':8}  {'下部欠け':8}  傾き°"
    print(header)
    print("  " + "-" * 78)
    ng_pages = []
    for r in results:
        line = (
            f"  {r['page']:>4}  {r['white_ratio']*100:>5.1f}%  {sym(r['text_clipped']):8}  {sym(r['extra_region']):8}  "
            f"{sym(r['distorted']):8}  {sym(r['half_content']):8}  {sym(r['bottom_cut']):8}  "
            f"{r['skew_angle']:+.1f}"
        )
        print(line)
        if r["extra_region"]:
            # 背景が残っている場合、上下左右の詳細を表示
            d = r["extra_detail"]
            detail = f"    └ 余分領域詳細 (白比率): Top:{d['top']:.2f}, Bot:{d['bottom']:.2f}, Left:{d['left']:.2f}, Right:{d['right']:.2f}"
            print(detail)
        
        if not r["ok"]:
            ng_pages.append(r["page"])
    print()
    if ng_pages:
        print(f"[WARNING] 要確認ページ: {ng_pages}")
    else:
        print("[OK] 全ページ品質基準クリア")
    print("=" * 70)


def main():
    args = parse_args()
    setup_logging(args.verbose, args.quiet)
    
    # 設定の構築
    # 書籍タイプごとのデフォルト値を適用
    grayscale = args.grayscale or (args.book_type == "manga")
    
    config = ProcessingConfig(
        book_type=args.book_type,
        dewarp_mode=args.dewarp_mode,
        orient=args.orient,
        border=args.border,
        output_size=args.output_size,
        sensitivity=args.sensitivity,
        grayscale=grayscale,
        shadow_strength=args.shadow_strength,
        rotate_angle=args.rotate_angle,
        writing_mode=args.writing_mode,
        ai_enhance=args.ai_enhance,
        ai_backend=args.ai_backend,
        ai_scale=args.ai_scale,
        show_book_area=args.show_book_area,
        show_page_area=args.show_page_area,
    )

    # 入力フォルダの存在チェック
    if not args.input.exists():
        print(f"エラー: 入力フォルダが見つかりません: {args.input}", file=sys.stderr)
        sys.exit(1)
    if not args.input.is_dir():
        print(f"エラー: 入力パスはフォルダを指定してください: {args.input}", file=sys.stderr)
        sys.exit(1)

    # プロセッサの実行
    processor = BookProcessor(config)

    try:
        if args.quiet:
            _progress_cb = None
        else:
            def _progress_cb(pct, msg):
                sys.stdout.write(f"\r[{pct*100:3.0f}%] {msg[:60]:<60}")
                sys.stdout.flush()

        processor.run(args.input, args.output, progress_cb=_progress_cb)
        if not args.quiet:
            print("\n\n処理が正常に完了しました！")

        if getattr(args, 'diagnose', False):
            _run_diagnosis(args.output)

    except Exception as e:
        logging.exception("Fatal error during processing")
        sys.exit(1)

if __name__ == "__main__":
    main()

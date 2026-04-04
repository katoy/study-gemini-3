"""
main.py
=======
書籍スキャン → PDF 変換アプリ (CLI エントリポイント)
"""

import argparse
import sys
import logging
from pathlib import Path

from processor import BookProcessor
from core.config import ProcessingConfig

def setup_logging(verbose: bool = False):
    """ロギングの設定を行う"""
    level = logging.DEBUG if verbose else logging.INFO
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
    parser.add_argument("--book-type", choices=["jp_vert", "jp_horiz", "en", "manga"], 
                        default="jp_vert", help="書籍タイプ (default: jp_vert)")
    parser.add_argument("--dewarp-mode", choices=["dewarpnet", "polynomial", "doctr", "none"], 
                        default="dewarpnet", help="湾曲補正モード (default: dewarpnet, doctr: AI Transformer)")
    parser.add_argument("--no-split", action="store_false", dest="split", help="見開き画像を分割しない")
    parser.add_argument("--no-orient", action="store_false", dest="orient", help="向きを自動補正しない")
    parser.add_argument("--no-border", action="store_false", dest="border", help="黒縁を除去しない")
    parser.add_argument("--output-size", default="A4", help="出力サイズ A4/A5/B5/Letter (default: A4)")
    parser.add_argument("--sensitivity", choices=["low", "medium", "high", "ai"], default="medium", 
                        help="境界検出感度 (ai: AI によるコーナー検出)")
    parser.add_argument("--grayscale", action="store_true", help="グレースケールで出力")
    parser.add_argument("--shadow-strength", type=float, default=1.0, help="影・裏写り除去強度 0-1.0 (default: 1.0)")
    parser.add_argument("--ai-enhance", action="store_true",
                        help="オープンソース AI モデルで超解像・復元補正を行う")
    parser.add_argument("--ai-backend", choices=["realesrgan", "swin2sr", "docres"], default="realesrgan",
                        help="AI 補正バックエンド (docres: AI による影・裏写り除去)")
    parser.add_argument("--ai-scale", type=int, choices=[1, 2, 4], default=2,
                        help="超解像の拡大倍率 (1: 復元のみ, default: 2)")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログを出力")
    
    return parser.parse_args()

def main():
    args = parse_args()
    setup_logging(args.verbose)
    
    # 設定の構築
    # 書籍タイプごとのデフォルト値を適用
    grayscale = args.grayscale or (args.book_type == "manga")
    
    config = ProcessingConfig(
        book_type=args.book_type,
        dewarp_mode=args.dewarp_mode,
        split=args.split,
        orient=args.orient,
        border=args.border,
        output_size=args.output_size,
        sensitivity=args.sensitivity,
        grayscale=grayscale,
        shadow_strength=args.shadow_strength,
        ai_enhance=args.ai_enhance,
        ai_backend=args.ai_backend,
        ai_scale=args.ai_scale,
    )
    
    # プロセッサの実行
    processor = BookProcessor(config)
    
    try:
        def progress_cb(pct, msg):
            sys.stdout.write(f"\r[{pct*100:3.0f}%] {msg[:60]:<60}")
            sys.stdout.flush()

        processor.run(args.input, args.output, progress_cb=progress_cb)
        print("\n\n処理が正常に完了しました！")
        
    except Exception as e:
        logging.exception("Fatal error during processing")
        sys.exit(1)

if __name__ == "__main__":
    main()

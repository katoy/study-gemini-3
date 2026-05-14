
import sys
import argparse
from pathlib import Path
import ocrmypdf

def run_ocr(input_path: Path, output_path: Path, language: str = "jpn+eng", skip_text: bool = True, verbose: bool = False):
    """
    PDF に対して OCR を実行し、検索可能なテキストレイヤーを追加します。
    
    Args:
        input_path: 入力 PDF パス
        output_path: 出力 PDF パス
        language: OCR 言語 (default: jpn+eng)
        skip_text: 既にテキストがあるページをスキップするか (default: True)
        verbose: 詳細ログを出力するか
    """
    print(f"OCR 開始: {input_path} -> {output_path} (Lang: {language})")
    
    try:
        ocrmypdf.ocr(
            input_path,
            output_path,
            language=language,
            skip_text=skip_text,      # 既にテキストがある場合はスキップ
            deskew=True,              # 傾き補正
            clean=True,               # ノイズ除去
            rotate_pages=True,        # ページの向きを自動修正
            jobs=4,                   # 並列ジョブ数
            verbose=verbose,          # 詳細ログ
            optimize=1,               # PDF 最適化 (0-3)
            # Tesseract への追加オプション (必要に応じて調整)
            # tesseract_pagesegmode=3, # ページ分割モード (3: デフォルト, 6: 単一ブロック, etc)
        )
        print(f"OCR 完了: {output_path}")
    except Exception as e:
        print(f"OCR 実行中にエラーが発生しました: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="PDF に OCR テキストレイヤーを追加するツール")
    parser.add_argument("input", type=Path, help="入力 PDF パス")
    parser.add_argument("output", type=Path, help="出力 PDF パス")
    parser.add_argument("--lang", default="jpn+eng", help="OCR 言語 (default: jpn+eng)")
    parser.add_argument("--force", action="store_true", help="既存のテキストがあっても強制的に OCR する")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログを出力")
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"エラー: 入力ファイルが見つかりません: {args.input}", file=sys.stderr)
        sys.exit(1)
        
    run_ocr(args.input, args.output, language=args.lang, skip_text=not args.force, verbose=args.verbose)

if __name__ == "__main__":
    main()

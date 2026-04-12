import sys
import argparse
from pathlib import Path
import pypdfium2 as pdfium
from ocrmac import ocrmac
from PIL import Image

def extract_text_from_pdf(pdf_path: Path, output_md: Path, languages: list = None, auto_rotate: bool = True):
    """
    PDF の各ページをレンダリングし、ocrmac (Apple Vision) を使用してテキストを抽出します。
    
    Args:
        pdf_path: 入力 PDF パス
        output_md: 出力 Markdown パス
        languages: OCR 言語の優先順位 (default: ['ja-JP', 'en-US'])
        auto_rotate: 0, 90, 180, 270 度のうち、最も単語数が多い向きを自動選択する。
    """
    if languages is None:
        languages = ['ja-JP', 'en-US']
        
    if not pdf_path.exists():
        print(f"エラー: 入力ファイルが見つかりません: {pdf_path}", file=sys.stderr)
        return False

    output_md.parent.mkdir(parents=True, exist_ok=True)

    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        all_text = []
        
        print(f"OCR 抽出開始 (全 {len(pdf)} ページ, 自動回転: {auto_rotate}): {pdf_path}")
        
        for i in range(len(pdf)):
            page = pdf[i]
            # 高解像度でレンダリング
            bitmap = page.render(scale=300/72) 
            pil_image = bitmap.to_pil()
            
            best_annotations = []
            best_angle = 0
            
            if auto_rotate:
                # 0, 90, 180, 270 度をテストして最も単語数が多いものを採用
                # (反時計回り)
                max_words = -1
                for angle in [0, 90, 180, 270]:
                    test_img = pil_image.rotate(angle, expand=True) if angle != 0 else pil_image
                    annotations = ocrmac.OCR(test_img, language_preference=languages).recognize()
                    word_count = len(annotations)
                    if word_count > max_words:
                        max_words = word_count
                        best_annotations = annotations
                        best_angle = angle
                print(f"  {i+1} / {len(pdf)} ページ完了 (採用角度: {best_angle}度, 検出単語数: {max_words})")
            else:
                best_annotations = ocrmac.OCR(pil_image, language_preference=languages).recognize()
                print(f"  {i+1} / {len(pdf)} ページ完了 (検出単語数: {len(best_annotations)})")
            
            # 認識結果をテキストに統合
            page_text = " ".join([ann[0] for ann in best_annotations])
            all_text.append(f"## Page {i+1}\n\n{page_text}\n")
            
        with open(output_md, "w", encoding="utf-8") as f:
            f.write("\n\n".join(all_text))
        
        print(f"Markdown 保存完了: {output_md}")
        return True

    except Exception as e:
        print(f"エラーが発生しました: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description="PDF から ocrmac (Apple Vision) を使用してテキストを抽出し Markdown に保存するツール")
    parser.add_argument("input", type=Path, help="入力 PDF パス")
    parser.add_argument("output", type=Path, help="出力 Markdown パス")
    parser.add_argument("--lang", nargs="+", default=['ja-JP', 'en-US'], help="OCR 言語の優先順位 (default: ja-JP en-US)")
    parser.add_argument("--no-auto-rotate", action="store_false", dest="auto_rotate", help="自動回転補正を行わない")
    
    args = parser.parse_args()
    
    success = extract_text_from_pdf(args.input, args.output, languages=args.lang, auto_rotate=args.auto_rotate)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()

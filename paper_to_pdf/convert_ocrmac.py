import pypdfium2 as pdfium
from ocrmac import ocrmac
from pathlib import Path

def convert_pdf_to_markdown_with_ocrmac(pdf_path: str, output_md: str):
    pdf = pdfium.PdfDocument(pdf_path)
    all_text = []
    
    print(f"PDF 変換中 (全 {len(pdf)} ページ): {pdf_path}")
    
    for i in range(len(pdf)):
        page = pdf[i]
        # ページを画像にレンダリング (高解像度 300dpi 相当)
        bitmap = page.render(scale=300/72) 
        pil_image = bitmap.to_pil()
        
        # 保存せずに一時的な PIL 画像から OCR 実行
        # ocrmac はファイルパスまたは PIL 画像を受け取る
        annotations = ocrmac.OCR(pil_image, language_preference=['ja-JP', 'en-US']).recognize()
        
        # 認識結果をテキストに統合
        page_text = " ".join([ann[0] for ann in annotations])
        all_text.append(f"## Page {i+1}\n\n{page_text}\n")
        print(f"  {i+1} ページ完了")
        
    with open(output_md, "w", encoding="utf-8") as f:
        f.write("\n\n".join(all_text))
    
    print(f"変換完了: {output_md}")

if __name__ == "__main__":
    convert_pdf_to_markdown_with_ocrmac("out.pdf", "out_ocrmac.md")

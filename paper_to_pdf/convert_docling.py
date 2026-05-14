from docling.document_converter import DocumentConverter
from pathlib import Path

def convert_with_docling(input_pdf: str, output_md: str):
    converter = DocumentConverter()
    result = converter.convert(input_pdf)
    
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(result.document.export_to_markdown())
    
    print(f"Docling 変換完了: {output_md}")

if __name__ == "__main__":
    convert_with_docling("out.pdf", "out_docling.md")

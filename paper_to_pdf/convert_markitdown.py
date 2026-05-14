from markitdown import MarkItDown
from pathlib import Path

def convert_with_markitdown(input_pdf: str, output_md: str):
    markitdown = MarkItDown()
    result = markitdown.convert(input_pdf)
    
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(result.text_content)
    
    print(f"変換完了: {output_md}")

if __name__ == "__main__":
    convert_with_markitdown("out_ocr.pdf", "out.md")

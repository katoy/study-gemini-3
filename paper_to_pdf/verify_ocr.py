
import opendataloader_pdf
from pathlib import Path

input_file = "samples_v/0001.png"
output_dir = "test_output"

print(f"Processing {input_file}...")

try:
    # OCR 実行
    opendataloader_pdf.convert(
        input_path=input_file,
        output_dir=output_dir,
        format="markdown",
        hybrid="docling-fast", # ハイブリッドモード（OCR）
    )
    
    # 結果の確認
    output_path = Path(output_dir) / "0001.md"
    if output_path.exists():
        print("OCR 成功!")
        print("-" * 20)
        print(output_path.read_text()[:500]) # 最初の一部を表示
        print("-" * 20)
    else:
        print("出力ファイルが見つかりません。")
        # フォルダの中身を確認
        for f in Path(output_dir).glob("*"):
            print(f"Found: {f}")

except Exception as e:
    print(f"Error during OCR: {e}")

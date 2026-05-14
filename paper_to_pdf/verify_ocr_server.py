
import opendataloader_pdf
from pathlib import Path
import time

input_file = "test_input.pdf"
output_dir = "test_output"

print(f"Processing {input_file} using OCR server...")

# サーバー起動待ち (数秒待機)
time.sleep(10)

try:
    # OCR 実行 (hybrid="docling-fast" はデフォルトで 5002 ポート)
    opendataloader_pdf.convert(
        input_path=input_file,
        output_dir=output_dir,
        format="markdown",
        hybrid="docling-fast"
    )
    
    # 結果の確認
    # 出力ファイル名は入力ファイル名に基づいて決まるはず
    output_path = Path(output_dir) / "test_input.md"
    if output_path.exists():
        print("OCR 成功!")
        print("-" * 20)
        print(output_path.read_text()[:1000])
        print("-" * 20)
    else:
        print("出力ファイル test_input.md が見つかりません。")
        # フォルダの中身を確認
        for f in Path(output_dir).glob("*"):
            print(f"Found: {f}")

except Exception as e:
    print(f"Error during OCR: {e}")

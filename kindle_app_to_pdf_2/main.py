import pyautogui as py
import time
import os
import img2pdf
import argparse
from datetime import datetime

# 設定
OUTPUT_DIR = "KindleScreenshots"
PAGE_TURN_WAIT = 1.0  # ページめくり後の待機時間（秒）
JPEG_QUALITY = 80      # 保存する画像の画質（0-100）

def get_args():
    parser = argparse.ArgumentParser(description="Kindle to PDF converter")
    parser.add_argument("--direction", choices=["left", "right"], default="right", help="ページめくり方向")
    parser.add_argument("--pages", type=int, default=200, help="撮影するページ数")
    return parser.parse_args()

def generate_file_name():
    now = datetime.now()
    return now.strftime("%Y%m%d_%H%M%S") + ".pdf"

def create_pdf(image_folder, output_pdf_name):
    print(f"\nPDF作成中: {output_pdf_name}")
    images = []
    
    # ファイル名でソートして連番通りに読み込む
    file_names = sorted(os.listdir(image_folder))
    for file_name in file_names:
        if file_name.endswith(".jpg"):
            path = os.path.join(image_folder, file_name)
            images.append(path)
            
    if images:
        with open(output_pdf_name, "wb") as f:
            f.write(img2pdf.convert(images))
        print("PDF作成が完了しました。")

def main():
    args = get_args()
    direction = args.direction
    total_pages = args.pages
    output_pdf_name = generate_file_name()
    
    # 出力用ディレクトリの作成
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print(f"設定: {total_pages}ページ、方向: {direction}")
    print("5秒後に開始します。Kindleアプリをアクティブにしてください...")
    time.sleep(5)
    
    turn_key = "left" if direction == "left" else "right"
    
    try:
        for i in range(1, total_pages + 1):
            # スクリーンショット撮影
            screenshot = py.screenshot()
            
            # 保存先のパス生成（0埋め4桁の連番）
            file_name = os.path.join(OUTPUT_DIR, f"page_{i:04d}.jpg")
            
            # RGBに変換してJPEG保存
            screenshot.convert("RGB").save(file_name, "JPEG", quality=JPEG_QUALITY)
            print(f"保存完了: {i} / {total_pages}")
            
            # ページめくり操作
            py.keyDown(turn_key)
            time.sleep(0.1)
            py.keyUp(turn_key)
            
            # ページ読み込み待機
            time.sleep(PAGE_TURN_WAIT)
            
        print("\n指定した全ページの撮影が完了しました。")
        
    except KeyboardInterrupt:
        print("\n中断されました。これまでに撮影したページでPDFを作成します。")
        
    # PDFへの変換処理
    create_pdf(OUTPUT_DIR, output_pdf_name)

if __name__ == "__main__":
    main()

import os
import subprocess
import time
from pathlib import Path

try:
    import pyautogui
except ImportError:
    print("pyautogui is required. Run: uv add pyautogui")
    exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_PATH = PROJECT_ROOT / "demo.gif"
VIDEO_TEMP = PROJECT_ROOT / "demo_temp.mov"

def run_demo():
    # 1. 前回のファイルを削除
    if VIDEO_TEMP.exists():
        VIDEO_TEMP.unlink()
    
    print("--- デモ動画の生成を開始します ---")
    print("※ macOS のアクセシビリティと画面収録の許可が必要です。")
    
    # 2. ffmpeg による画面録画の開始 (Mac の avfoundation を使用)
    # 録画範囲: 左上から 1360x840 (アプリの geometry と一致させる)
    # -i "1" は通常メインディスプレイ。
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "avfoundation",
        "-pix_fmt", "uyvy422",
        "-i", "1",  # 画面インデックス 1
        "-video_size", "1360x840",
        "-t", "20",  # 最大 20 秒
        str(VIDEO_TEMP)
    ]
    
    print("録画を開始します (20秒間)...")
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 録画開始を待つ
    time.sleep(2)
    
    # 3. アプリの起動 (デモモード)
    env = os.environ.copy()
    env["NHK_RADIO_DEMO_MODE"] = "1"
    app_proc = subprocess.Popen(["python3", "nhk_radio_dl.py"], env=env)
    
    # 起動待ち
    time.sleep(5)
    
    try:
        # 4. pyautogui による操作のシミュレート
        # ウィンドウが (0,0) にある前提
        
        # 検索窓をクリック (座標は 1360x840 の中央付近を想定 - 実際は試行錯誤が必要)
        # サイドバー幅 430px の中の検索窓を狙う
        print("操作を実行中...")
        pyautogui.click(200, 150) # 検索窓あたり
        time.sleep(1)
        pyautogui.write("language", interval=0.1)
        pyautogui.press("enter")
        time.sleep(2)
        
        # 一覧から一つ選択
        pyautogui.click(200, 300)
        time.sleep(1)
        
        # 一覧取得ボタンをクリック (右側パネルの上部)
        pyautogui.click(600, 200)
        time.sleep(5)
        
    except Exception as e:
        print(f"エラー発生: {e}")
    finally:
        # 5. アプリの終了
        print("終了処理中...")
        app_proc.terminate()
        time.sleep(1)
        ffmpeg_proc.terminate()
        ffmpeg_proc.wait()

    # 6. GIF への変換 (高品質パレット作成)
    if VIDEO_TEMP.exists():
        print("GIF に変換中...")
        palette_path = Path("palette.png")
        subprocess.run(["ffmpeg", "-y", "-i", str(VIDEO_TEMP), "-vf", "palettegen", str(palette_path)])
        subprocess.run([
            "ffmpeg", "-y", "-i", str(VIDEO_TEMP), "-i", str(palette_path),
            "-filter_complex", "fps=10,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse",
            str(DEMO_PATH)
        ])
        palette_path.unlink()
        VIDEO_TEMP.unlink()
        print(f"完了しました! 生成されたファイル: {DEMO_PATH}")
    else:
        print("録画ファイルが生成されませんでした。")

if __name__ == "__main__":
    run_demo()

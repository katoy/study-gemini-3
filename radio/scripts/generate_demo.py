import os
import subprocess
import threading
import time
from pathlib import Path
import sys

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nhk_radio.core import fetch_program_list
from nhk_radio.gui.browser import EpisodeGuiBrowser
from nhk_radio.gui.toolkit import tk

DEMO_PATH = PROJECT_ROOT / "demo.gif"
VIDEO_TEMP = PROJECT_ROOT / "demo_temp.mov"

def run_auto_commands(browser: EpisodeGuiBrowser):
    """アプリのUIを自動操作するシナリオ"""
    print("オートデモシナリオを開始します...")
    
    try:
        # 1. 起動後の待機
        time.sleep(3)
        
        # 2. ジャンルを選択 (例: 語学講座)
        print("ジャンルを選択中...")
        browser.program_genre_filter_var.set("語学講座")
        # trace_add により自動的にフィルタが走る
        time.sleep(2)
        
        # 3. 番組を検索
        print("番組を検索中...")
        browser.program_search_var.set("ラジオ英会話")
        time.sleep(2)
        
        # 4. 番組一覧の最初を選択
        print("番組を選択中...")
        children = browser.program_tree.get_children()
        if children:
            browser._select_program_item(children[0])
            browser._on_program_select()
        time.sleep(2)
        
        # 5. エピソード一覧を取得 (「一覧を取得」ボタンを擬似クリック)
        print("エピソード一覧を取得中...")
        if hasattr(browser, "fetch_button"):
            browser.fetch_button.invoke()
        
        # 取得完了まで待機 (5秒程度)
        time.sleep(6)
        
        # 6. エピソードを選択
        print("エピソードを選択中...")
        ep_children = browser.episode_tree.get_children()
        if ep_children:
            browser.episode_tree.selection_set(ep_children[0])
            browser.episode_tree.focus(ep_children[0])
        time.sleep(3)
        
    except Exception as e:
        print(f"オートデモ中にエラーが発生しました: {e}")
    finally:
        print("デモ終了。アプリを閉じます。")
        browser.root.destroy()

def run_demo():
    if VIDEO_TEMP.exists():
        VIDEO_TEMP.unlink()
    
    print("--- 高精度オートデモ動画の生成を開始します ---")
    
    # 1. ffmpeg による画面録画の開始
    # 1360x840 の範囲を録画
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "avfoundation",
        "-pix_fmt", "uyvy422",
        "-i", "1",  # 画面インデックス (環境に合わせて調整が必要な場合があります)
        "-video_size", "1360x840",
        "-t", "30",
        str(VIDEO_TEMP)
    ]
    
    print("録画を開始します (ffmpeg)...")
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    
    # 2. アプリのセットアップ
    os.environ["NHK_RADIO_DEMO_MODE"] = "1"
    programs = fetch_program_list()
    output_dir = PROJECT_ROOT / "downloads"
    
    browser = EpisodeGuiBrowser(programs, output_dir)
    
    # 3. 自動操作スレッドの開始
    # mainloop がブロックするため、別スレッドで操作を送る
    threading.Thread(target=run_auto_commands, args=(browser,), daemon=True).start()
    
    # 4. アプリ起動 (メインループ)
    print("アプリを起動しました。")
    browser.run()
    
    # 5. 後処理
    ffmpeg_proc.terminate()
    ffmpeg_proc.wait()
    
    # 6. GIF 変換
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

if __name__ == "__main__":
    run_demo()

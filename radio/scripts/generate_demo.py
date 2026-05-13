import argparse
import importlib
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if TYPE_CHECKING:
    from nhk_radio.gui.browser import EpisodeGuiBrowser

fetch_program_list = importlib.import_module("nhk_radio.core").fetch_program_list
EpisodeGuiBrowserClass = importlib.import_module("nhk_radio.gui.browser").EpisodeGuiBrowser

DEMO_PATH = PROJECT_ROOT / "demo.gif"
VIDEO_TEMP = PROJECT_ROOT / "demo_temp.mov"

def run_auto_commands(browser: "EpisodeGuiBrowser"):
    """アプリのUIを自動操作するシナリオ"""
    print("オートデモシナリオを開始します...")
    try:
        time.sleep(4)
        browser.program_genre_filter_var.set("語学")
        browser.root.after(0, browser._on_program_filter_change)
        time.sleep(2)
        browser.program_search_var.set("英語")
        time.sleep(3)
        children = browser.program_tree.get_children()
        if children:
            browser._select_program_item(children[0])
            browser._on_program_select()
            time.sleep(2)
            if hasattr(browser, "fetch_button"):
                browser.fetch_button.invoke()
        time.sleep(8)
        ep_children = browser.episode_tree.get_children()
        if ep_children:
            browser.episode_tree.selection_set(ep_children[0])
            browser.episode_tree.focus(ep_children[0])
            time.sleep(2)
            if hasattr(browser, "download_button"):
                browser.download_button.invoke()
            start_wait = time.time()
            while time.time() - start_wait < 30:
                has_active = any(row["state"] == "running" for row in browser.active_download_rows.values())
                if not has_active and getattr(browser, "download_finished_count", 0) > 0:
                    break
                time.sleep(1)
        time.sleep(3)
    except Exception as e:
        print(f"オートデモ中にエラーが発生しました: {e}")
    finally:
        print("デモ終了。アプリを閉じます。")
        browser.root.after(0, browser.root.destroy)

def run_demo(manual: bool = False):
    if VIDEO_TEMP.exists():
        VIDEO_TEMP.unlink()

    print(f"--- 画面全体の録画を開始します ({'手動操作' if manual else '自動シナリオ'}) ---")

    # 1. ffmpeg 開始 (crop なし、画面全体)
    ffmpeg_cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "avfoundation",
        "-pixel_format", "uyvy422",
        "-framerate", "30",
        "-i", "3", # Capture screen 0
        "-pix_fmt", "yuv420p",
        str(VIDEO_TEMP)
    ]

    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd)
    time.sleep(1)

    # 2. アプリのセットアップ
    os.environ["NHK_RADIO_DEMO_MODE"] = "1"
    programs = fetch_program_list()
    browser = EpisodeGuiBrowserClass(programs, PROJECT_ROOT / "downloads")

    # 位置を (100, 100) 付近に配置 (フルスクリーンでも見やすい位置)
    browser.root.geometry("1360x840+100+100")

    if not manual:
        threading.Thread(target=run_auto_commands, args=(browser,), daemon=True).start()

    print("アプリ起動中...")
    browser.run()

    # 3. 録画停止
    print("録画を停止中...")
    ffmpeg_proc.send_signal(signal.SIGINT)
    try:
        ffmpeg_proc.wait(timeout=5)
    except Exception:
        ffmpeg_proc.kill()

    # 4. GIF 変換
    if VIDEO_TEMP.exists() and VIDEO_TEMP.stat().st_size > 0:
        print("GIF に変換中 (画面全体)...")
        palette_path = PROJECT_ROOT / "palette.png"
        try:
            # 画面全体は解像度が高いため、1280px幅にリサイズしてGIFを作成
            subprocess.run([
                "ffmpeg", "-loglevel", "error", "-y", "-i", str(VIDEO_TEMP),
                "-vf", "palettegen", "-sws_flags", "lanczos",
                "-frames:v", "1", "-update", "1", str(palette_path)
            ], check=True)
            subprocess.run([
                "ffmpeg", "-loglevel", "error", "-y", "-i", str(VIDEO_TEMP), "-i", str(palette_path),
                "-filter_complex", "fps=10,scale=1280:-1:flags=lanczos[x];[x][1:v]paletteuse",
                str(DEMO_PATH)
            ], check=True)
            print(f"完了しました! {DEMO_PATH}")
        finally:
            if palette_path.exists():
                palette_path.unlink()
            if VIDEO_TEMP.exists():
                VIDEO_TEMP.unlink()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true", help="手動操作モードで録画する")
    args = parser.parse_args()
    run_demo(manual=args.manual)

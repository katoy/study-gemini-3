import os
import subprocess
import threading
import time
from pathlib import Path
import sys
import signal

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nhk_radio.core import fetch_program_list
from nhk_radio.gui.browser import EpisodeGuiBrowser

DEMO_PATH = PROJECT_ROOT / "demo.gif"
VIDEO_TEMP = PROJECT_ROOT / "demo_temp.mov"

def run_auto_commands(browser: EpisodeGuiBrowser):
    """アプリのUIを自動操作するシナリオ"""
    print("オートデモシナリオを開始します...")
    
    try:
        time.sleep(3)
        
        print("ジャンルを選択中 (語学)...")
        browser.program_genre_filter_var.set("語学")
        time.sleep(2)
        
        print("番組を検索中 (英語)...")
        browser.program_search_var.set("英語")
        time.sleep(3)
        
        children = browser.program_tree.get_children()
        if children:
            print(f"番組を選択中... ({len(children)} 件ヒット)")
            browser._select_program_item(children[0])
            browser._on_program_select()
            time.sleep(2)
            
            print("エピソード一覧を取得中...")
            if hasattr(browser, "fetch_button") and str(browser.fetch_button["state"]) != "disabled":
                browser.fetch_button.invoke()
            else:
                threading.Thread(target=browser._fetch_episodes_for_selected, daemon=True).start()
        else:
            print("警告: 検索結果が空です。")
        
        time.sleep(6)
        
        print("エピソードを選択中...")
        ep_children = browser.episode_tree.get_children()
        if ep_children:
            browser.episode_tree.selection_set(ep_children[0])
            browser.episode_tree.focus(ep_children[0])
            time.sleep(2)
            
            print("最初のエピソードをダウンロード開始...")
            if hasattr(browser, "download_button") and str(browser.download_button["state"]) != "disabled":
                browser.download_button.invoke()
            
            print("ダウンロード完了を待機中...")
            start_wait = time.time()
            while time.time() - start_wait < 30:
                has_active = any(
                    row["state"] == "running" for row in browser.active_download_rows.values()
                )
                if not has_active and browser.download_finished_count > 0:
                    print("ダウンロードが完了しました。")
                    break
                time.sleep(1)
        
    except Exception as e:
        print(f"オートデモ中にエラーが発生しました: {e}")
    finally:
        print("デモ終了。アプリを閉じます。")
        browser.root.destroy()

def run_demo():
    if VIDEO_TEMP.exists():
        VIDEO_TEMP.unlink()
    
    print("--- 高精度オートデモ動画の生成を開始します ---")
    
    # ffmpeg 設定
    # デバイス一覧の観測結果: [3] Capture screen 0
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "avfoundation",
        "-framerate", "10",  # サポートされている範囲の値を明示
        "-pix_fmt", "uyvy422",
        "-i", "3",           # 画面インデックス 3 (Capture screen 0)
        "-video_size", "1360x840",
        str(VIDEO_TEMP)
    ]
    
    print("録画を開始します (ffmpeg)...")
    # エラー出力を取得するために stderr=PIPE にする
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(2)
    
    # 録画が即座に失敗していないかチェック
    if ffmpeg_proc.poll() is not None:
        _, stderr = ffmpeg_proc.communicate()
        print("ffmpeg が起動直後に終了しました。画面インデックスが正しくないか、許可がない可能性があります。")
        print(f"--- エラー出力 ---\n{stderr}")
        return

    # アプリのセットアップ
    os.environ["NHK_RADIO_DEMO_MODE"] = "1"
    programs = fetch_program_list()
    output_dir = PROJECT_ROOT / "downloads"
    
    browser = EpisodeGuiBrowser(programs, output_dir)
    threading.Thread(target=run_auto_commands, args=(browser,), daemon=True).start()
    
    print("アプリを起動しました。")
    browser.run()
    
    print("録画を停止しています...")
    ffmpeg_proc.send_signal(signal.SIGINT)
    try:
        ffmpeg_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        ffmpeg_proc.kill()
    
    # GIF 変換
    if VIDEO_TEMP.exists() and VIDEO_TEMP.stat().st_size > 0:
        print(f"録画成功 ({VIDEO_TEMP.stat().st_size} bytes)。GIF に変換中...")
        palette_path = PROJECT_ROOT / "palette.png"
        try:
            subprocess.run(["ffmpeg", "-y", "-i", str(VIDEO_TEMP), "-vf", "palettegen", str(palette_path)], check=True)
            subprocess.run([
                "ffmpeg", "-y", "-i", str(VIDEO_TEMP), "-i", str(palette_path),
                "-filter_complex", "fps=10,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse",
                str(DEMO_PATH)
            ], check=True)
            print(f"完了しました! 生成されたファイル: {DEMO_PATH}")
        except Exception as e:
            print(f"GIF 変換に失敗しました: {e}")
        finally:
            if palette_path.exists(): palette_path.unlink()
            if VIDEO_TEMP.exists(): VIDEO_TEMP.unlink()
    else:
        stdout, stderr = ffmpeg_proc.communicate()
        print("録画ファイルが生成されませんでした。")
        print(f"--- ffmpeg エラー出力 ---\n{stderr}")

if __name__ == "__main__":
    run_demo()

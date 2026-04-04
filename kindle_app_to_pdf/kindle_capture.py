"""
Mac Kindle デスクトップアプリのページをスクリーンショットでキャプチャするモジュール。
osascript (AppleScript) と screencapture コマンドを使用します。
"""

import hashlib
import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 定数
KINDLE_APP_NAMES = ["Kindle", "Amazon Kindle"]
MAX_SAME_PAGES = 3  # 同じ画面が何回続いたら終端とみなすか


def sanitize_filename(name: str) -> str:
    """ファイル名として使用できない文字を除去・置換します。"""
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name[:80] or 'kindle_book'


def _run_applescript(script: str) -> str:
    """AppleScript を実行して標準出力を返します。"""
    result = subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript エラー: {result.stderr.strip()}")
    return result.stdout.strip()


def _find_and_activate_kindle() -> tuple[str, str]:
    """
    Kindle アプリをアクティブにして (アプリ名, プロセス名) を返します。

    Returns:
        (app_name, process_name) のタプル
    """
    for app_name in KINDLE_APP_NAMES:
        try:
            _run_applescript(f'tell application "{app_name}" to activate')
            time.sleep(1.0)  # アクティブ化の完了を待つ
            process_name = _find_kindle_process_name()
            return app_name, process_name
        except RuntimeError:
            continue

    raise RuntimeError(
        "Kindle アプリが見つかりません。\n"
        "Kindle アプリが起動しており、本が表示されていることを確認してください。"
    )


def _find_kindle_process_name() -> str:
    """System Events で動作中の Kindle プロセス名を取得します。"""
    script = '''
tell application "System Events"
    set kindleProcs to name of every process whose name contains "Kindle"
    if (count of kindleProcs) > 0 then
        return item 1 of kindleProcs
    end if
    return ""
end tell
'''
    result = _run_applescript(script)
    if result:
        return result
    raise RuntimeError("System Events で Kindle プロセスが見つかりません。")


def get_window_title(process_name: str) -> str:
    """System Events 経由で Kindle ウィンドウのタイトルを取得します。"""
    script = f'''
tell application "System Events"
    tell process "{process_name}"
        return name of front window
    end tell
end tell
'''
    try:
        return _run_applescript(script)
    except Exception as e:
        logger.warning(f"ウィンドウタイトルの取得に失敗しました: {e}")
        return "kindle_book"


def _get_window_bounds(process_name: str) -> tuple[int, int, int, int]:
    """
    System Events 経由でウィンドウの表示領域を返します。

    Returns:
        (x, y, width, height) のタプル
    """
    script = f'''
tell application "System Events"
    tell process "{process_name}"
        set pos to position of front window
        set sz to size of front window
        return (item 1 of pos as string) & "," & (item 2 of pos as string) & "," & (item 1 of sz as string) & "," & (item 2 of sz as string)
    end tell
end tell
'''
    raw = _run_applescript(script)
    parts = [int(v.strip()) for v in raw.split(',')]
    x, y, w, h = parts
    return x, y, w, h


def _capture_window_region(process_name: str, output_path: str) -> None:
    """
    Kindle ウィンドウの領域をスクリーンショット撮影します。

    screencapture の -R オプションで指定領域のみを撮影します。
    """
    x, y, w, h = _get_window_bounds(process_name)
    subprocess.run(
        ['screencapture', '-x', '-R', f'{x},{y},{w},{h}', output_path],
        check=True
    )


def _send_next_page(process_name: str) -> None:
    """次ページへ進むキー（右矢印キー）を Kindle アプリに送信します。"""
    script = f'''
tell application "System Events"
    tell process "{process_name}"
        key code 124
    end tell
end tell
'''
    _run_applescript(script)


def _calculate_md5(path: Path) -> str:
    """ファイルの MD5 ハッシュを計算します。"""
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def capture_kindle_pages(
    output_dir: str,
    page_delay: float = 1.5,
) -> tuple[str, list[str]]:
    """
    Mac Kindle デスクトップアプリの全ページをキャプチャします。

    Args:
        output_dir:  スクリーンショットの保存先ディレクトリ
        page_delay:  ページ送り後の待機時間（秒）

    Returns:
        (book_title, [screenshot_path, ...])
    """
    app_name, process_name = _find_and_activate_kindle()
    logger.info(f"Kindle アプリを検出: {app_name} (プロセス: {process_name})")

    raw_title = get_window_title(process_name)
    book_title = sanitize_filename(raw_title)
    logger.info(f"書籍タイトル: {book_title}")

    book_dir = Path(output_dir) / book_title
    counter = 2
    while book_dir.exists():
        book_dir = Path(output_dir) / f"{book_title}_{counter}"
        counter += 1
    book_dir.mkdir(parents=True, exist_ok=True)

    screenshots: list[str] = []
    prev_hash: str | None = None
    same_count = 0

    logger.info("キャプチャ開始 (終端を検出したら自動停止します)...")

    while True:
        shot_path = book_dir / f"page_{len(screenshots) + 1:04d}.png"
        _capture_window_region(process_name, str(shot_path))
        cur_hash = _calculate_md5(shot_path)

        if cur_hash == prev_hash:
            same_count += 1
            if shot_path.exists():
                shot_path.unlink()
            if same_count >= MAX_SAME_PAGES:
                print(f"\n終端を検出しました。合計 {len(screenshots)} ページ")
                break
        else:
            same_count = 0
            screenshots.append(str(shot_path))
            print(f"\rキャプチャ中: {len(screenshots)} ページ目...", end='', flush=True)

        prev_hash = cur_hash
        _send_next_page(process_name)
        time.sleep(page_delay)

    return book_title, screenshots

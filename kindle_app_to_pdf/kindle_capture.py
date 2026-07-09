"""
Kindle デスクトップアプリのページをスクリーンショットでキャプチャするモジュール。
Mac: osascript (AppleScript) と screencapture コマンドを使用
Windows: pygetwindow と PIL.ImageGrab を使用
"""

import hashlib
import logging
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class KindleCapturer(Protocol):
    """Kindle キャプチャのインターフェース。"""

    def capture_pages(
        self,
        output_dir: str,
        page_delay: float = 1.5,
        direction: str = 'right',
    ) -> tuple[str, list[str]]:
        """Kindle デスクトップアプリの全ページをキャプチャします。"""
        ...

# Windows 用のインポート
if sys.platform == "win32":
    try:
        import pygetwindow as gw  # type: ignore
        from PIL import ImageGrab  # type: ignore
        import ctypes
        from ctypes import wintypes
        import winreg

        # Python プロセスを DPI-aware にする
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()  # type: ignore
            except Exception:
                pass
    except ImportError:
        pass
else:
    # 非 Windows 環境での型チェック用
    gw: Any = None
    ImageGrab: Any = None
    wintypes: Any = None
    winreg: Any = None
    ctypes: Any = None

# 定数
KINDLE_APP_NAMES = ["Kindle", "Amazon Kindle"]
MAX_SAME_PAGES = 3  # 同じ画面が何回続いたら終端とみなすか


def sanitize_filename(name: str) -> str:
    """ファイル名として使用できない文字を除去・置換します。"""
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    name = name[:80].strip()  # 80文字に切り詰めて末尾の空白を削除
    return name or 'kindle_book'


def _escape_applescript_string(s: str) -> str:
    """AppleScript の文字列リテラル内で安全に使用できるようにエスケープします。"""
    return s.replace('\\', '\\\\').replace('"', '\\"')


def _calculate_md5(path: Path) -> str:
    """ファイルの MD5 ハッシュを計算します。"""
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


class MacKindleCapturer:
    """Mac 用の Kindle キャプチャ実装。"""

    def capture_pages(
        self,
        output_dir: str,
        page_delay: float = 1.5,
        direction: str = 'right',
    ) -> tuple[str, list[str]]:
        """Mac 用の Kindle ページキャプチャ処理。"""
        app_name, process_name = self._find_and_activate_kindle()
        logger.info(f"Kindle アプリを検出: {app_name} (プロセス: {process_name})")

        raw_book_title = self._get_window_title(process_name)
        book_title = sanitize_filename(raw_book_title)
        logger.info(f"書籍タイトル: {book_title} (判定用: {raw_book_title})")

        book_dir = Path(output_dir) / book_title
        counter = 2
        while book_dir.exists():
            book_dir = Path(output_dir) / f"{book_title}_{counter}"
            counter += 1
        book_dir.mkdir(parents=True, exist_ok=True)

        screenshots: list[str] = []
        hash_history: list[str] = []
        MAX_HISTORY = 5
        same_count = 0

        logger.info(f"キャプチャ開始 (方向: {direction})...")

        while True:
            # 1. 撮影前のチェック (ダイアログが出ていたらまず消去を試みる)
            if self._is_dialog_active(process_name, raw_book_title):
                logger.info("撮影前にダイアログ（またはウィンドウ状態の変化）を検出しました。消去を試みます。")
                self._dismiss_dialog(process_name)
                time.sleep(1.5)

            shot_path = book_dir / f"page_{len(screenshots) + 1:04d}.png"
            self._capture_window_region(process_name, str(shot_path))

            # 2. 撮影直後のチェック (重要: 撮影中に評価ダイアログが出た場合)
            if self._is_dialog_active(process_name, raw_book_title):
                logger.info("撮影した画像にダイアログが含まれている可能性があるため、破棄して終了します。")
                if shot_path.exists():
                    shot_path.unlink()
                break

            cur_hash = _calculate_md5(shot_path)

            # 3. ハッシュによる重複チェック
            if cur_hash in hash_history:
                same_count += 1
                if shot_path.exists():
                    shot_path.unlink()
                if same_count >= MAX_SAME_PAGES:
                    print(f"\n終端を検出しました（画像重複による停滞）。合計 {len(screenshots)} ページ")
                    # 【重要】進めなくなった際の最後の1枚（＝重複の起点となったダイアログ等）を削除
                    if screenshots:
                        last_path = screenshots.pop()
                        if Path(last_path).exists():
                            Path(last_path).unlink()
                        print(f"末尾の重複元画像を除外しました。最終合計: {len(screenshots)} ページ")
                    break
            else:
                same_count = 0
                screenshots.append(str(shot_path))
                hash_history.append(cur_hash)
                if len(hash_history) > MAX_HISTORY:
                    hash_history.pop(0)

                print(f"キャプチャ中: {len(screenshots)} ページ目...")

            # 次のページへ
            self._send_next_page(process_name, direction=direction)
            time.sleep(page_delay)

        return book_title, screenshots

    def _run_applescript(self, script: str) -> str:
        """AppleScript を実行して標準出力を返します。"""
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"AppleScript エラー: {result.stderr.strip()}")
        return result.stdout.strip()


    def _find_and_activate_kindle(self) -> tuple[str, str]:
        """Kindle アプリをアクティブにして (アプリ名, プロセス名) を返します。"""
        for app_name in KINDLE_APP_NAMES:
            try:
                self._run_applescript(f'tell application "{app_name}" to activate')
                time.sleep(1.0)  # アクティブ化の完了を待つ
                process_name = self._find_kindle_process_name()
                return app_name, process_name
            except RuntimeError:
                continue

        raise RuntimeError(
            "Kindle アプリが見つかりません。\n"
            "Kindle アプリが起動しており、本が表示されていることを確認してください。"
        )


    def _find_kindle_process_name(self) -> str:
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
        result = self._run_applescript(script)
        if result:
            return result
        raise RuntimeError("System Events で Kindle プロセスが見つかりません。")


    def _get_window_title(self, process_name: str) -> str:
        """System Events 経由で Kindle ウィンドウのタイトルを取得します。"""
        safe_proc = _escape_applescript_string(process_name)
        script = f'''
tell application "System Events"
    tell process "{safe_proc}"
        return name of front window
    end tell
end tell
'''
        try:
            return self._run_applescript(script)
        except Exception as e:
            logger.warning(f"ウィンドウタイトルの取得に失敗しました: {e}")
            return "kindle_book"



    def _get_window_bounds(self, process_name: str) -> tuple[int, int, int, int]:
        """Kindle 本体のウィンドウ（最も大きいウィンドウ）の領域を返します。"""
        safe_proc = _escape_applescript_string(process_name)
        script = f'''
tell application "System Events"
    tell process "{safe_proc}"
        set allWindows to every window
        if (count of allWindows) is 0 then return "0,0,0,0"
        
        set largestWin to item 1 of allWindows
        set maxArea to 0
        repeat with win in allWindows
            try
                set sz to size of win
                set area to (item 1 of sz) * (item 2 of sz)
                if area > maxArea then
                    set maxArea to area
                    set largestWin to win
                end if
            end try
        end repeat
        
        set pos to position of largestWin
        set sz to size of largestWin
        return (item 1 of pos as string) & "," & (item 2 of pos as string) & "," & (item 1 of sz as string) & "," & (item 2 of sz as string)
    end tell
end tell
'''
        raw = self._run_applescript(script)
        parts = [int(v.strip()) for v in raw.split(',')]
        if len(parts) != 4:
            raise RuntimeError("ウィンドウ領域の取得に失敗しました。")
        return parts[0], parts[1], parts[2], parts[3]

    def _capture_window_region(self, process_name: str, output_path: str) -> None:
        """Kindle ウィンドウの領域をスクリーンショット撮影します。"""
        safe_proc = _escape_applescript_string(process_name)
        # 撮影直前に確実に最前面へ
        script_activate = f'''
tell application "System Events"
    tell process "{safe_proc}"
        set frontmost to true
    end tell
end tell
'''
        self._run_applescript(script_activate)
        time.sleep(0.1)

        x, y, w, h = self._get_window_bounds(process_name)
        if w == 0 or h == 0:
            raise RuntimeError("Kindle ウィンドウが見つかりません。")
        subprocess.run(
            ['screencapture', '-x', '-R', f'{x},{y},{w},{h}', output_path],
            check=True
        )


    def _send_next_page(self, process_name: str, direction: str = 'right') -> None:
        """次ページへ進むキーを Kindle アプリに送信します。"""
        # 123: 左矢印, 124: 右矢印, 49: スペース
        if direction == 'left':
            key_code = 123
        elif direction == 'space':
            key_code = 49
        else:
            key_code = 124

        safe_proc = _escape_applescript_string(process_name)
        script = f'''
tell application "System Events"
    tell process "{safe_proc}"
        set frontmost to true
        key code {key_code}
    end tell
end tell
'''
        self._run_applescript(script)

    def _dismiss_dialog(self, process_name: str) -> bool:
        """Escape キーを送信してダイアログを閉じます。"""
        safe_proc = _escape_applescript_string(process_name)
        script = f'''
tell application "System Events"
    tell process "{safe_proc}"
        set frontmost to true
        key code 53 # Escape
    end tell
end tell
'''
        try:
            self._run_applescript(script)
            return True
        except Exception:
            return False

    def _is_dialog_active(self, process_name: str, book_title: str) -> bool:
        """評価ダイアログや終了画面が表示されているか判定します。"""
        safe_proc = _escape_applescript_string(process_name)
        safe_book_title = _escape_applescript_string(book_title)
        
        script = f'''
tell application "System Events"
    tell process "{safe_proc}"
        set winList to every window
        if (count of winList) is 0 then return "true|no_window"
        
        set frontWin to front window
        set frontTitle to name of frontWin
        
        if frontTitle is not "" and frontTitle does not contain "{safe_book_title}" then
            return "true|title_mismatch|" & frontTitle
        end if
        
        try
            set uiElems to UI elements of frontWin
            set allNames to ""
            repeat with e in uiElems
                try
                    set n to name of e
                    set allNames to allNames & n & ","
                end try
            end repeat
            
            set keywords to {{"評価", "レビュー", "完了", "閉じる", "送信", "Rate this", "Review", "Done", "Close"}}
            repeat with k in keywords
                if allNames contains k then
                    return "true|keyword_detected|" & k
                end if
            end repeat
        end try

        repeat with w in winList
            try
                if role of w is "AXDialog" or subrole of w is "AXDialog" then
                    return "true|dialog_role|" & (name of w)
                end if
            end try
        end repeat

        return "false"
    end tell
end tell
'''
        try:
            result = self._run_applescript(script)
            if not result or result == "false":
                return False
            
            logger.info(f"終端・ダイアログ検知: {result}")
            return True
        except Exception as e:
            logger.debug(f"ダイアログチェック失敗 (無視して継続): {e}")
            return False

class WindowsKindleCapturer:
    """Windows 用の Kindle キャプチャ実装。"""

    def capture_pages(
        self,
        output_dir: str,
        page_delay: float = 1.5,
        direction: str = 'right',
    ) -> tuple[str, list[str]]:
        """Windows 用の Kindle ページキャプチャ処理。"""
        # Kindle ウィンドウを一度だけ検出（位置を固定）
        x, y, width, height = self._find_kindle_window()
        bbox = (x, y, x + width, y + height)

        book_title = self._get_book_title()
        logger.info(f"書籍タイトル: {book_title}")

        book_dir = Path(output_dir) / book_title
        counter = 2
        while book_dir.exists():
            book_dir = Path(output_dir) / f"{book_title}_{counter}"
            counter += 1
        book_dir.mkdir(parents=True, exist_ok=True)

        screenshots: list[str] = []
        last_hash = None
        same_count = 0

        logger.info(f"キャプチャ開始 (方向: {direction})...")
        print("Windows Kindle をキャプチャ中です...")

        while True:
            shot_path = book_dir / f"page_{len(screenshots) + 1:04d}.png"

            try:
                self._capture_window_region(str(shot_path), bbox)
            except Exception as e:
                logger.error(f"キャプチャエラー: {e}")
                break

            cur_hash = _calculate_md5(shot_path)

            # 前のページと同じハッシュかどうかをチェック
            if cur_hash == last_hash:
                same_count += 1
                logger.debug(f"重複検出: {same_count}/{MAX_SAME_PAGES}")
                if shot_path.exists():
                    shot_path.unlink()
                if same_count >= MAX_SAME_PAGES:
                    print(f"\n終端を検出しました（画像が変わらなくなった）。合計 {len(screenshots)} ページ")
                    break
            else:
                same_count = 0
                screenshots.append(str(shot_path))
                last_hash = cur_hash

                print(f"キャプチャ中: {len(screenshots)} ページ目...")

            # 次のページへ
            try:
                self._send_next_page(direction=direction)
            except Exception as e:
                logger.warning(f"ページ送り エラー: {e}")
                break

            time.sleep(page_delay)

        return book_title, screenshots

    def _get_dpi_scale(self) -> float:
        """Windows の DPI スケーリング係数を取得します。"""
        try:
            registry_path = r"Control Panel\Desktop"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path) as key:
                dpi_value, _ = winreg.QueryValueEx(key, "LogPixels")
                return float(dpi_value / 96.0)
        except Exception:
            try:
                hdc = ctypes.windll.user32.GetDC(0)
                dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
                ctypes.windll.user32.ReleaseDC(0, hdc)
                return float(dpi / 96.0)
            except Exception:
                return 1.0

    def _find_kindle_window(self) -> tuple[int, int, int, int]:
        """Windows で Kindle ウィンドウを検出し、クライアント領域を返します。"""
        kindle_windows = gw.getWindowsWithTitle("Kindle")
        if not kindle_windows:
            raise RuntimeError("Kindle window not found. Please open the Kindle app and try again.")

        window = kindle_windows[0]
        logger.info(f"Found Kindle window: {window.title}")

        try:
            window.activate()
        except Exception as e:
            logger.warning(f"Kindle ウィンドウの有効化に失敗しました (通常起動試行): {e}")
            try:
                logger.info("ウィンドウの復元 (restore) を試みます...")
                window.restore()
                window.activate()
            except Exception as e2:
                logger.warning(f"ウィンドウの復元/有効化に失敗しました: {e2}")
                logger.warning("手動で Kindle ウィンドウをクリックして最前面にしてください。")

        # Windows のフォーカス奪取防止対策として、タイトルバーをクリックして確実にアクティブ化する
        try:
            import pyautogui as py  # type: ignore
            time.sleep(0.2)
            py.click(window.left + 150, window.top + 15)
            time.sleep(0.1)
            py.press('esc')  # タイトルバークリックで奪われたキーボードフォーカスを本文に戻す
            logger.info("Kindle ウィンドウのタイトルバーをクリックしてフォーカスを設定しました。")
        except Exception as e:
            logger.warning(f"Kindle ウィンドウのクリックによるアクティブ化に失敗しました: {e}")
        time.sleep(0.5)

        hwnd = window._hWnd
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        client_rect = wintypes.RECT()
        ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(client_rect))

        # クライアント領域の左上 (0, 0) をスクリーン座標に変換して正しいキャプチャ開始位置を取得する
        pt = wintypes.POINT(0, 0)
        ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))

        x, y = pt.x, pt.y
        width = client_rect.right - client_rect.left
        height = client_rect.bottom - client_rect.top

        dpi_scale = self._get_dpi_scale()
        logger.info(f"Capture region: {width}x{height} (DPI: {dpi_scale:.2f}x)")

        return x, y, width, height

    def _get_book_title(self) -> str:
        """Windows で Kindle ウィンドウのタイトルから本のタイトルを抽出します。"""
        kindle_windows = gw.getWindowsWithTitle("Kindle")
        if kindle_windows:
            title = kindle_windows[0].title
            if " - " in title:
                return sanitize_filename(title.split(" - ", 1)[1])
        return "kindle_book"

    def _capture_window_region(self, output_path: str, bbox: tuple[int, int, int, int]) -> None:
        """Windows で Kindle ウィンドウの領域をスクリーンショット撮影します。"""
        screenshot = ImageGrab.grab(bbox=bbox)
        screenshot.convert("RGB").save(output_path, "PNG")

    def _send_next_page(self, direction: str = 'right') -> None:
        """Windows で Kindle ウィンドウにページめくりキーを送信します。"""
        import pyautogui as py  # type: ignore
        kindle_windows = gw.getWindowsWithTitle("Kindle")
        if kindle_windows:
            window = kindle_windows[0]
            if not window.isActive:
                try:
                    window.activate()
                    time.sleep(0.1)
                    py.click(window.left + 150, window.top + 15)
                    time.sleep(0.1)
                    py.press('esc')  # タイトルバークリックで奪われたキーボードフォーカスを本文に戻す
                except Exception as e:
                    logger.debug(f"ページ送り時の Kindle ウィンドウ有効化に失敗しました (無視して継続します): {e}")
                time.sleep(0.2)

        key = 'left' if direction == 'left' else 'space' if direction == 'space' else 'right'
        py.press(key)


def capture_kindle_pages(
    output_dir: str,
    page_delay: float = 1.5,
    direction: str = 'right',
) -> tuple[str, list[str]]:
    """
    Kindle デスクトップアプリの全ページをキャプチャします。
    OS に応じて適切なキャプチャ実装を選択します。
    """
    system = platform.system()
    capturer: KindleCapturer

    if system == "Windows":
        capturer = WindowsKindleCapturer()
    else:
        capturer = MacKindleCapturer()

    return capturer.capture_pages(output_dir, page_delay, direction)

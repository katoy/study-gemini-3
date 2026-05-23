"""
Kindle Cloud Reader のページをスクリーンショットでキャプチャするモジュール。
既存の Chrome セッション (CDP) に接続して動作します。
"""

import asyncio
import hashlib
import logging
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger(__name__)

# 定数
DEFAULT_CDP_URL = "http://localhost:9222"
MAX_SAME_PAGES = 3  # 同じ画面が何回続いたら終端とみなすか
MAX_PAGES = 5000  # 暴走防止のための最大キャプチャ枚数
NEXT_PAGE_KEY = "ArrowDown"  # 縦書き・横書きに関わらず次ページへ進むキー
CHROME_LAUNCH_TIMEOUT = 15.0  # Chrome 起動を待つ最大秒数
PAGE_STABLE_TIMEOUT = 10.0  # ページ安定検知の最大秒数


def sanitize_filename(name: str) -> str:
    """ファイル名として使用できない文字を除去・置換します。"""
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:80] or "kindle_book"


async def capture_kindle_pages(
    output_dir: str,
    cdp_url: str = DEFAULT_CDP_URL,
    page_delay: float = 0.8,
    browser_type: str = "chrome",
) -> Tuple[str, List[str]]:
    """
    Kindle Cloud Reader のページを全てキャプチャします。

    Returns:
        (book_title, [screenshot_path, ...])
    """
    async with async_playwright() as p:
        browser = await _connect_to_browser(p, cdp_url, browser_type)
        try:
            kindle_page = _find_kindle_tab(browser)

            await kindle_page.bring_to_front()
            await asyncio.sleep(2)

            raw_title = await kindle_page.title()
            book_title = _extract_title(raw_title)
            logger.info("ターゲットURL: %s", kindle_page.url)
            logger.info("書籍タイトル: %s", book_title)

            book_dir = Path(output_dir) / book_title
            counter = 2
            while book_dir.exists():
                book_dir = Path(output_dir) / f"{book_title}_{counter}"
                counter += 1
            book_dir.mkdir(parents=True, exist_ok=True)

            await _focus_reader(kindle_page)
            logger.info("キャプチャ準備完了。")

            screenshots = await _capture_all_pages(kindle_page, book_dir, page_delay)
            return book_title, screenshots
        finally:
            await browser.close()


async def _connect_to_browser(p, cdp_url: str, browser_type: str = "chrome") -> Browser:
    """ブラウザのリモートデバッグポートに接続します。"""
    try:
        return await p.chromium.connect_over_cdp(cdp_url)
    except Exception as e:
        os_name = platform.system()
        browser_name = "Edge" if browser_type == "edge" else "Chrome"

        if browser_type == "edge":
            if os_name == "Darwin":
                browser_cmd = (
                    "/Applications/Microsoft\\ Edge.app/Contents/MacOS/Microsoft\\ Edge "
                    "--remote-debugging-port=9222 --no-first-run"
                )
            elif os_name == "Windows":
                browser_cmd = (
                    '"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" '
                    "--remote-debugging-port=9222"
                )
            else:
                browser_cmd = "microsoft-edge --remote-debugging-port=9222"
        else:
            if os_name == "Darwin":
                browser_cmd = (
                    "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
                    "--remote-debugging-port=9222 --no-first-run"
                )
            elif os_name == "Windows":
                browser_cmd = (
                    '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
                    "--remote-debugging-port=9222"
                )
            else:
                browser_cmd = "google-chrome --remote-debugging-port=9222"

        raise RuntimeError(
            f"{browser_name} に接続できません: {e}\n\n"
            f"以下のコマンドで {browser_name} を起動してから再実行してください:\n"
            f"  {browser_cmd}\n"
            f"※ すでに {browser_name} が起動している場合は一度終了してから実行してください。"
        ) from e


def _get_browser_executable(browser_type: str = "chrome") -> str:
    """OS とブラウザの種類に応じた実行ファイルパスを返します。"""
    os_name = platform.system()
    if browser_type == "edge":
        if os_name == "Darwin":
            return "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        elif os_name == "Windows":
            candidates = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
            for path in candidates:
                if Path(path).exists():
                    return path
            return candidates[0]
        else:
            return "microsoft-edge"
    else:
        # Default to Chrome
        if os_name == "Darwin":
            return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        elif os_name == "Windows":
            candidates = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Google (x86)\Chrome\Application\chrome.exe",
            ]
            for path in candidates:
                if Path(path).exists():
                    return path
            return candidates[0]
        else:
            return "google-chrome"


def find_free_port() -> int:
    """使用可能な空きポートを探して返します。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _is_port_open(port: int, timeout: float = 1.0) -> bool:
    """指定ポートが開いているか確認します。"""
    try:
        with socket.create_connection(("localhost", port), timeout=timeout):
            return True
    except OSError:
        return False


def launch_browser(
    cdp_port: int = 9222,
    user_data_dir: Optional[str] = None,
    initial_url: Optional[str] = None,
    browser_type: str = "chrome",
) -> subprocess.Popen:
    """
    空のプロファイルでブラウザを新たに起動します。

    Args:
        cdp_port: CDP (リモートデバッグ) ポート番号 (デフォルト: 9222)
        user_data_dir: ユーザーデータディレクトリ。None の場合は一時ディレクトリを使用。
        initial_url: 起動時に開く URL
        browser_type: ブラウザの種類 (chrome or edge)

    Returns:
        起動したブラウザプロセス
    """
    browser_path = _get_browser_executable(browser_type)
    browser_name = "Edge" if browser_type == "edge" else "Chrome"

    if not Path(browser_path).exists() and platform.system() != "Linux":
        raise FileNotFoundError(f"{browser_name} が見つかりません: {browser_path}")

    if user_data_dir is None:
        user_data_dir = tempfile.mkdtemp(prefix=f"kindle_{browser_type}_")

    cmd = [
        browser_path,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if initial_url:
        cmd.append(initial_url)

    # ブラウザのクラッシュ原因を診断できるよう stderr を一時ファイルに保存する
    stderr_log = Path(tempfile.mkstemp(prefix=f"kindle_{browser_type}_", suffix=".log")[1])
    logger.info("%s を起動中: port=%d (stderr: %s)", browser_name, cdp_port, stderr_log)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=stderr_log.open("w"),
    )

    deadline = time.monotonic() + CHROME_LAUNCH_TIMEOUT
    while time.monotonic() < deadline:
        # プロセス自体が落ちている場合は即座に検知して中断する
        if proc.poll() is not None:
            stderr_tail = _tail_log(stderr_log)
            raise RuntimeError(
                f"{browser_name} プロセスが exit code {proc.returncode} で終了しました。\nstderr (末尾):\n{stderr_tail}"
            )
        if _is_port_open(cdp_port):
            logger.debug("%s が CDP ポート %d で起動しました", browser_name, cdp_port)
            return proc
        time.sleep(0.5)

    # タイムアウト時はプロセスを確実に終了させる
    _terminate_process(proc)
    stderr_tail = _tail_log(stderr_log)
    raise RuntimeError(
        f"{browser_name} が {CHROME_LAUNCH_TIMEOUT:.0f} 秒以内に CDP ポート {cdp_port} で応答しませんでした。\n"
        f"stderr (末尾):\n{stderr_tail}"
    )


def _terminate_process(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    """プロセスを丁寧に終了させ、必要なら kill する。"""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("Chrome が terminate に応答しないため kill します")
        proc.kill()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error("Chrome プロセスの終了に失敗しました (pid=%s)", proc.pid)


def _tail_log(path: Path, max_bytes: int = 4096) -> str:
    """ログファイルの末尾を最大 max_bytes だけ読み取って返します。"""
    try:
        data = path.read_bytes()
    except OSError as e:
        return f"(stderr ログ読み取り失敗: {e})"
    if not data:
        return "(空)"
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    return data.decode("utf-8", errors="replace")


def _find_kindle_tab(browser: Browser) -> Page:
    """Kindle Cloud Reader が開かれているタブを探します。"""
    all_urls = []
    kindle_pages = []
    for context in browser.contexts:
        for page in context.pages:
            url = page.url
            all_urls.append(url)
            if "read.amazon" in url:
                kindle_pages.append(page)

    if not kindle_pages:
        url_list = "\n".join(f"  - {u}" for u in all_urls) if all_urls else "  (タブなし)"
        raise RuntimeError(
            "Kindle Cloud Reader のタブが見つかりません。\n\n"
            "接続中の Chrome で開いているタブ:\n"
            f"{url_list}\n\n"
            "対処法:\n"
            "  1. --remote-debugging-port=9222 オプション付きで起動した Chrome で\n"
            "     Kindle Cloud Reader (read.amazon.co.jp) を開いてください。\n"
            "  2. 通常の Chrome とは別プロセスになります。"
        )

    for p in kindle_pages:
        if "asin=" in p.url or "reading" in p.url:
            return p
    return kindle_pages[-1]


def _extract_title(raw_title: str) -> str:
    """ページタイトルから書籍名を抽出します。"""
    title = raw_title.replace("Kindle Cloud Reader", "").strip(" -")
    return sanitize_filename(title)


async def _wait_for_page_stable(
    page: Page,
    check_interval: float = 0.3,
    stable_checks: int = 2,
    timeout: float = PAGE_STABLE_TIMEOUT,
) -> bool:
    """ページのレンダリングが安定するまで待機します（ローディング完了待ち）。

    連続する2回のスクリーンショットが一致したら安定とみなします。
    タイムアウト時は False を返します（呼び出し側で警告ログ等を出す）。
    """
    start = time.monotonic()
    prev_hash: Optional[str] = None
    stable_count = 0

    while time.monotonic() - start < timeout:
        try:
            data = await page.screenshot(full_page=False)
        except Exception:
            logger.debug("page stable 判定中に screenshot 取得失敗", exc_info=True)
            return False
        cur_hash = hashlib.md5(data).hexdigest()

        if cur_hash == prev_hash:
            stable_count += 1
            if stable_count >= stable_checks:
                return True
        else:
            stable_count = 0

        prev_hash = cur_hash
        await asyncio.sleep(check_interval)

    return False


async def _capture_all_pages(
    page: Page,
    book_dir: Path,
    page_delay: float,
) -> List[str]:
    """全ページを順にキャプチャします。"""
    screenshots: List[str] = []
    prev_hash: Optional[str] = None
    same_count = 0
    use_progress_line = sys.stderr.isatty()

    logger.info("キャプチャ開始 (終端を検出したら自動停止します)...")

    while True:
        # 暴走防止: 異常な数のページが取れた場合は強制終了
        if len(screenshots) >= MAX_PAGES:
            logger.warning(
                "キャプチャ枚数が上限 %d に達しました。終端検知が機能していない可能性があります。",
                MAX_PAGES,
            )
            break

        shot_path = book_dir / f"page_{len(screenshots) + 1:04d}.png"
        try:
            await page.screenshot(path=str(shot_path), full_page=False)
        except Exception as e:
            logger.error("ページ %d のキャプチャに失敗しました: %s", len(screenshots) + 1, e)
            raise
        cur_hash = _calculate_md5(shot_path)

        if cur_hash == prev_hash:
            same_count += 1
            if shot_path.exists():
                shot_path.unlink()
            if same_count >= MAX_SAME_PAGES:
                if use_progress_line:
                    print()  # 進捗行を改行で確定
                logger.info("終端を検出しました。合計 %d ページ", len(screenshots))
                break
        else:
            same_count = 0
            screenshots.append(str(shot_path))
            if use_progress_line:
                print(f"\rキャプチャ中: {len(screenshots)} ページ目...", end="", flush=True)
            else:
                logger.info("キャプチャ中: %d ページ目", len(screenshots))

        prev_hash = cur_hash
        await page.keyboard.press(NEXT_PAGE_KEY)
        await asyncio.sleep(page_delay)  # ページ遷移開始を確保する最低待機
        stable = await _wait_for_page_stable(page)  # ローディング完了まで待機
        if not stable:
            logger.warning(
                "ページ %d でレンダリング安定検知がタイムアウトしました (%.0f 秒)。"
                "終端検出が誤動作する可能性があります。",
                len(screenshots),
                PAGE_STABLE_TIMEOUT,
            )

    return screenshots


async def _focus_reader(page: Page) -> None:
    """リーダー画面にフォーカスを当てます。"""
    try:
        await page.bring_to_front()
        await page.focus("body")
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
    except Exception:
        # Escape 等は失敗しても致命的ではないが、診断用に DEBUG で残す
        logger.debug("リーダーへのフォーカス処理で例外が発生しました", exc_info=True)


def _calculate_md5(path: Path) -> str:
    """ファイルの MD5 ハッシュを計算します。"""
    return hashlib.md5(path.read_bytes()).hexdigest()

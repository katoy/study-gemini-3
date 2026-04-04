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
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger(__name__)

# 定数
VERTICAL_WRITING_MODES = {'vertical-rl', 'vertical-lr'}
DEFAULT_CDP_URL = 'http://localhost:9222'
MAX_SAME_PAGES = 3  # 同じ画面が何回続いたら終端とみなすか
NEXT_PAGE_KEY = 'ArrowDown'  # 縦書き・横書きに関わらず次ページへ進むキー


def sanitize_filename(name: str) -> str:
    """ファイル名として使用できない文字を除去・置換します。"""
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name[:80] or 'kindle_book'


async def capture_kindle_pages(
    output_dir: str,
    cdp_url: str = DEFAULT_CDP_URL,
    page_delay: float = 0.8,
) -> Tuple[str, List[str], str]:
    """
    Kindle Cloud Reader のページを全てキャプチャします。

    Returns:
        (book_title, [screenshot_path, ...], detected_writing_mode)
    """
    async with async_playwright() as p:
        browser = await _connect_to_chrome(p, cdp_url)
        try:
            kindle_page = _find_kindle_tab(browser)

            await kindle_page.bring_to_front()
            await asyncio.sleep(2)

            raw_title = await kindle_page.title()
            book_title = _extract_title(raw_title)
            logger.info(f"ターゲットURL: {kindle_page.url}")
            logger.info(f"書籍タイトル: {book_title}")

            book_dir = Path(output_dir) / book_title
            counter = 2
            while book_dir.exists():
                book_dir = Path(output_dir) / f"{book_title}_{counter}"
                counter += 1
            book_dir.mkdir(parents=True, exist_ok=True)

            await _focus_reader(kindle_page)
            logger.info("キャプチャ準備完了。")

            # ログ出力用に判定だけ行う
            detected = await _detect_writing_mode(kindle_page)
            logger.info(f"組方向(推定): {detected}")

            screenshots = await _capture_all_pages(kindle_page, book_dir, page_delay)
            return book_title, screenshots, detected
        finally:
            await browser.close()


async def _connect_to_chrome(p, cdp_url: str) -> Browser:
    """Chrome のリモートデバッグポートに接続します。"""
    try:
        return await p.chromium.connect_over_cdp(cdp_url)
    except Exception as e:
        os_name = platform.system()
        chrome_cmd = ""
        if os_name == "Darwin":
            chrome_cmd = (
                "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
                "--remote-debugging-port=9222 --no-first-run"
            )
        elif os_name == "Windows":
            chrome_cmd = (
                "\"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\" "
                "--remote-debugging-port=9222"
            )
        else:
            chrome_cmd = "google-chrome --remote-debugging-port=9222"

        raise RuntimeError(
            f"Chrome に接続できません: {e}\n\n"
            "以下のコマンドで Chrome を起動してから再実行してください:\n"
            f"  {chrome_cmd}\n"
            "※ すでに Chrome が起動している場合は一度終了してから実行してください。"
        )


def _get_chrome_executable() -> str:
    """OS に応じた Chrome の実行ファイルパスを返します。"""
    os_name = platform.system()
    if os_name == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif os_name == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return candidates[0]
    else:
        return "google-chrome"


def find_free_port() -> int:
    """使用可能な空きポートを探して返します。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def _is_port_open(port: int, timeout: float = 1.0) -> bool:
    """指定ポートが開いているか確認します。"""
    try:
        with socket.create_connection(("localhost", port), timeout=timeout):
            return True
    except OSError:
        return False


def launch_chrome(
    cdp_port: int = 9222,
    user_data_dir: Optional[str] = None,
    initial_url: Optional[str] = None,
) -> subprocess.Popen:
    """
    空のプロファイルで Chrome を新たに起動します。

    Args:
        cdp_port: CDP (リモートデバッグ) ポート番号 (デフォルト: 9222)
        user_data_dir: ユーザーデータディレクトリ。None の場合は一時ディレクトリを使用。
        initial_url: 起動時に開く URL

    Returns:
        起動した Chrome プロセス
    """
    chrome_path = _get_chrome_executable()

    if not Path(chrome_path).exists() and platform.system() != "Linux":
        raise FileNotFoundError(f"Chrome が見つかりません: {chrome_path}")

    if user_data_dir is None:
        user_data_dir = tempfile.mkdtemp(prefix="kindle_chrome_")

    cmd = [
        chrome_path,
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if initial_url:
        cmd.append(initial_url)

    logger.info(f"Chrome を起動中: port={cdp_port}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    deadline = time.time() + 15
    while time.time() < deadline:
        if _is_port_open(cdp_port):
            return proc
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError(f"Chrome が {cdp_port} ポートで起動しませんでした。")


def _find_kindle_tab(browser: Browser) -> Page:
    """Kindle Cloud Reader が開かれているタブを探します。"""
    all_urls = []
    kindle_pages = []
    for context in browser.contexts:
        for page in context.pages:
            url = page.url
            all_urls.append(url)
            if 'read.amazon' in url:
                kindle_pages.append(page)

    if not kindle_pages:
        url_list = '\n'.join(f'  - {u}' for u in all_urls) if all_urls else '  (タブなし)'
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
        if 'asin=' in p.url or 'reading' in p.url:
            return p
    return kindle_pages[-1]


def _extract_title(raw_title: str) -> str:
    """ページタイトルから書籍名を抽出します。"""
    title = raw_title.replace('Kindle Cloud Reader', '').strip(' -')
    return sanitize_filename(title)


async def _wait_for_page_stable(
    page: Page,
    check_interval: float = 0.3,
    stable_checks: int = 2,
    timeout: float = 10.0,
) -> None:
    """ページのレンダリングが安定するまで待機します（ローディング完了待ち）。

    連続する2回のスクリーンショットが一致したら安定とみなします。
    """
    start = time.monotonic()
    prev_hash: Optional[str] = None
    stable_count = 0

    while time.monotonic() - start < timeout:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            tmp_path = Path(f.name)
        try:
            await page.screenshot(path=str(tmp_path), full_page=False)
            cur_hash = _calculate_md5(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        if cur_hash == prev_hash:
            stable_count += 1
            if stable_count >= stable_checks:
                return
        else:
            stable_count = 0

        prev_hash = cur_hash
        await asyncio.sleep(check_interval)


async def _capture_all_pages(
    page: Page,
    book_dir: Path,
    page_delay: float,
) -> List[str]:
    """全ページを順にキャプチャします。"""
    screenshots: List[str] = []
    prev_hash: Optional[str] = None
    same_count = 0

    logger.info("キャプチャ開始 (終端を検出したら自動停止します)...")

    while True:
        shot_path = book_dir / f"page_{len(screenshots) + 1:04d}.png"
        await page.screenshot(path=str(shot_path), full_page=False)
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
        await page.keyboard.press(NEXT_PAGE_KEY)
        await asyncio.sleep(page_delay)  # ページ遷移開始を確保する最低待機
        await _wait_for_page_stable(page)  # ローディング完了まで待機

    return screenshots


async def _detect_writing_mode(page: Page) -> str:
    """縦書き・横書きを自動判定します（CSS解析）。"""
    try:
        wm = await page.evaluate("""() => {
            const getWM = (el) => {
                if (!el) return null;
                const style = getComputedStyle(el);
                return style.writingMode || style.webkitWritingMode;
            };

            // Kindle Cloud Reader の主要なテキストコンテナを探す
            const checkElements = (doc) => {
                // 優先度の高いクラス/ID
                const selectors = [
                    '.k6-content', 
                    '#ST_RE_Container', 
                    '.kindle-reader-container', 
                    'body', 
                    'html'
                ];
                for (const sel of selectors) {
                    const el = doc.querySelector(sel);
                    const s = getWM(el);
                    if (s && s.includes('vertical')) return 'vertical';
                }
                // それ以外の dir 属性などを持つ要素
                const items = doc.querySelectorAll('*[dir], .text, .content');
                for (const el of items) {
                    const s = getWM(el);
                    if (s && s.includes('vertical')) return 'vertical';
                }
                return null;
            };

            // メインドキュメントのチェック
            if (checkElements(document) === 'vertical') return 'vertical';

            // iframe 内のチェック
            for (const iframe of document.querySelectorAll('iframe')) {
                try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    if (checkElements(doc) === 'vertical') return 'vertical';
                } catch (_) {}
            }
            return 'horizontal-tb';
        }""")
        
        if wm and 'vertical' in wm:
            logger.info(f"  (判定: CSS解析により縦書きを検出)")
            return 'vertical'
    except Exception as e:
        logger.debug(f"CSS解析中にエラー: {e}")

    # デフォルトの判定
    logger.info("  (判定: 縦書きと仮定)")
    return 'vertical'


async def _focus_reader(page: Page) -> None:
    """リーダー画面にフォーカスを当てます。"""
    try:
        await page.bring_to_front()
        await page.focus('body')
        await page.keyboard.press('Escape')
        await asyncio.sleep(0.5)
        await page.keyboard.press('Escape')
        await asyncio.sleep(0.5)
    except Exception:
        pass


def _calculate_md5(path: Path) -> str:
    """ファイルの MD5 ハッシュを計算します。"""
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

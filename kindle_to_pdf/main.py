#!/usr/bin/env python3
"""
Kindle 本をキャプチャして画像 PDF を生成するツールのエントリーポイント。
"""

import argparse
import asyncio
import contextlib
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from kindle_capture import (
    _terminate_process,
    capture_kindle_pages,
    find_free_port,
    launch_browser,
    sanitize_filename,
)
from pdf_maker import make_pdf

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    """ログ設定をエントリーポイントで一度だけ初期化する。"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析します。"""
    parser = argparse.ArgumentParser(description="Kindle 本をキャプチャして PDF を生成します")
    parser.add_argument(
        "--output-dir",
        "-o",
        default="./output",
        help="出力先ディレクトリ (デフォルト: ./output)",
    )
    parser.add_argument(
        "--cdp-url",
        default="http://localhost:9222",
        help="Chrome CDP URL (デフォルト: http://localhost:9222)",
    )
    parser.add_argument(
        "--browser",
        choices=["chrome", "edge"],
        default="chrome",
        help="使用するブラウザ (デフォルト: chrome)",
    )
    parser.add_argument(
        "--launch-chrome",
        action="store_true",
        help="空のプロファイルでブラウザを新たに起動する (既存のブラウザとは独立した専用ウィンドウ)",
    )
    parser.add_argument(
        "--chrome-user-data-dir",
        help="--launch-chrome 使用時のユーザーデータディレクトリ (省略時は一時ディレクトリを使用)",
    )
    parser.add_argument(
        "--images-dir",
        metavar="DIR",
        help="既存の PNG 画像ディレクトリを入力として使用し、Kindle キャプチャをスキップする",
    )
    parser.add_argument(
        "--screenshots",
        choices=["delete", "keep"],
        default="delete",
        help="キャプチャした PNG の後処理: delete=削除(デフォルト), keep=保持\n"
        "※ --images-dir 指定時は既存ディレクトリのため常に保持される",
    )
    parser.add_argument(
        "--page-delay",
        type=float,
        default=0.8,
        help="ページ送りの待機時間(秒) (デフォルト: 0.8)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG レベルのログを有効にする (LOG_LEVEL=DEBUG でも可)",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    """メイン実行フロー。"""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ブラウザの自動起動
    chrome_proc = None
    with contextlib.ExitStack() as stack:
        if args.launch_chrome:
            import urllib.parse

            cdp_port = find_free_port()
            parsed_url = urllib.parse.urlparse(args.cdp_url)
            args.cdp_url = f"{parsed_url.scheme}://{parsed_url.hostname}:{cdp_port}{parsed_url.path}"

            # ユーザーデータディレクトリが省略されたら明示的に作成し、終了時に削除する
            if args.chrome_user_data_dir is None:
                temp_dir = stack.enter_context(tempfile.TemporaryDirectory(prefix="kindle_browser_"))
                args.chrome_user_data_dir = temp_dir
                logger.debug("一時ユーザーデータディレクトリを作成: %s", args.chrome_user_data_dir)

            try:
                chrome_proc = launch_browser(
                    cdp_port=cdp_port,
                    user_data_dir=args.chrome_user_data_dir,
                    initial_url="https://read.amazon.co.jp/",
                    browser_type=args.browser,
                )
            except (FileNotFoundError, RuntimeError):
                logger.exception("%s の起動に失敗しました", args.browser.capitalize())
                sys.exit(1)

        try:
            while True:
                print("\n" + "!" * 60)
                if chrome_proc:
                    print(f"専用の {args.browser.capitalize()} ウィンドウが起動しました。以下の準備をしてください：")
                    print("1. そのウィンドウで Amazon にログインし、本を開く。")
                    print("2. 準備ができたら、このターミナルに戻って Enter キーを押す。")
                else:
                    print("Kindle Cloud Reader で処理したい本を開き、")
                    print("準備ができたら Enter キーを押してください。")
                print("（終了する場合は 'q' を入力して Enter）")
                print("!" * 60 + "\n")

                try:
                    user_input = input(">> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()  # 改行を入れる
                    break

                if not user_input:
                    continue
                if user_input == "q":
                    break

                try:
                    # Step 1: キャプチャ（または既存画像の取得）
                    book_title, screenshots, shot_dir = await _prepare_screenshots(args, output_dir)

                    # Step 2: PDF 生成
                    pdf_path = _generate_pdf(output_dir, book_title, screenshots)

                    # Step 3: スクリーンショット削除
                    if args.screenshots == "delete" and shot_dir is not None:
                        _delete_screenshots(shot_dir)

                    _print_summary(pdf_path)

                    print("\n次の本を処理しますか？")
                except Exception:
                    # traceback も含めて出力（--verbose が無くても原因特定できるように）
                    logger.exception("エラーが発生しました")
                    print("修正して再試行するか、'q' で終了してください。")

        finally:
            if chrome_proc is not None:
                _terminate_process(chrome_proc)
                logger.info("%s を終了しました。", args.browser.capitalize())


async def _prepare_screenshots(args: argparse.Namespace, output_dir: Path) -> Tuple[str, List[str], Optional[Path]]:
    """キャプチャを実行するか、既存のスクリーンショットを準備します。"""
    shot_dir: Optional[Path]

    if args.images_dir:
        shot_dir = Path(args.images_dir)
        if not shot_dir.exists():
            raise FileNotFoundError(f"指定されたディレクトリが見つかりません: {shot_dir}")

        screenshots = sorted([str(p) for p in shot_dir.glob("page_*.png")])
        book_title = shot_dir.name
        logger.info("[1/2] 既存画像を使用: %s (%d ページ)", book_title, len(screenshots))
        return book_title, screenshots, None

    logger.info("[1/2] Kindle ページをキャプチャ中...")
    book_title, screenshots = await capture_kindle_pages(
        output_dir=str(output_dir),
        cdp_url=args.cdp_url,
        page_delay=args.page_delay,
        browser_type=args.browser,
    )
    logger.info("      完了: %s (%d ページ)", book_title, len(screenshots))
    shot_dir = Path(screenshots[0]).parent if screenshots else None
    return book_title, screenshots, shot_dir


def _generate_pdf(output_dir: Path, book_title: str, screenshots: List[str]) -> Path:
    """PDF を生成します。"""
    base_name = sanitize_filename(book_title)
    pdf_path = output_dir / (base_name + ".pdf")
    counter = 2
    while pdf_path.exists():
        pdf_path = output_dir / f"{base_name}_{counter}.pdf"
        counter += 1

    logger.info("[2/2] PDF を生成中: %s", pdf_path)
    make_pdf(
        screenshots=screenshots,
        output_path=str(pdf_path),
    )
    return pdf_path


def _delete_screenshots(shot_dir: Path) -> None:
    """スクリーンショットディレクトリを削除します。"""
    logger.info("スクリーンショットを削除中: %s", shot_dir)
    shutil.rmtree(shot_dir, ignore_errors=True)
    logger.info("      削除完了")


def _print_summary(pdf_path: Path) -> None:
    """実行結果のサマリーを表示します。"""
    print("\n" + "=" * 50)
    print("処理が完了しました！")
    print(f"  PDF パス:  {pdf_path.absolute()}")
    print("=" * 50 + "\n")


def main() -> None:
    """エントリーポイント。"""
    args = parse_args()
    verbose = args.verbose or os.environ.get("LOG_LEVEL", "").upper() == "DEBUG"
    _configure_logging(verbose)

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print()  # ^C 直後の改行
        logger.info("ユーザーにより中断されました。")
        sys.exit(0)
    except Exception:
        logger.critical("予期しないエラーが発生しました", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

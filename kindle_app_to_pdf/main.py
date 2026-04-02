#!/usr/bin/env python3
"""
Mac Kindle デスクトップアプリをキャプチャして画像 PDF を生成するツールのエントリーポイント。
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from kindle_capture import capture_kindle_pages, sanitize_filename
from pdf_maker import make_pdf

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を解析します。"""
    parser = argparse.ArgumentParser(
        description='Mac Kindle アプリをキャプチャして PDF を生成します'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='./output',
        help='出力先ディレクトリ (デフォルト: ./output)',
    )
    parser.add_argument(
        '--images-dir',
        metavar='DIR',
        help='既存の PNG 画像ディレクトリを入力として使用し、Kindle キャプチャをスキップする',
    )
    parser.add_argument(
        '--screenshots',
        choices=['delete', 'keep'],
        default='delete',
        help='キャプチャした PNG の後処理: delete=削除(デフォルト), keep=保持\n'
             '※ --images-dir 指定時は既存ディレクトリのため常に保持される',
    )
    parser.add_argument(
        '--page-delay',
        type=float,
        default=1.5,
        help='ページ送り後の待機時間(秒) (デフォルト: 1.5)',
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    """メイン実行フロー。"""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    while True:
        print("\n" + "!" * 60)
        print("Kindle アプリで処理したい本を開き、最初のページを表示してください。")
        print("準備ができたら Enter キーを押してください。")
        print("（終了する場合は 'q' を入力して Enter）")
        print("!" * 60 + "\n")

        user_input = input(">> ").strip().lower()
        if user_input == 'q':
            break

        try:
            # Step 1: キャプチャ（または既存画像の取得）
            book_title, screenshots, shot_dir = _prepare_screenshots(args, output_dir)

            # Step 2: PDF 生成
            pdf_path = _generate_pdf(output_dir, book_title, screenshots)

            # Step 3: スクリーンショット削除
            if args.screenshots == 'delete' and shot_dir is not None:
                _delete_screenshots(shot_dir)

            _print_summary(pdf_path)

            print("\n次の本を処理しますか？")
        except Exception as e:
            logger.error(f"エラーが発生しました: {e}")
            print("修正して再試行するか、'q' で終了してください。")


def _prepare_screenshots(
    args: argparse.Namespace, output_dir: Path
) -> Tuple[str, List[str], Optional[Path]]:
    """キャプチャを実行するか、既存のスクリーンショットを準備します。"""
    if args.images_dir:
        shot_dir = Path(args.images_dir)
        if not shot_dir.exists():
            logger.error(f"指定されたディレクトリが見つかりません: {shot_dir}")
            sys.exit(1)

        screenshots = sorted([str(p) for p in shot_dir.glob('page_*.png')])
        book_title = shot_dir.name
        logger.info(f"[1/2] 既存画像を使用: {book_title} ({len(screenshots)} ページ)")
        return book_title, screenshots, None

    logger.info("[1/2] Kindle ページをキャプチャ中...")
    try:
        book_title, screenshots = capture_kindle_pages(
            output_dir=str(output_dir),
            page_delay=args.page_delay,
        )
        logger.info(f"      完了: {book_title} ({len(screenshots)} ページ)")
        shot_dir = Path(screenshots[0]).parent if screenshots else None
        return book_title, screenshots, shot_dir
    except Exception as e:
        logger.error(f"キャプチャ中にエラーが発生しました: {e}")
        sys.exit(1)


def _generate_pdf(
    output_dir: Path,
    book_title: str,
    screenshots: List[str]
) -> Path:
    """PDF を生成します。"""
    base_name = sanitize_filename(book_title)
    pdf_path = output_dir / (base_name + '.pdf')
    counter = 2
    while pdf_path.exists():
        pdf_path = output_dir / f"{base_name}_{counter}.pdf"
        counter += 1

    logger.info(f"[2/2] PDF を生成中: {pdf_path}")
    try:
        make_pdf(
            screenshots=screenshots,
            output_path=str(pdf_path),
        )
        return pdf_path
    except Exception as e:
        logger.error(f"PDF 生成中にエラーが発生しました: {e}")
        sys.exit(1)


def _delete_screenshots(shot_dir: Path) -> None:
    """スクリーンショットディレクトリを削除します。"""
    logger.info(f"スクリーンショットを削除中: {shot_dir}")
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
    try:
        run(args)
    except KeyboardInterrupt:
        logger.info("\nユーザーにより中断されました。")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"予期しないエラーが発生しました: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

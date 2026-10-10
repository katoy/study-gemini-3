import argparse
from pathlib import Path
import runpy
import sys
from unittest.mock import patch
import pytest

import main


def test_parse_args_defaults() -> None:
    """parse_args: デフォルト引数のテスト。"""
    with patch.object(sys, "argv", ["main.py"]):
        args = main.parse_args()
        assert args.output_dir == "./output"
        assert args.images_dir is None
        assert args.screenshots == "delete"
        assert args.page_delay == 1.5
        assert args.direction == "space"
        assert args.max_pages == 2000


def test_parse_args_custom() -> None:
    """parse_args: カスタム引数のテスト。"""
    test_argv = [
        "main.py",
        "-o",
        "./custom_output",
        "--images-dir",
        "./imgs",
        "--screenshots",
        "keep",
        "--page-delay",
        "2.0",
        "--direction",
        "left",
        "--max-pages",
        "500",
    ]
    with patch.object(sys, "argv", test_argv):
        args = main.parse_args()
        assert args.output_dir == "./custom_output"
        assert args.images_dir == "./imgs"
        assert args.screenshots == "keep"
        assert args.page_delay == 2.0
        assert args.direction == "left"
        assert args.max_pages == 500


def test_run_images_dir_success(tmp_path: Path) -> None:
    """run: --images-dir 指定での正常系フロー。"""
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    (img_dir / "page_0001.png").touch()
    out_dir = tmp_path / "output"

    args = argparse.Namespace(
        output_dir=str(out_dir),
        images_dir=str(img_dir),
        screenshots="delete",
        page_delay=1.5,
        direction="right",
    )

    with patch("main.make_pdf") as mock_make_pdf:
        main.run(args)
        mock_make_pdf.assert_called_once()
        expected_pdf = out_dir / f"{img_dir.name}.pdf"
        assert expected_pdf.parent.exists()


def test_m5_images_dir_pdf_path_matches_duplicate(tmp_path: Path) -> None:
    """M-5 再現テスト: 既存 PDF がある場合、サマリー表示に渡されるパスが _2.pdf であること。"""
    img_dir = tmp_path / "my_book"
    img_dir.mkdir()
    (img_dir / "page_0001.png").touch()
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    # 既存の同名 PDF を作成しておく
    (out_dir / "my_book.pdf").touch()

    args = argparse.Namespace(
        output_dir=str(out_dir),
        images_dir=str(img_dir),
        screenshots="delete",
        page_delay=1.5,
        direction="right",
    )

    with patch("main.make_pdf"), patch("main._print_summary") as mock_summary:
        main.run(args)
        # 実際に生成されたパス (_2.pdf) がサマリーに渡されるべき
        mock_summary.assert_called_once_with(out_dir / "my_book_2.pdf")


def test_run_images_dir_exception(tmp_path: Path) -> None:
    """run: --images-dir 指定でエラー時に sys.exit(1) で終了。"""
    args = argparse.Namespace(
        output_dir=str(tmp_path / "out"),
        images_dir=str(tmp_path / "not_found"),
        screenshots="delete",
        page_delay=1.5,
        direction="right",
    )
    with pytest.raises(SystemExit) as exc:
        main.run(args)
    assert exc.value.code == 1


def test_run_capture_loop_quit_immediately(tmp_path: Path) -> None:
    """run: 対話ループで即 'q' を入力して終了。"""
    args = argparse.Namespace(
        output_dir=str(tmp_path / "out"),
        images_dir=None,
        screenshots="delete",
        page_delay=1.5,
        direction="right",
    )
    with patch("builtins.input", return_value="q"):
        main.run(args)


def test_run_capture_loop_success_and_delete(tmp_path: Path) -> None:
    """run: 1回キャプチャ成功後、次回プロンプトで 'q' 終了、画像削除処理が実行される。"""
    shot_dir = tmp_path / "book_shots"
    shot_dir.mkdir()
    p1 = shot_dir / "page_0001.png"
    p1.touch()

    args = argparse.Namespace(
        output_dir=str(tmp_path / "out"),
        images_dir=None,
        screenshots="delete",
        page_delay=1.5,
        direction="right",
        max_pages=2000,
    )

    with (
        patch("builtins.input", side_effect=["", "q"]),
        patch("main.capture_kindle_pages", return_value=("Sample Book", [str(p1)])),
        patch("main.make_pdf"),
        patch("main._delete_screenshots") as mock_del,
    ):
        main.run(args)
        mock_del.assert_called_once_with(shot_dir)


def test_run_capture_loop_pdf_generation_fails(tmp_path: Path) -> None:
    """run: PDF 生成で例外が発生した際のエラーハンドリングと継続。"""
    shot_dir = tmp_path / "book_shots"
    shot_dir.mkdir()
    p1 = shot_dir / "page_0001.png"
    p1.touch()

    args = argparse.Namespace(
        output_dir=str(tmp_path / "out"),
        images_dir=None,
        screenshots="delete",
        page_delay=1.5,
        direction="right",
        max_pages=2000,
    )

    with (
        patch("builtins.input", side_effect=["", "q"]),
        patch("main.capture_kindle_pages", return_value=("Book", [str(p1)])),
        patch("main.make_pdf", side_effect=RuntimeError("PDF error")),
    ):
        main.run(args)


def test_run_capture_loop_outer_exception(tmp_path: Path) -> None:
    """run: 外側の例外（キャプチャ失敗等）のハンドリング。"""
    args = argparse.Namespace(
        output_dir=str(tmp_path / "out"),
        images_dir=None,
        screenshots="delete",
        page_delay=1.5,
        direction="right",
        max_pages=2000,
    )

    with (
        patch("builtins.input", side_effect=["", "q"]),
        patch("main._prepare_screenshots", side_effect=RuntimeError("Capture fail")),
    ):
        main.run(args)


def test_prepare_screenshots_images_dir_no_files(tmp_path: Path) -> None:
    """_prepare_screenshots: images_dir に対象画像がない場合に FileNotFoundError。"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    args = argparse.Namespace(images_dir=str(empty_dir))
    with pytest.raises(FileNotFoundError, match="見つかりませんでした"):
        main._prepare_screenshots(args, tmp_path)


def test_prepare_screenshots_capture_empty() -> None:
    """_prepare_screenshots: キャプチャ結果が空の場合に RuntimeError。"""
    args = argparse.Namespace(images_dir=None, page_delay=1.5, direction="right", max_pages=2000)
    with patch("main.capture_kindle_pages", return_value=("Title", [])):
        with pytest.raises(RuntimeError, match="キャプチャされたページがありません"):
            main._prepare_screenshots(args, Path("./out"))


def test_prepare_screenshots_capture_single_page_warning(tmp_path: Path) -> None:
    """_prepare_screenshots: キャプチャが1枚のみの場合の警告ログ（right と space/left の両方向）。"""
    img = tmp_path / "page_0001.png"
    img.touch()

    # direction == "right"
    args_right = argparse.Namespace(
        images_dir=None, page_delay=1.5, direction="right", max_pages=2000
    )
    with patch("main.capture_kindle_pages", return_value=("Title", [str(img)])):
        title, shots, s_dir = main._prepare_screenshots(args_right, tmp_path)
        assert len(shots) == 1

    # direction == "space"
    args_space = argparse.Namespace(
        images_dir=None, page_delay=1.5, direction="space", max_pages=2000
    )
    with patch("main.capture_kindle_pages", return_value=("Title", [str(img)])):
        title, shots, s_dir = main._prepare_screenshots(args_space, tmp_path)
        assert len(shots) == 1

    # direction == "left"
    args_left = argparse.Namespace(
        images_dir=None, page_delay=1.5, direction="left", max_pages=2000
    )
    with patch("main.capture_kindle_pages", return_value=("Title", [str(img)])):
        title, shots, s_dir = main._prepare_screenshots(args_left, tmp_path)
        assert len(shots) == 1


def test_generate_pdf_duplicate_numbers(tmp_path: Path) -> None:
    """_generate_pdf: 既に同名 PDF が存在する場合、_2.pdf, _3.pdf とインクリメントされる。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "Test Book.pdf").touch()
    (out_dir / "Test Book_2.pdf").touch()

    with patch("main.make_pdf") as mock_make:
        pdf_path = main._generate_pdf(out_dir, "Test Book", ["p1.png"])
        assert pdf_path.name == "Test Book_3.pdf"
        mock_make.assert_called_once()


def test_delete_screenshots(tmp_path: Path) -> None:
    """_delete_screenshots: page_*.png を削除し、空になればディレクトリも削除。"""
    shot_dir = tmp_path / "shots"
    shot_dir.mkdir()
    p1 = shot_dir / "page_0001.png"
    p2 = shot_dir / "page_0002.png"
    p1.touch()
    p2.touch()

    main._delete_screenshots(shot_dir)
    assert not shot_dir.exists()


def test_delete_screenshots_keeps_dir_if_other_files(tmp_path: Path) -> None:
    """_delete_screenshots: page_*.png 以外のファイルがある場合はディレクトリを残す。"""
    shot_dir = tmp_path / "shots_kept"
    shot_dir.mkdir()
    p1 = shot_dir / "page_0001.png"
    p1.touch()
    other = shot_dir / "other.txt"
    other.touch()

    main._delete_screenshots(shot_dir)
    assert shot_dir.exists()
    assert not p1.exists()
    assert other.exists()


def test_delete_screenshots_unlink_exception(tmp_path: Path) -> None:
    """_delete_screenshots: ファイル削除で例外が出てもクラッシュしない。"""
    shot_dir = tmp_path / "shots_unlink_err"
    shot_dir.mkdir()
    p1 = shot_dir / "page_0001.png"
    p1.touch()

    with patch.object(Path, "unlink", side_effect=OSError("unlink error")):
        main._delete_screenshots(shot_dir)


def test_delete_screenshots_rmdir_exception(tmp_path: Path) -> None:
    """_delete_screenshots: ディレクトリ削除で例外が出てもクラッシュしない。"""
    shot_dir = tmp_path / "shots_rmdir_err"
    shot_dir.mkdir()

    with patch.object(Path, "rmdir", side_effect=OSError("rmdir error")):
        main._delete_screenshots(shot_dir)


def test_main_keyboard_interrupt() -> None:
    """main: KeyboardInterrupt 発生時に sys.exit(0) で終了。"""
    with patch("main.parse_args"), patch("main.run", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as exc:
            main.main()
        assert exc.value.code == 0


def test_main_general_exception() -> None:
    """main: 予期しない例外発生時に sys.exit(1) で終了。"""
    with patch("main.parse_args"), patch("main.run", side_effect=RuntimeError("unexpected")):
        with pytest.raises(SystemExit) as exc:
            main.main()
        assert exc.value.code == 1


def test_main_entrypoint(tmp_path: Path) -> None:
    """__main__ 実行ブロックのテスト。"""
    from PIL import Image

    img_dir = tmp_path / "entry_imgs"
    img_dir.mkdir()
    valid_png = img_dir / "page_0001.png"
    Image.new("RGB", (10, 10), color="white").save(valid_png)
    out_dir = tmp_path / "entry_out"

    with (
        patch.object(sys, "argv", ["main.py", "--images-dir", str(img_dir), "-o", str(out_dir)]),
        patch("pdf_maker.make_pdf"),
    ):
        runpy.run_module("main", run_name="__main__")

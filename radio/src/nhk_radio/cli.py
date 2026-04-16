"""Command-line entrypoint for the NHK radio downloader."""

import argparse
import subprocess
import sys
from pathlib import Path

from .cache import clear_all_cache
from .core import (
    NHK_GENRES,
    _resolve_program_from_url,
    _url_to_program,
    fetch_program_list,
    get_episode_list,
)
from .downloads import (
    _download_episode_command,
    _program_filename_template,
    _program_output_dir,
    _yt_dlp_command,
    is_episode_downloaded,
    mark_episode_downloaded,
    resolve_episode_downloaded_path,
)
from .gui import browse_programs


def select_program(programs: list[dict]) -> dict | None:
    """番組一覧を表示してユーザーに選択させる"""
    print()
    print("=" * 70)
    print(f"  NHK ラジオ 聞き逃し番組一覧  ({len(programs)} 番組)")
    print("=" * 70)
    for i, p in enumerate(programs, 1):
        date = p.get("display_date", "----")
        title = p.get("display_title", p["title"])
        print(f"  {i:3}. [{date}] {title}")
    print("=" * 70)
    print("  0. キャンセル / URL を直接入力: u")
    print()

    while True:
        try:
            raw = input("番号を入力してください: ").strip()
            if raw == "0":
                return None
            if raw.lower() == "u":
                url = input("番組 URL を入力してください: ").strip()
                program = _url_to_program(url)
                if program is None:
                    print(f"  URL の形式が正しくありません: {url}")
                return program
            n = int(raw)
            if 1 <= n <= len(programs):
                return programs[n - 1]
            print(f"  1〜{len(programs)} または 0 / u を入力してください。")
        except (ValueError, EOFError):
            print("  数字を入力してください。")


def select_episodes(episodes: list[dict]) -> list[dict] | None:
    """エピソード一覧を表示して選択させる"""
    if not episodes:
        print("  利用可能なエピソードがありません。")
        return None

    print()
    print("-" * 70)
    for i, ep in enumerate(episodes, 1):
        date_text = ep.get("display_date", ep["date"][:10] if ep["date"] else "----")
        btime = ep.get("broadcast_time", "")
        dur = ep.get("duration_str", "")
        meta = date_text
        if btime:
            meta = f"{meta} {btime}"
        if dur:
            meta = f"{meta} [{dur}]"
        print(f"  {i:3}. [{meta}] {ep['title']}")
    print("-" * 70)
    print(f"  a. 全件 ({len(episodes)} 件)")
    print("  0. 戻る")
    print()

    while True:
        try:
            raw = input("番号を入力 (複数はカンマ区切り, 例: 1,3,5): ").strip()
            if raw == "0":
                return None
            if raw.lower() == "a":
                return episodes
            selected = []
            valid = True
            for part in raw.split(","):
                n = int(part.strip())
                if 1 <= n <= len(episodes):
                    selected.append(episodes[n - 1])
                else:
                    print(f"  {n} は範囲外です (1〜{len(episodes)})。")
                    valid = False
                    break
            if valid and selected:
                return selected
        except (ValueError, EOFError):
            print("  数字を入力してください。")


def download_episode(
    url: str,
    output_dir: Path,
    filename_template: str,
    *,
    audio_only: bool = True,
    verbose: bool = True,
) -> bool:
    """yt-dlp で1エピソードをダウンロードする"""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = _download_episode_command(url, output_dir, filename_template, audio_only=audio_only)
    if verbose:
        print(f"  → {url}")
    return subprocess.run(cmd).returncode == 0


def download_url_direct(
    url: str,
    output_dir: Path,
    max_items: int | None,
    audio_only: bool,
    genre: str | None = None,
):
    """URL を直接指定してダウンロードする (非対話モード)"""
    program = _resolve_program_from_url(url, genre=genre)
    if program is None:
        print(f"URL の形式が正しくありません: {url}")
        sys.exit(1)

    target_dir = _program_output_dir(output_dir, program)
    target_dir.mkdir(parents=True, exist_ok=True)

    tmpl = str(target_dir / _program_filename_template(program, max_items=bool(max_items)))

    cmd = _yt_dlp_command(
        url,
        tmpl,
        audio_only=audio_only,
        no_playlist=not bool(max_items),
        max_items=max_items,
    )

    print(f"ダウンロード開始: {url}")
    print(f"保存先: {target_dir}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\nダウンロード完了!")
    else:
        print(f"\nエラー (終了コード: {result.returncode})")
        sys.exit(result.returncode)


def _download_selected_episodes(program: dict, episodes: list[dict], output_dir: Path, *, audio_only: bool) -> int:
    target_dir = _program_output_dir(output_dir, program)
    filename_template = _program_filename_template(program)
    downloaded_count = 0
    for episode in episodes:
        title = episode.get("display_title", episode["title"])
        if is_episode_downloaded(output_dir, program, episode):
            print(f"スキップ: {title} (保存済み)")
            continue
        success = download_episode(episode["url"], target_dir, filename_template, audio_only=audio_only)
        if not success:
            print(f"失敗: {title}")
            continue
        downloaded_path = resolve_episode_downloaded_path(output_dir, program, episode)
        mark_episode_downloaded(output_dir, program, episode, downloaded_path)
        downloaded_count += 1
    return downloaded_count


def _interactive_cli_fallback(programs: list[dict], output_dir: Path, *, audio_only: bool) -> None:
    program = select_program(programs)
    if program is None:
        print("終了します。")
        return

    try:
        episodes, _source = get_episode_list(program)
    except Exception as e:
        print(f"エピソード一覧を取得できませんでした: {e}")
        sys.exit(1)

    selected = select_episodes(episodes)
    if not selected:
        print("終了します。")
        return

    completed = _download_selected_episodes(program, selected, output_dir, audio_only=audio_only)
    print(f"完了: {completed} 件")


def interactive_mode(output_dir: Path, genre: str | None = None, *, audio_only: bool = True):
    programs = fetch_program_list(genre)

    if not programs:
        print("番組が見つかりませんでした。")
        sys.exit(1)

    try:
        program, episodes = browse_programs(programs, output_dir, audio_only=audio_only)
    except RuntimeError as e:
        print(f"GUI を起動できませんでした: {e}")
        _interactive_cli_fallback(programs, output_dir, audio_only=audio_only)
        print("終了します。")
        return

    if program and episodes:
        completed = _download_selected_episodes(program, episodes, output_dir, audio_only=audio_only)
        print(f"完了: {completed} 件")
    print("終了します。")


def main():
    parser = argparse.ArgumentParser(
        description="NHK ラジオ 聞き逃し番組ダウンローダー (個人学習用)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方例:
  # 番組一覧から選択 (GUI 専用モード)
  python nhk_radio_dl.py
  # GUI 操作: 上段をクリックしてキャッシュ表示 / ダブルクリックで一覧取得 / 下段で複数選択してダウンロード

  # URL を直接指定してダウンロード
  python nhk_radio_dl.py "https://www.nhk.or.jp/radio/ondemand/detail.html?p=XXXX_01"

  # 直近5件をダウンロード
  python nhk_radio_dl.py <URL> -n 5

  # 番組一覧・エピソード一覧のキャッシュを削除
  python nhk_radio_dl.py --clear-cache

  # 保存先ディレクトリを指定
  python nhk_radio_dl.py -o ~/Downloads/nhk

  # 保存先は downloads/<ジャンル>/<番組名>/YYYYMMDD_<番組名>_<回タイトル>.mp3
        """,
    )
    parser.add_argument("url", nargs="?", help="番組 URL (省略すると GUI モード)")
    parser.add_argument(
        "--output-dir", "-o", default="./downloads", help="保存先ディレクトリ (デフォルト: ./downloads)"
    )
    parser.add_argument("--max-items", "-n", type=int, default=None, help="最大ダウンロード件数")
    parser.add_argument("--keep-video", action="store_true", help="音声変換せず元ファイルを保持する")
    parser.add_argument(
        "--clear-cache", action="store_true", help="番組一覧・エピソード一覧のキャッシュを削除して終了する"
    )
    parser.add_argument(
        "--genre",
        "-g",
        choices=NHK_GENRES,
        default=None,
        metavar=f"{{{','.join(NHK_GENRES)}}}",
        help="番組ジャンルで絞り込む (省略すると全番組)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()

    if args.clear_cache:
        removed = clear_all_cache()
        print(f"キャッシュを削除しました: {removed} 件")
        return

    if args.url:
        download_url_direct(args.url, output_dir, args.max_items, audio_only=not args.keep_video, genre=args.genre)
    else:
        interactive_mode(output_dir, genre=args.genre, audio_only=not args.keep_video)

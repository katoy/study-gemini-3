"""レビュー L3（manifest.py の読み込み）の回帰テスト。"""

import json
from pathlib import Path

import pytest

from nhk_radio import downloads
from nhk_radio.downloads import manifest
from nhk_radio.types import Episode, Program

PROGRAM = Program(
    title="番組A",
    display_title="番組A",
    genre="language",
    genre_label="語学",
    site_id="SITE",
    corner_id="01",
    url="https://example.com/SITE_01",
    display_date="2024-04-15(月)",
)

EPISODE = Episode(
    id="ep-1",
    date="20240415",
    title="第1回",
    display_title="第1回",
    display_date="2024-04-15",
    broadcast_time="",
    duration_str="",
    url="https://example.com/ep1",
)


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    """テストごとにマニフェストのキャッシュを空にする。"""
    manifest._clear_manifest_cache()
    yield
    manifest._clear_manifest_cache()


def _write_manifest(directory: Path, paths: dict[str, str]) -> None:
    """directory にマニフェストを書く。"""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".downloaded.json").write_text(json.dumps({"paths": paths}), encoding="utf-8")


def test_load_download_manifest_returns_copy_of_cache(tmp_path: Path) -> None:
    """呼び出し側が戻り値を書き換えても、キャッシュの内容は変わらない。"""
    _write_manifest(downloads.program_output_dir(tmp_path, PROGRAM), {"ep-1": "a.mp3"})

    first = manifest._load_download_manifest(PROGRAM, tmp_path)
    first["ep-1"] = "changed.mp3"
    first["ep-2"] = "added.mp3"
    second = manifest._load_download_manifest(PROGRAM, tmp_path)

    assert second == {"ep-1": "a.mp3"}


def test_load_download_manifest_cache_hit_returns_copy(tmp_path: Path) -> None:
    """キャッシュから返した値を書き換えても、次の読み込みに影響しない。"""
    _write_manifest(downloads.program_output_dir(tmp_path, PROGRAM), {"ep-1": "a.mp3"})
    manifest._load_download_manifest(PROGRAM, tmp_path)

    hit = manifest._load_download_manifest(PROGRAM, tmp_path)
    hit.clear()

    assert manifest._load_download_manifest(PROGRAM, tmp_path) == {"ep-1": "a.mp3"}


def test_load_download_manifest_resolves_legacy_relative_path_against_legacy_dir(tmp_path: Path) -> None:
    """旧ディレクトリのマニフェストの相対パスは、旧ディレクトリを基準にした絶対パスにする。"""
    legacy_dir = tmp_path / "語学" / "番組A"
    _write_manifest(legacy_dir, {"ep-1": "old.mp3"})

    saved_paths = manifest._load_download_manifest(PROGRAM, tmp_path)

    assert saved_paths == {"ep-1": str(legacy_dir / "old.mp3")}


def test_load_download_manifest_keeps_primary_relative_path(tmp_path: Path) -> None:
    """現在の番組ディレクトリのマニフェストの相対パスは、そのまま返す。"""
    _write_manifest(downloads.program_output_dir(tmp_path, PROGRAM), {"ep-1": "new.mp3"})

    assert manifest._load_download_manifest(PROGRAM, tmp_path) == {"ep-1": "new.mp3"}


def test_find_episode_downloaded_path_finds_file_recorded_in_legacy_manifest(tmp_path: Path) -> None:
    """旧ディレクトリのマニフェストに記録されたファイルを、旧ディレクトリから見つける。"""
    legacy_dir = tmp_path / "語学" / "番組A"
    # パターン照合では見つからない名前にして、マニフェスト経由で見つかることを確かめる
    saved = legacy_dir / "renamed.mp3"
    _write_manifest(legacy_dir, {downloads._episode_key(EPISODE): "renamed.mp3"})
    saved.write_text("x", encoding="utf-8")

    assert downloads.find_episode_downloaded_path(tmp_path, PROGRAM, EPISODE) == saved

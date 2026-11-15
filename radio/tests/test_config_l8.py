"""レビュー L8（config.py）の回帰テスト。"""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from nhk_radio import config


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """キャッシュと設定のディレクトリを tmp_path の下に向ける。"""
    cache_dir = tmp_path / "cache"
    config_dir = tmp_path / "config"
    monkeypatch.setenv("NHK_RADIO_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("NHK_RADIO_CONFIG_DIR", str(config_dir))
    return cache_dir, config_dir


def test_migrate_legacy_ui_settings_logs_failure(dirs: tuple[Path, Path], caplog: pytest.LogCaptureFixture) -> None:
    """旧設定の移行に失敗したら、握りつぶさずに警告を出す。"""
    cache_dir, _config_dir = dirs
    cache_dir.mkdir(parents=True)
    (cache_dir / "ui_settings.json").write_text("{}", encoding="utf-8")

    with (
        patch.object(Path, "replace", side_effect=OSError("disk full")),
        caplog.at_level(logging.WARNING, logger="nhk_radio.config"),
    ):
        config._migrate_legacy_ui_settings()

    assert "移行に失敗" in caplog.text
    assert "disk full" in caplog.text


def test_save_ui_settings_keeps_unknown_keys(dirs: tuple[Path, Path]) -> None:
    """新しい版が書いた未知のキーを、保存し直しても消さない。"""
    _cache_dir, config_dir = dirs
    config_dir.mkdir(parents=True)
    path = config_dir / "ui_settings.json"
    path.write_text(json.dumps({"theme": "dark", "future_option": {"a": 1}, "help_seen_version": 3}), encoding="utf-8")

    config._save_ui_settings("light", 12, ["検索"])

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["future_option"] == {"a": 1}
    assert saved["help_seen_version"] == 3
    assert saved["theme"] == "light"
    assert saved["font_size_pt"] == 12
    assert saved["program_search_history"] == ["検索"]


def test_save_ui_settings_without_existing_file(dirs: tuple[Path, Path]) -> None:
    """設定ファイルが無ければ、既知のキーだけで作る。"""
    _cache_dir, config_dir = dirs

    config._save_ui_settings("dark", 10)

    saved = json.loads((config_dir / "ui_settings.json").read_text(encoding="utf-8"))
    assert saved == {"theme": "dark", "font_size_pt": 10, "program_search_history": []}

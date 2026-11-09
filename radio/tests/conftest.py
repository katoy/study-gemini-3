"""テスト全体で共有するフィクスチャ。"""

import os
import sys
from collections.abc import Iterator

import pytest

# init プロセス (pid 1) のプロセスグループ ID 以下は送信対象にしない
_MIN_SAFE_PGID = 1


@pytest.fixture(autouse=True)
def _guard_killpg(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """MagicMock の pid (整数化すると 1) 経由でテストランナー自身を killpg しないよう防ぐ。

    Popen をモックしたテストでは process.pid が MagicMock になり、os.getpgid(1) の結果に
    SIGTERM が送られて CI ジョブごと停止することがあるため、危険な pgid への送信を拒否する。
    """
    if sys.platform == "win32":
        yield
        return
    real_killpg = os.killpg
    own_pgid = os.getpgrp()

    def _safe_killpg(pgid: int, sig: int) -> None:
        if pgid <= _MIN_SAFE_PGID or pgid == own_pgid:
            raise PermissionError(f"テスト中は pgid {pgid} への killpg を禁止しています")
        real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", _safe_killpg)
    yield

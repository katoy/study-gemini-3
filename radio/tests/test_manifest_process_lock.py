"""レビュー L3（プロセスをまたぐマニフェストのロック）の回帰テスト。"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from nhk_radio import _io, downloads
from nhk_radio.types import Program

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
EPISODES_PER_PROCESS = 40

# 別プロセスで、エピソードを 1 件ずつマニフェストに記録する
WRITER_SCRIPT = """
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from nhk_radio import downloads
from nhk_radio.types import Episode, Program

output_dir = Path(sys.argv[2])
prefix = sys.argv[3]
count = int(sys.argv[4])
program = Program(title="P", display_title="P", display_date="", site_id="S", corner_id="01", url="U")
program_dir = downloads.program_output_dir(output_dir, program)
program_dir.mkdir(parents=True, exist_ok=True)
for i in range(count):
    episode = Episode(id=f"{prefix}{i}", title="t", display_title="t", date="20240415",
                      display_date="", broadcast_time="", duration_str="", url="")
    path = program_dir / f"{prefix}{i}.mp3"
    path.write_text("x")
    downloads.mark_episode_downloaded(output_dir, program, episode, path)
"""


def test_concurrent_processes_do_not_lose_manifest_entries(tmp_path: Path) -> None:
    """2 つのプロセスが同時にマニフェストへ記録しても、記録が失われない。"""
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", WRITER_SCRIPT, str(SRC_DIR), str(tmp_path), prefix, str(EPISODES_PER_PROCESS)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for prefix in ("a", "b")
    ]
    for proc in procs:
        _stdout, stderr = proc.communicate(timeout=120)
        assert proc.returncode == 0, stderr

    program = Program(title="P", display_title="P", display_date="", site_id="S", corner_id="01", url="U")
    manifest_path = downloads.program_output_dir(tmp_path, program) / ".downloaded.json"
    paths = json.loads(manifest_path.read_text(encoding="utf-8"))["paths"]

    assert len(paths) == EPISODES_PER_PROCESS * 2


def test_file_lock_blocks_other_holder(tmp_path: Path) -> None:
    """ロックを持っている間、別の取得者は待たされる。"""
    lock_path = tmp_path / "x.lock"
    events: list[str] = []

    def other() -> None:
        with _io.file_lock(lock_path):
            events.append("other")

    with _io.file_lock(lock_path):
        thread = threading.Thread(target=other)
        thread.start()
        time.sleep(0.3)
        events.append("holder")
    thread.join(timeout=5)

    assert events == ["holder", "other"]


def test_file_lock_is_reentrant_in_same_thread(tmp_path: Path) -> None:
    """同じスレッドで入れ子に取得しても、自分自身を待って止まらない。"""
    lock_path = tmp_path / "x.lock"
    with _io.file_lock(lock_path), _io.file_lock(lock_path):
        pass

"""Download management logic decoupled from UI."""

import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..downloads import (
    _episode_key,
    cleanup_partial_episode_files,
    download_episode_command,
    program_output_dir,
    run_yt_dlp_subprocess,
    sync_episode_download_history,
)
from ..downloads.cleanup import BACKUP_MIN_AGE_SECONDS
from ..types import Episode, Program

logger = logging.getLogger(__name__)

# DL 中は退避ファイルの mtime をこの間隔で更新し、別プロセスの起動時整理で復元されないようにする
BACKUP_HEARTBEAT_INTERVAL_SECONDS = BACKUP_MIN_AGE_SECONDS / 5


class DownloadManager:
    """Manages background download processes and their lifecycle."""

    def __init__(
        self,
        output_dir: Path,
        audio_only: bool,
        on_result: Callable[[str, str, Program, Episode, Any], None],
    ):
        self.output_dir = output_dir
        self.audio_only = audio_only
        self.on_result = on_result  # (type, episode_key, program, episode, data)

        self.processes: dict[str, subprocess.Popen | None] = {}
        self.cancel_events: dict[str, threading.Event] = {}
        self.active_program_dirs: dict[str, Path] = {}
        self.process_lock = threading.Lock()

        self.started_count = 0
        self.finished_count = 0

    def start_download(self, program: Program, episode: Episode) -> str:
        """Starts a background download for the given episode."""
        episode_key = _episode_key(episode)

        with self.process_lock:
            if episode_key in self.processes:
                return episode_key  # Already downloading

            cancel_event = threading.Event()
            self.cancel_events[episode_key] = cancel_event
            self.processes[episode_key] = None
            self.active_program_dirs[episode_key] = program_output_dir(self.output_dir, program)
            self.started_count += 1

        thread = threading.Thread(
            target=self._download_worker,
            args=(program, episode, episode_key, cancel_event),
            daemon=True,
        )
        thread.start()
        return episode_key

    def cancel_download(self, episode_key: str):
        """Signals a download to stop and terminates the process."""
        with self.process_lock:
            if episode_key in self.cancel_events:
                self.cancel_events[episode_key].set()

            process = self.processes.get(episode_key)
            if process:
                from ..downloads.runner import _terminate_process

                _terminate_process(process)

    def cancel_all(self):
        """Cancels all active downloads."""
        with self.process_lock:
            for key, cancel_event in list(self.cancel_events.items()):
                cancel_event.set()
                process = self.processes.get(key)
                if process:
                    from ..downloads.runner import _terminate_process

                    _terminate_process(process)

    def is_active(self) -> bool:
        """Returns True if any downloads are currently running."""
        with self.process_lock:
            return len(self.processes) > 0

    def get_active_program_dirs(self) -> set[Path]:
        """現在ダウンロード進行中の番組ディレクトリのセットを返す (2-2)。"""
        with self.process_lock:
            return set(self.active_program_dirs.values())

    @staticmethod
    def _backup_heartbeat(backup_path: Path, stop_event: threading.Event) -> None:
        """DL 中、退避ファイルの mtime を定期更新して「使用中」であることを示す。"""
        while not stop_event.wait(BACKUP_HEARTBEAT_INTERVAL_SECONDS):
            try:
                os.utime(backup_path)
            except OSError as e:
                logger.debug(f"退避ファイルの mtime 更新に失敗: {backup_path} ({e})")
                return

    def _download_worker(
        self,
        program: Program,
        episode: Episode,
        episode_key: str,
        cancel_event: threading.Event,
    ):
        """Background thread worker for a single download."""
        with self.process_lock:
            if episode_key not in self.processes:
                self.processes[episode_key] = None

        success = False
        captured_output_path: list[Path] = []
        backup_path: Path | None = None
        existing_path: Path | None = None
        heartbeat_stop = threading.Event()
        try:
            target_dir = program_output_dir(self.output_dir, program)
            target_dir.mkdir(parents=True, exist_ok=True)

            # 上書き時にダウンロード失敗やキャンセルで元ファイルを失わないよう、事前退避 (G4, 2-1)
            from ..downloads import BACKUP_SUFFIX, find_episode_downloaded_path

            existing_path = find_episode_downloaded_path(self.output_dir, program, episode, audio_only=self.audio_only)
            if existing_path and existing_path.exists():
                try:
                    backup_path = existing_path.with_name(existing_path.name + BACKUP_SUFFIX)
                    if backup_path.exists():
                        with suppress(OSError):
                            backup_path.unlink()
                    existing_path.replace(backup_path)
                    # rename は mtime を保持するため、退避時刻で更新して起動時整理の経過時間判定を効かせる
                    os.utime(backup_path)
                except OSError as e:
                    logger.warning(f"既存ファイルの退避に失敗: {e}")
                    backup_path = None

            if backup_path:
                threading.Thread(
                    target=self._backup_heartbeat, args=(backup_path, heartbeat_stop), daemon=True
                ).start()

            from ..downloads import program_filename_template
            filename_template = program_filename_template(program)

            cmd = download_episode_command(
                episode.url,
                target_dir,
                filename_template,
                audio_only=self.audio_only,
                force_overwrites=True,
            )

            def on_progress(percent: float | None, eta: str | None, status: str | None) -> None:
                if percent is not None:
                    self.on_result("progress", episode_key, program, episode, (percent, eta or "", status or ""))

            def on_proc(p: subprocess.Popen) -> None:
                with self.process_lock:
                    if episode_key in self.processes:
                        self.processes[episode_key] = p

            def on_output_path(p: Path) -> None:
                captured_output_path.append(p)

            success = run_yt_dlp_subprocess(
                cmd,
                on_progress=on_progress,
                cancel_event=cancel_event,
                on_process=on_proc,
                on_output_path=on_output_path,
            )
            success = success and not cancel_event.is_set()

        except Exception as e:
            logger.error(f"Download thread error: {e}")
            success = False

        finally:
            heartbeat_stop.set()
            # 退避ファイルのクリーンアップまたは復元 (G4)
            if backup_path:
                if success:
                    with suppress(OSError):
                        backup_path.unlink()
                else:
                    with suppress(OSError):
                        if backup_path.exists() and existing_path:
                            backup_path.replace(existing_path)

            terminal_event_data: Any = None
            if success:
                if captured_output_path and captured_output_path[-1].exists():
                    actual_path = captured_output_path[-1]
                    from ..downloads import mark_episode_downloaded
                    mark_episode_downloaded(self.output_dir, program, episode, actual_path)
                    terminal_event_data = actual_path
                else:
                    # 履歴同期（最大3回試行、指数バックオフ）
                    # 最初は即座、失敗時に 0.1秒・0.2秒 待機
                    for delay in [0, 0.1, 0.2]:
                        terminal_event_data = sync_episode_download_history(
                            self.output_dir, program, episode, audio_only=self.audio_only
                        )
                        if terminal_event_data:
                            break
                        if delay > 0:
                            time.sleep(delay)
                res_type = "done_one"
            else:
                if not cancel_event.is_set():
                    with suppress(Exception):
                        cleanup_partial_episode_files(self.output_dir, program, episode)
                res_type = "cancelled_one" if cancel_event.is_set() else "failed_one"

            self.on_result(res_type, episode_key, program, episode, terminal_event_data)

            with self.process_lock:
                self.processes.pop(episode_key, None)
                self.cancel_events.pop(episode_key, None)
                self.active_program_dirs.pop(episode_key, None)
                self.finished_count += 1

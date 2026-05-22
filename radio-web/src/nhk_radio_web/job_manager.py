"""ダウンロードジョブ管理とキューイング。"""

import asyncio
import logging
import uuid
from typing import Any

from nhk_radio_web.config import _default_download_dir
from nhk_radio_web.constants import HTTP_RETRY_BACKOFF_BASE, HTTP_RETRY_MAX_ATTEMPTS
from nhk_radio_web.downloads import (
    _download_episode_command,
    _parse_yt_dlp_progress,
    _program_filename_template,
    _program_output_dir,
    sync_episode_download_history,
)
from nhk_radio_web.types import Episode, Progress, Program

logger = logging.getLogger(__name__)


class JobManager:
    """ダウンロードジョブの並行実行・キュー管理。

    最大同時実行数は max_concurrent で制御。
    超過分はキューで待機。
    """

    def __init__(self, max_concurrent: int = 2):
        """Initialize JobManager.

        Args:
            max_concurrent: 最大同時実行ダウンロード数
        """
        self.max_concurrent = max_concurrent
        self._jobs: dict[str, dict[str, Any]] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._task_map: dict[str, asyncio.Task] = {}
        self._subscribers: set[asyncio.Queue] = set()

    def enqueue(self, program: Program, episode: Episode) -> str:
        """ダウンロード job を登録し job_id を返す。

        Args:
            program: 番組情報
            episode: エピソード情報

        Returns:
            job_id: 登録されたジョブの一意識別子
        """
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            "status": "pending",
            "program": program,
            "episode": episode,
            "error": "",
            "progress": None,
        }
        return job_id

    async def start(self, job_id: str) -> None:
        """ジョブ実行を開始する (Semaphore で待機)。

        Args:
            job_id: 実行対象ジョブ ID
        """
        if job_id not in self._jobs:
            raise ValueError(f"Job {job_id} not found")

        async def _run_with_semaphore():
            async with self._semaphore:
                await self._run_download(job_id)

        task = asyncio.create_task(_run_with_semaphore())
        self._task_map[job_id] = task

    async def cancel(self, job_id: str) -> None:
        """実行中ジョブをキャンセルする。

        Args:
            job_id: キャンセル対象ジョブ ID
        """
        if job_id not in self._jobs:
            raise ValueError(f"Job {job_id} not found")

        job = self._jobs[job_id]
        if job["status"] not in ("pending", "downloading"):
            return

        # Task をキャンセル
        if job_id in self._task_map:
            task = self._task_map[job_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._jobs[job_id]["status"] = "cancelled"
        self._jobs[job_id]["error"] = "ユーザーがキャンセルしました"
        logger.info(f"Job {job_id} cancelled by user")

    async def cancel_all(self) -> None:
        """全実行中ジョブをキャンセルする。"""
        job_ids = [jid for jid, j in self._jobs.items() if j["status"] in ("pending", "downloading")]
        for job_id in job_ids:
            await self.cancel(job_id)

    def status_snapshot(self, job_id: str) -> dict[str, Any] | None:
        """ジョブの現在状態を返す。

        Args:
            job_id: 対象ジョブ ID

        Returns:
            ジョブ情報辞書、またはジョブが見つからない場合は None
        """
        return self._jobs.get(job_id)

    def all_jobs(self) -> dict[str, dict[str, Any]]:
        """全ジョブのスナップショットを返す。"""
        return dict(self._jobs)

    def subscribe(self) -> asyncio.Queue:
        """ジョブイベントを受け取るキューを登録して返す。

        Returns:
            asyncio.Queue: ジョブ状態変更を受け取るキュー
        """
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """キューの登録を解除する。

        Args:
            queue: 登録を解除するキュー
        """
        self._subscribers.discard(queue)

    async def _notify(self, job_id: str) -> None:
        """全購読者にジョブ状態変更を通知する。

        Args:
            job_id: ジョブ ID
        """
        job = self._jobs.get(job_id)
        if not job:
            return
        payload = {
            "job_id": job_id,
            "status": job["status"],
            "title": job["episode"].title,
            "error": job.get("error", ""),
            "progress": (
                {"percent": job["progress"].percent, "eta": job["progress"].eta}
                if job.get("progress")
                else None
            ),
        }
        for q in list(self._subscribers):
            await q.put(payload)

    async def _run_download(self, job_id: str) -> None:
        """バックグラウンドで yt-dlp を実行してエピソードをダウンロードする。

        リトライ機能付き (HTTP エラーのみ)。

        Args:
            job_id: ダウンロード対象ジョブ ID
        """
        job = self._jobs[job_id]
        program: Program = job["program"]
        episode: Episode = job["episode"]

        self._jobs[job_id]["status"] = "downloading"
        await self._notify(job_id)
        output_dir = _default_download_dir()
        program_dir = _program_output_dir(output_dir, program)
        program_dir.mkdir(parents=True, exist_ok=True)
        filename_template = _program_filename_template(program)
        cmd = _download_episode_command(episode.url, program_dir, filename_template)

        # リトライループ
        for attempt in range(1, HTTP_RETRY_MAX_ATTEMPTS + 1):
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                # stdout をリアルタイムで読んで進捗を抽出
                if proc.stdout:
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="replace")
                        percent, eta, status = _parse_yt_dlp_progress(text)
                        if percent is not None or eta is not None:
                            self._jobs[job_id]["progress"] = Progress(percent=percent, eta=eta, status=status)
                            await self._notify(job_id)

                await proc.wait()
                if proc.returncode == 0:
                    file_path = sync_episode_download_history(output_dir, program, episode)
                    self._jobs[job_id]["status"] = "done"
                    self._jobs[job_id]["progress"] = None
                    if file_path:
                        self._jobs[job_id]["file_path"] = str(file_path)
                    await self._notify(job_id)
                    return
                # HTTP エラー系は リトライ対象
                if attempt < HTTP_RETRY_MAX_ATTEMPTS:
                    wait_time = HTTP_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(f"Job {job_id} 再試行 {attempt}/{HTTP_RETRY_MAX_ATTEMPTS} ({wait_time}秒待機)")
                    await asyncio.sleep(wait_time)
                    continue
                # 最後の試行で失敗
                self._jobs[job_id]["status"] = "error"
                self._jobs[job_id]["error"] = f"yt-dlp 終了コード: {proc.returncode}"
                self._jobs[job_id]["progress"] = None
                await self._notify(job_id)
                return
            except asyncio.CancelledError:
                # キャンセルされた場合はすでに status が set されているはず
                logger.info(f"Job {job_id} was cancelled during download")
                raise
            except Exception as e:
                if attempt < HTTP_RETRY_MAX_ATTEMPTS:
                    wait_time = HTTP_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(f"Job {job_id} エラーで再試行 {attempt}/{HTTP_RETRY_MAX_ATTEMPTS}: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                # 最後の試行で失敗
                self._jobs[job_id]["status"] = "error"
                self._jobs[job_id]["error"] = str(e)
                self._jobs[job_id]["progress"] = None
                await self._notify(job_id)
                logger.error(f"ダウンロードエラー (job={job_id}, 試行数={HTTP_RETRY_MAX_ATTEMPTS}): {e}")
                return

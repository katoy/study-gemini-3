"""JobManager テスト。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nhk_radio_web.job_manager import JobManager
from nhk_radio_web.types import Episode, Program


@pytest.fixture
def job_manager():
    """JobManager インスタンス。"""
    return JobManager(max_concurrent=2)


@pytest.fixture
def sample_program():
    """テスト用番組。"""
    return Program(
        title="テスト番組",
        display_title="テスト番組",
        display_date="2026-05-16",
        site_id="site1",
        corner_id="corner1",
        url="https://example.com",
    )


@pytest.fixture
def sample_episode():
    """テスト用エピソード。"""
    return Episode(
        id="ep-1",
        title="テストエピソード",
        display_title="テストエピソード",
        date="20260516",
        display_date="2026-05-16",
        broadcast_time="10:00",
        duration_str="30分",
        url="https://example.com/episode",
    )


def test_enqueue_creates_job(job_manager, sample_program, sample_episode):
    """enqueue がジョブを登録し job_id を返す。"""
    job_id = job_manager.enqueue(sample_program, sample_episode)

    assert isinstance(job_id, str)
    assert len(job_id) > 0

    job = job_manager.status_snapshot(job_id)
    assert job is not None
    assert job["status"] == "pending"
    assert job["program"] == sample_program
    assert job["episode"] == sample_episode
    assert job["error"] == ""


def test_status_snapshot_returns_none_for_missing_job(job_manager):
    """status_snapshot は存在しないジョブに対して None を返す。"""
    result = job_manager.status_snapshot("nonexistent")
    assert result is None


def test_all_jobs_returns_all(job_manager, sample_program, sample_episode):
    """all_jobs が全ジョブを返す。"""
    job_id_1 = job_manager.enqueue(sample_program, sample_episode)
    job_id_2 = job_manager.enqueue(sample_program, sample_episode)

    all_jobs = job_manager.all_jobs()
    assert len(all_jobs) == 2
    assert job_id_1 in all_jobs
    assert job_id_2 in all_jobs


@pytest.mark.asyncio
async def test_start_updates_status_to_downloading(job_manager, sample_program, sample_episode):
    """start を呼ぶと status が downloading に変わる。"""
    job_id = job_manager.enqueue(sample_program, sample_episode)

    with patch("nhk_radio_web.job_manager.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=None)
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        with patch("nhk_radio_web.job_manager._default_download_dir") as mock_dir:
            mock_dir.return_value = "/tmp/test"

            with patch("nhk_radio_web.job_manager._program_output_dir") as mock_out:
                mock_path = MagicMock()
                mock_path.mkdir = MagicMock()
                mock_out.return_value = mock_path

                with patch("nhk_radio_web.job_manager._program_filename_template") as mock_tpl:
                    mock_tpl.return_value = "test_{title}"

                    with patch("nhk_radio_web.job_manager._download_episode_command") as mock_cmd:
                        mock_cmd.return_value = ["echo", "test"]

                        with patch("nhk_radio_web.job_manager.mark_episode_downloaded") as mock_mark:
                            await job_manager.start(job_id)
                            await asyncio.sleep(0.1)  # wait for task

                            job = job_manager.status_snapshot(job_id)
                            assert job["status"] == "done"


@pytest.mark.asyncio
async def test_cancel_sets_status_and_error(job_manager, sample_program, sample_episode):
    """cancel がジョブをキャンセルし status と error をセットする。"""
    job_id = job_manager.enqueue(sample_program, sample_episode)

    with patch("nhk_radio_web.job_manager.asyncio.create_subprocess_exec") as mock_exec:
        # 実行を続ける subprocess をモック (キャンセル対象)
        mock_proc = AsyncMock()

        async def slow_wait():
            await asyncio.sleep(10)  # long wait

        mock_proc.wait = slow_wait
        mock_proc.returncode = None
        mock_exec.return_value = mock_proc

        with patch("nhk_radio_web.job_manager._default_download_dir"):
            with patch("nhk_radio_web.job_manager._program_output_dir") as mock_out:
                mock_path = MagicMock()
                mock_path.mkdir = MagicMock()
                mock_out.return_value = mock_path

                with patch("nhk_radio_web.job_manager._program_filename_template"):
                    with patch("nhk_radio_web.job_manager._download_episode_command"):
                        await job_manager.start(job_id)
                        await asyncio.sleep(0.05)

                        await job_manager.cancel(job_id)

                        job = job_manager.status_snapshot(job_id)
                        assert job["status"] == "cancelled"
                        assert "キャンセル" in job["error"]


@pytest.mark.asyncio
async def test_cancel_raises_for_missing_job(job_manager):
    """cancel は存在しないジョブに対して ValueError を raise する。"""
    with pytest.raises(ValueError, match="not found"):
        await job_manager.cancel("nonexistent")


@pytest.mark.asyncio
async def test_cancel_all_cancels_all_pending(job_manager, sample_program, sample_episode):
    """cancel_all が全 pending ジョブをキャンセルする。"""
    job_id_1 = job_manager.enqueue(sample_program, sample_episode)
    job_id_2 = job_manager.enqueue(sample_program, sample_episode)

    await job_manager.cancel_all()

    job_1 = job_manager.status_snapshot(job_id_1)
    job_2 = job_manager.status_snapshot(job_id_2)
    assert job_1["status"] == "cancelled"
    assert job_2["status"] == "cancelled"


@pytest.mark.asyncio
async def test_semaphore_limits_concurrent_downloads(sample_program, sample_episode):
    """Semaphore が最大同時実行数を制限する。"""
    job_manager = JobManager(max_concurrent=1)

    job_id_1 = job_manager.enqueue(sample_program, sample_episode)
    job_id_2 = job_manager.enqueue(sample_program, sample_episode)

    concurrent_count = 0
    max_concurrent_observed = 0

    async def mock_subprocess(*args, **kwargs):
        nonlocal concurrent_count, max_concurrent_observed
        concurrent_count += 1
        max_concurrent_observed = max(max_concurrent_observed, concurrent_count)
        await asyncio.sleep(0.05)
        concurrent_count -= 1

        class MockProc:
            returncode = 0

            async def wait(self):
                pass

        return MockProc()

    with patch("nhk_radio_web.job_manager.asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        with patch("nhk_radio_web.job_manager._default_download_dir"):
            with patch("nhk_radio_web.job_manager._program_output_dir") as mock_out:
                mock_path = MagicMock()
                mock_path.mkdir = MagicMock()
                mock_out.return_value = mock_path

                with patch("nhk_radio_web.job_manager._program_filename_template"):
                    with patch("nhk_radio_web.job_manager._download_episode_command"):
                        with patch("nhk_radio_web.job_manager.mark_episode_downloaded"):
                            await job_manager.start(job_id_1)
                            await job_manager.start(job_id_2)
                            await asyncio.sleep(0.2)

    # max_concurrent=1 なので、同時実行は最大 1
    assert max_concurrent_observed <= 1


@pytest.mark.asyncio
async def test_start_raises_for_missing_job(job_manager):
    """start は存在しないジョブに対して ValueError を raise する。"""
    with pytest.raises(ValueError, match="not found"):
        await job_manager.start("nonexistent")


@pytest.mark.asyncio
async def test_cancel_already_done_job_returns_early(job_manager, sample_program, sample_episode):
    """done ジョブに cancel を呼んでも何もしない (early return)。"""
    job_id = job_manager.enqueue(sample_program, sample_episode)
    job_manager._jobs[job_id]["status"] = "done"

    # cancel を呼んでも ValueError が raise されない
    await job_manager.cancel(job_id)
    # status は done のまま
    assert job_manager.status_snapshot(job_id)["status"] == "done"


@pytest.mark.asyncio
async def test_run_download_failure_returncode(job_manager, sample_program, sample_episode):
    """returncode != 0 の場合、リトライ後にエラー status を設定する。"""
    job_id = job_manager.enqueue(sample_program, sample_episode)

    with patch("nhk_radio_web.job_manager.asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=None)
        mock_proc.returncode = 1  # failure
        mock_exec.return_value = mock_proc

        with patch("nhk_radio_web.job_manager._default_download_dir"):
            with patch("nhk_radio_web.job_manager._program_output_dir") as mock_out:
                mock_path = MagicMock()
                mock_path.mkdir = MagicMock()
                mock_out.return_value = mock_path

                with patch("nhk_radio_web.job_manager._program_filename_template"):
                    with patch("nhk_radio_web.job_manager._download_episode_command"):
                        await job_manager.start(job_id)
                        # リトライが 3 回実行される (1 + 1 + 4 = 6 秒の指数バックオフ)
                        await asyncio.sleep(7)

                        job = job_manager.status_snapshot(job_id)
                        assert job["status"] == "error"
                        assert "終了コード: 1" in job["error"]
                        # リトライは 3 回試行されたはず
                        assert mock_exec.call_count == 3


@pytest.mark.asyncio
async def test_run_download_exception_handling(job_manager, sample_program, sample_episode):
    """_run_download で例外が発生した場合、リトライ後にエラー status を設定する。"""
    job_id = job_manager.enqueue(sample_program, sample_episode)

    with patch("nhk_radio_web.job_manager.asyncio.create_subprocess_exec") as mock_exec:
        mock_exec.side_effect = RuntimeError("subprocess exec failed")

        with patch("nhk_radio_web.job_manager._default_download_dir"):
            with patch("nhk_radio_web.job_manager._program_output_dir") as mock_out:
                mock_path = MagicMock()
                mock_path.mkdir = MagicMock()
                mock_out.return_value = mock_path

                with patch("nhk_radio_web.job_manager._program_filename_template"):
                    with patch("nhk_radio_web.job_manager._download_episode_command"):
                        await job_manager.start(job_id)
                        # リトライが 3 回実行される (1 + 2 + 4 = 7 秒の指数バックオフ)
                        await asyncio.sleep(8)

                        job = job_manager.status_snapshot(job_id)
                        assert job["status"] == "error"
                        assert "subprocess exec failed" in job["error"]
                        # リトライは 3 回試行されたはず
                        assert mock_exec.call_count == 3


@pytest.mark.asyncio
async def test_subscribe_returns_queue(job_manager):
    """subscribe がキューを返し、購読者リストに追加される。"""
    q = job_manager.subscribe()
    assert isinstance(q, asyncio.Queue)
    assert q in job_manager._subscribers


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue(job_manager):
    """unsubscribe がキューを購読者リストから削除する。"""
    q = job_manager.subscribe()
    assert q in job_manager._subscribers
    job_manager.unsubscribe(q)
    assert q not in job_manager._subscribers


@pytest.mark.asyncio
async def test_notify_sends_to_subscribers(job_manager, sample_program, sample_episode):
    """_notify が全購読者にジョブ状態変更を送信する。"""
    job_id = job_manager.enqueue(sample_program, sample_episode)
    job_manager._jobs[job_id]["status"] = "downloading"

    q = job_manager.subscribe()
    await job_manager._notify(job_id)

    payload = await asyncio.wait_for(q.get(), timeout=1.0)
    assert payload["job_id"] == job_id
    assert payload["status"] == "downloading"
    assert payload["title"] == sample_episode.title
    assert payload["error"] == ""


@pytest.mark.asyncio
async def test_notify_missing_job_returns_early(job_manager):
    """_notify は存在しないジョブで early return する。"""
    q = job_manager.subscribe()
    await job_manager._notify("nonexistent-job")
    # キューに何も入らないはず
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.1)

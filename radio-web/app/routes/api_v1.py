"""API v1 ルート (/api/v1/*)。"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status

from nhk_radio_web import __version__
from nhk_radio_web.cache import get_cache_status
from nhk_radio_web.config import _default_download_dir
from nhk_radio_web.job_manager import JobManager
from nhk_radio_web.search import filter_episodes, filter_programs
from nhk_radio_web.types import Program

from ..api_models import (
    CacheStatusData,
    CacheStatusResponse,
    CountMeta,
    DownloadJobCreateRequest,
    DownloadJobListMeta,
    DownloadJobListResponse,
    DownloadJobResponse,
    EpisodeDetailMeta,
    EpisodeDetailResponse,
    EpisodeListMeta,
    EpisodeListResponse,
    GenreData,
    GenreListResponse,
    HealthData,
    HealthResponse,
    MetaData,
    MetaResponse,
    ProgramDetailResponse,
    ProgramFiltersMeta,
    ProgramListMeta,
    ProgramListResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)
from ._shared import (
    UNCLASSIFIED_GENRE,
    JobStatusQuery,
    LimitQuery,
    _all_programs_dep,
    _build_genre_options,
    _create_download_job_from_models,
    _episode_to_api_data,
    _from_public_genre_id,
    _genre_counts,
    _job_manager_dep,
    _job_to_api_data,
    _matches_genre,
    _program_dep,
    _program_to_api_data,
    _settings_payload,
    _to_public_genre_id,
    _update_storage_limit,
    get_episode_list,
    is_episode_downloaded,
    load_storage_limit,
)
from .internal import download_file

api_v1_router = APIRouter(prefix="/api/v1", tags=["api-v1"])


@api_v1_router.get("/health", response_model=HealthResponse)
async def api_v1_health():
    return HealthResponse(data=HealthData(status="ok", version=__version__))


@api_v1_router.get("/meta", response_model=MetaResponse)
async def api_v1_meta(request: Request):
    app = request.app
    return MetaResponse(
        data=MetaData(
            name="radio-web",
            version=__version__,
            docs_url=getattr(app, "docs_url", None),
            openapi_url=getattr(app, "openapi_url", None),
            redoc_url=getattr(app, "redoc_url", None),
            capabilities=[
                "genres",
                "programs",
                "episodes",
                "download_jobs",
                "settings",
                "websocket_jobs",
            ],
        )
    )


@api_v1_router.get("/genres", response_model=GenreListResponse)
async def api_v1_genres(all_programs: Annotated[list[Program], Depends(_all_programs_dep)]):
    genre_counts = _genre_counts(all_programs)
    options = _build_genre_options()
    return GenreListResponse(
        data=[
            GenreData(
                id=_to_public_genre_id(option["value"]),
                label=option["label"],
                count=genre_counts.get(option["value"], 0),
                is_unclassified=option["value"] == UNCLASSIFIED_GENRE,
            )
            for option in _build_genre_options()
            if option["value"]
        ],
        meta=CountMeta(count=len(options) - 1),
    )


@api_v1_router.get("/programs", response_model=ProgramListResponse)
async def api_v1_programs(
    all_programs: Annotated[list[Program], Depends(_all_programs_dep)],
    genre: Annotated[str, Query(description="ジャンル ID。未分類は unclassified")] = "",
    q: Annotated[str, Query(max_length=200)] = "",
    limit: LimitQuery = None,
):
    effective_genre = _from_public_genre_id(genre)
    programs = [p for p in all_programs if _matches_genre(p, effective_genre)] if effective_genre else all_programs
    if q:
        programs = filter_programs(programs, needle=q)
    if limit is not None:
        programs = programs[:limit]
    return ProgramListResponse(
        data=[_program_to_api_data(program) for program in programs],
        meta=ProgramListMeta(
            count=len(programs),
            filters=ProgramFiltersMeta(genre=genre or None, q=q or None),
        ),
    )


@api_v1_router.get("/programs/{program_id}", response_model=ProgramDetailResponse)
async def api_v1_program(program: Annotated[Program, Depends(_program_dep)]):
    return ProgramDetailResponse(data=_program_to_api_data(program))


@api_v1_router.get("/programs/{program_id}/episodes", response_model=EpisodeListResponse)
async def api_v1_program_episodes(
    program: Annotated[Program, Depends(_program_dep)],
    program_id: str,
    q: Annotated[str, Query(max_length=200)] = "",
    limit: LimitQuery = None,
):
    try:
        episodes, source = await get_episode_list(program)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Episodes fetch failed: {e}") from e
    if q:
        episodes = filter_episodes(episodes, needle=q)
    if limit is not None:
        episodes = episodes[:limit]
    output_dir = _default_download_dir()
    episode_payloads = [
        _episode_to_api_data(episode, downloaded=is_episode_downloaded(output_dir, program, episode))
        for episode in episodes
    ]
    return EpisodeListResponse(
        data=episode_payloads,
        meta=EpisodeListMeta(count=len(episode_payloads), source=source, program_id=program_id, q=q or None),
    )


@api_v1_router.get("/programs/{program_id}/episodes/{episode_id}", response_model=EpisodeDetailResponse)
async def api_v1_program_episode(
    program: Annotated[Program, Depends(_program_dep)],
    program_id: str,
    episode_id: str,
):
    try:
        episodes, source = await get_episode_list(program)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Episodes fetch failed: {e}") from e
    episode = next((candidate for candidate in episodes if candidate.id == episode_id), None)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    output_dir = _default_download_dir()
    return EpisodeDetailResponse(
        data=_episode_to_api_data(episode, downloaded=is_episode_downloaded(output_dir, program, episode)),
        meta=EpisodeDetailMeta(source=source, program_id=program_id),
    )


@api_v1_router.post(
    "/download-jobs",
    response_model=DownloadJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def api_v1_create_download_job(
    payload: DownloadJobCreateRequest,
    background_tasks: BackgroundTasks,
    job_manager: Annotated[JobManager, Depends(_job_manager_dep)] = None,
):
    job_id, job = _create_download_job_from_models(payload, job_manager, background_tasks)
    return DownloadJobResponse(data=_job_to_api_data(job_id, job))


@api_v1_router.get("/download-jobs", response_model=DownloadJobListResponse)
async def api_v1_download_jobs(
    job_manager: Annotated[JobManager, Depends(_job_manager_dep)] = None,
    status_filter: JobStatusQuery = None,
    limit: LimitQuery = None,
):
    jobs: list = []
    jobs_dict = job_manager.all_jobs()
    for job_id, job in reversed(list(jobs_dict.items())):
        if status_filter and job["status"] != status_filter:
            continue
        jobs.append(_job_to_api_data(job_id, job))
        if limit is not None and len(jobs) >= limit:
            break
    return DownloadJobListResponse(
        data=jobs,
        meta=DownloadJobListMeta(count=len(jobs), status=status_filter),
    )


@api_v1_router.get("/download-jobs/{job_id}", response_model=DownloadJobResponse)
async def api_v1_download_job(job_id: str, job_manager: Annotated[JobManager, Depends(_job_manager_dep)] = None):
    job = job_manager.status_snapshot(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return DownloadJobResponse(data=_job_to_api_data(job_id, job))


@api_v1_router.delete("/download-jobs/{job_id}", response_model=DownloadJobResponse)
async def api_v1_cancel_download_job(job_id: str, job_manager: Annotated[JobManager, Depends(_job_manager_dep)] = None):
    job = job_manager.status_snapshot(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await job_manager.cancel(job_id)
    cancelled_job = job_manager.status_snapshot(job_id)
    assert cancelled_job is not None
    return DownloadJobResponse(data=_job_to_api_data(job_id, cancelled_job))


@api_v1_router.delete("/download-jobs", response_model=DownloadJobListResponse)
async def api_v1_batch_delete_download_jobs(
    status: Annotated[str | None, Query()] = None,
    job_manager: Annotated[JobManager, Depends(_job_manager_dep)] = None,
):
    """複数ダウンロードジョブをバッチ削除。status フィルタで特定ステータスのみ削除。"""
    all_jobs = job_manager.all_jobs()
    deleted_jobs = []

    # ステータスでフィルタして削除
    for job_id, job in all_jobs.items():
        if status is None or job.get("status") == status:
            await job_manager.cancel(job_id)
            cancelled_job = job_manager.status_snapshot(job_id)
            if cancelled_job is not None:
                deleted_jobs.append(_job_to_api_data(job_id, cancelled_job))

    return DownloadJobListResponse(
        data=deleted_jobs,
        meta=DownloadJobListMeta(count=len(deleted_jobs), status=status),
    )


@api_v1_router.get("/download-jobs/{job_id}/file")
async def api_v1_download_job_file(request: Request, job_id: str):
    return await download_file(request, job_id)


@api_v1_router.get("/settings", response_model=SettingsResponse)
async def api_v1_get_settings(request: Request):
    return SettingsResponse(data=_settings_payload(load_storage_limit()))


@api_v1_router.put("/settings", response_model=SettingsResponse)
async def api_v1_save_settings(request: Request, payload: SettingsUpdateRequest):
    return SettingsResponse(data=_update_storage_limit(request, payload))


@api_v1_router.get("/cache/status", response_model=CacheStatusResponse)
async def api_v1_cache_status():
    """キャッシュ状態を取得（サイズ・最終更新時刻）。"""
    status = get_cache_status()
    return CacheStatusResponse(data=CacheStatusData(**status))
